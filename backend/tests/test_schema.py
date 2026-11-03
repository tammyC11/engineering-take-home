from datetime import date

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.api import CONSENT_VERSION
from app.db import SessionLocal
from app.models import AccessLog, ConsentText, Share


def add_record() -> int:
    with SessionLocal() as db:
        record = AccessLog(
            patient_id=1,
            clinician_id=1,
            entry_ids=[1, 2],
            days=[date(2026, 10, 3)],
            notes_shown=False,
            consent_versions=[CONSENT_VERSION],
        )
        db.add(record)
        db.commit()
        return record.id


def test_access_log_is_append_only() -> None:
    record_id = add_record()

    with SessionLocal() as db:
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(update(AccessLog).values(entry_ids=[]))
        db.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(delete(AccessLog))
        db.rollback()

        assert db.get_one(AccessLog, record_id).entry_ids == [1, 2]


def test_the_only_allowed_change_is_unlinking_the_patient() -> None:
    record_id = add_record()

    with SessionLocal() as db:
        for not_allowed in (
            {"patient_id": 2},
            {"patient_id": None, "notes_shown": True},
            {"patient_id": None, "days": []},
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(update(AccessLog).values(**not_allowed))
            db.rollback()

        db.execute(update(AccessLog).values(patient_id=None))
        db.commit()

        record = db.get_one(AccessLog, record_id)
        assert (record.patient_id, record.days) == (None, [date(2026, 10, 3)])


def test_share_period_cannot_end_before_it_starts() -> None:
    with SessionLocal() as db:
        db.add(
            Share(
                patient_id=1,
                clinician_id=1,
                from_date=date(2026, 10, 7),
                to_date=date(2026, 10, 1),
                timezone="Europe/Berlin",
                consent_version=CONSENT_VERSION,
            )
        )
        with pytest.raises(IntegrityError, match="share_period"):
            db.commit()


def test_every_consent_version_has_its_wording() -> None:
    with SessionLocal() as db:
        assert db.get_one(ConsentText, CONSENT_VERSION).wording

        db.add(
            Share(
                patient_id=1,
                clinician_id=1,
                from_date=date(2026, 10, 1),
                to_date=date(2026, 10, 7),
                timezone="Europe/Berlin",
                consent_version="wording-nobody-saw",
            )
        )
        with pytest.raises(IntegrityError, match="consent_version"):
            db.commit()
