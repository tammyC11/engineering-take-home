import logging
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.main import WithholdExceptionMessages
from app.models import DiaryEntry


def test_request_log_has_no_health_data(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="diary.requests")
    entry = {"recorded_at": "2026-10-05T08:30:00Z", "mood": 2, "note": "Panic attack at work"}

    client.post("/entries", json=entry, headers={"Authorization": "Bearer patient-1"})

    assert "POST /entries -> 201" in caplog.text
    assert "Panic attack" not in caplog.text


def test_crash_logs_have_no_health_data() -> None:
    # Postgres quotes the failing row, note included, in the error message.
    with SessionLocal() as db:
        db.add(
            DiaryEntry(
                patient_id=1,
                recorded_at=datetime(2026, 10, 5, tzinfo=UTC),
                mood=9,
                note="Panic attack at work",
            )
        )
        with pytest.raises(IntegrityError) as caught:
            db.commit()
    error = caught.value
    assert "Panic attack" in str(error)
    record = logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        __file__,
        1,
        "Exception in ASGI application",
        (),
        (type(error), error, error.__traceback__),
    )

    WithholdExceptionMessages().filter(record)
    logged = logging.Formatter().format(record)

    assert "Exception in ASGI application: IntegrityError (message withheld)" in logged
    assert "db.commit()" in logged  # the stack is kept for debugging
    assert "Panic attack" not in logged


def test_uvicorn_crash_log_is_filtered() -> None:
    filters = logging.getLogger("uvicorn.error").filters
    assert any(isinstance(f, WithholdExceptionMessages) for f in filters)
