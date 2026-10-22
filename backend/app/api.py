import logging
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import User, current_clinician, current_patient, current_user
from app.db import get_db
from app.metrics import ACCESS_LOG_WRITE_FAILURES, APP_EVENTS, CLINICIAN_READS, SHARE_CHANGES
from app.models import AccessLog, Clinician, DiaryEntry, Patient, Share
from app.schemas import (
    AccessRecordOut,
    ClinicianEntryOut,
    ClinicianOut,
    EntryIn,
    EntryOut,
    Me,
    ShareIn,
    ShareOut,
    TelemetryEvent,
)
from app.sharing import actual_recorded_at, covering_shares, search_window

logger = logging.getLogger("diary.sharing")

# The consent wording the app shows before sharing (O.Cons_3). Bump it whenever that text changes.
CONSENT_VERSION = "2026-10-share-v1"

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
AnyUser = Annotated[User, Depends(current_user)]
PatientUser = Annotated[User, Depends(current_patient)]
ClinicianUser = Annotated[User, Depends(current_clinician)]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/me", response_model=Me)
def me(user: AnyUser) -> User:
    return user


@router.get("/clinicians", response_model=list[ClinicianOut])
def list_clinicians(_: AnyUser, db: Db) -> Sequence[Clinician]:
    return db.scalars(select(Clinician).order_by(Clinician.name)).all()


@router.get("/entries", response_model=list[EntryOut])
def list_entries(user: PatientUser, db: Db) -> Sequence[DiaryEntry]:
    query = (
        select(DiaryEntry)
        .where(DiaryEntry.patient_id == user.id)
        .order_by(DiaryEntry.recorded_at.desc())
    )
    return db.scalars(query).all()


@router.post("/entries", response_model=EntryOut, status_code=201)
def create_entry(body: EntryIn, user: PatientUser, db: Db) -> DiaryEntry:
    entry = DiaryEntry(patient_id=user.id, **body.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/shares", response_model=ShareOut, status_code=201)
def create_share(body: ShareIn, user: PatientUser, db: Db) -> Share:
    if db.get(Clinician, body.clinician_id) is None:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "clinician_id"),
                    "msg": "Unknown clinician",
                    "input": body.clinician_id,
                }
            ]
        )
    patient = db.get_one(Patient, user.id)
    share = Share(
        patient_id=user.id,
        timezone=patient.timezone,
        consent_version=CONSENT_VERSION,
        **body.model_dump(),
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    SHARE_CHANGES.labels("created").inc()
    return share


@router.get("/shares", response_model=list[ShareOut])
def list_shares(user: PatientUser, db: Db) -> Sequence[Share]:
    query = (
        select(Share)
        .where(Share.patient_id == user.id)
        .order_by(Share.created_at.desc(), Share.id.desc())
    )
    return db.scalars(query).all()


@router.post("/shares/{share_id}/revoke", response_model=ShareOut)
def revoke_share(share_id: int, user: PatientUser, db: Db) -> Share:
    share = db.get(Share, share_id)
    # Someone else's share looks exactly like a missing one.
    if share is None or share.patient_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    # Revoking twice keeps the first revocation time.
    if share.revoked_at is None:
        share.revoked_at = func.now()
        db.commit()
        db.refresh(share)
        SHARE_CHANGES.labels("revoked").inc()
    return share


@router.get("/access-log", response_model=list[AccessRecordOut])
def access_log(user: PatientUser, db: Db) -> list[AccessRecordOut]:
    query = (
        select(AccessLog, Clinician.name)
        .join(Clinician, Clinician.id == AccessLog.clinician_id)
        .where(AccessLog.patient_id == user.id)
        .order_by(AccessLog.accessed_at.desc(), AccessLog.id.desc())
    )
    return [
        AccessRecordOut(
            clinician_id=record.clinician_id,
            clinician_name=name,
            accessed_at=record.accessed_at,
            entry_ids=record.entry_ids,
        )
        for record, name in db.execute(query).tuples()
    ]


@router.get("/clinician/patients/{patient_id}/entries", response_model=list[ClinicianEntryOut])
def clinician_entries(patient_id: int, user: ClinicianUser, db: Db) -> list[ClinicianEntryOut]:
    shares = db.scalars(
        select(Share).where(
            Share.patient_id == patient_id,
            Share.clinician_id == user.id,
            Share.revoked_at.is_(None),
        )
    ).all()
    # Unknown patient, never shared, shared with another doctor, revoked: all answer the same,
    # so a doctor can't find out who is a patient of ours.
    if not shares:
        CLINICIAN_READS.labels("not_found").inc()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    start, end = search_window(shares)
    candidates = db.scalars(
        select(DiaryEntry).where(
            DiaryEntry.patient_id == patient_id,
            DiaryEntry.recorded_at >= start,
            DiaryEntry.recorded_at < end,
        )
    ).all()
    visible = []
    for entry in candidates:
        covering = covering_shares(entry, shares)
        if not covering:
            continue
        visible.append(
            ClinicianEntryOut(
                id=entry.id,
                recorded_at=actual_recorded_at(entry, covering[0].timezone),
                mood=entry.mood,
                symptoms=entry.symptoms,
                # Notes stay private unless a share covering this day includes them.
                note=entry.note if any(s.include_notes for s in covering) else None,
            )
        )
    visible.sort(key=lambda e: (e.recorded_at, e.id), reverse=True)

    # O.Log_1: no entry leaves without a record. The record is committed before responding;
    # if that fails, the doctor gets nothing.
    if visible:
        db.add(
            AccessLog(
                patient_id=patient_id,
                clinician_id=user.id,
                entry_ids=[e.id for e in visible],
                notes_shown=any(e.note is not None for e in visible),
            )
        )
        try:
            db.commit()
        except SQLAlchemyError as error:
            db.rollback()
            ACCESS_LOG_WRITE_FAILURES.inc()
            CLINICIAN_READS.labels("error").inc()
            # The exception type only: its message holds SQL and parameters.
            logger.error("Access log write failed (%s); read refused", type(error).__name__)
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error"
            ) from None
    CLINICIAN_READS.labels("ok").inc()
    return visible


@router.post("/telemetry", status_code=204)
def telemetry(body: TelemetryEvent, _: AnyUser) -> Response:
    APP_EVENTS.labels(body.event).inc()
    return Response(status_code=204)
