from datetime import date

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db import SessionLocal
from app.models import AccessLog, Share


def test_access_log_is_append_only() -> None:
    with SessionLocal() as db:
        record = AccessLog(patient_id=1, clinician_id=1, entry_ids=[1, 2], notes_shown=False)
        db.add(record)
        db.commit()

        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(update(AccessLog).values(entry_ids=[]))
        db.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(delete(AccessLog))
        db.rollback()

        assert db.get(AccessLog, record.id).entry_ids == [1, 2]


def test_share_period_cannot_end_before_it_starts() -> None:
    with SessionLocal() as db:
        db.add(
            Share(
                patient_id=1,
                clinician_id=1,
                from_date=date(2026, 10, 7),
                to_date=date(2026, 10, 1),
                timezone="Europe/Berlin",
                consent_version="test",
            )
        )
        with pytest.raises(IntegrityError, match="share_period"):
            db.commit()
