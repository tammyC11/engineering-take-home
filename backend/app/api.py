from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import User, current_patient, current_user
from app.db import get_db
from app.metrics import APP_EVENTS, SHARE_CHANGES
from app.models import Clinician, DiaryEntry, Patient, Share
from app.schemas import (
    ClinicianOut,
    EntryIn,
    EntryOut,
    Me,
    ShareIn,
    ShareOut,
    TelemetryEvent,
)

# The consent wording the app shows before sharing (O.Cons_3). Bump it whenever that text changes.
CONSENT_VERSION = "2026-10-share-v1"

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
AnyUser = Annotated[User, Depends(current_user)]
PatientUser = Annotated[User, Depends(current_patient)]


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


@router.post("/telemetry", status_code=204)
def telemetry(body: TelemetryEvent, _: AnyUser) -> Response:
    APP_EVENTS.labels(body.event).inc()
    return Response(status_code=204)
