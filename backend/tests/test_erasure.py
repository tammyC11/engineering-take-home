from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api import CONSENT_VERSION
from app.db import SessionLocal
from app.erase import erase_patient, main
from app.models import AccessLog, ConsentText, DiaryEntry, Patient, Share
from tests.test_clinician_access import (
    CLINICIAN_1,
    CLINICIAN_2,
    PATIENT_1,
    PATIENT_2,
    add_entry,
    read,
    share,
)


def erase(patient_id: int) -> None:
    with SessionLocal() as db:
        erase_patient(db, patient_id)
        db.commit()


def rows_about(patient_id: int) -> int:
    with SessionLocal() as db:
        return sum(
            db.scalar(select(func.count()).select_from(model).where(condition)) or 0
            for model, condition in (
                (Patient, Patient.id == patient_id),
                (DiaryEntry, DiaryEntry.patient_id == patient_id),
                (Share, Share.patient_id == patient_id),
                (AccessLog, AccessLog.patient_id == patient_id),
            )
        )


def test_erasure_removes_everything_about_the_patient(client: TestClient) -> None:
    add_entry("2026-10-03T08:00:00Z")
    add_entry("2026-10-03T08:00:00Z", patient_id=2)
    share(client)
    share(client, headers=PATIENT_2)
    read(client)
    read(client, patient_id=2)

    erase(1)

    assert rows_about(1) == 0
    assert client.get("/entries", headers=PATIENT_1).status_code == 401
    # Nobody else is touched.
    assert len(client.get("/entries", headers=PATIENT_2).json()) == 1
    assert len(client.get("/shares", headers=PATIENT_2).json()) == 1
    assert len(client.get("/access-log", headers=PATIENT_2).json()) == 1


def test_access_records_still_answer_which_doctor_when_which_days_notes_and_consent(
    client: TestClient,
) -> None:
    add_entry("2026-10-03T08:00:00Z")
    add_entry("2026-10-04T22:30:00Z")  # 5 Oct, 00:30 in Berlin
    share(client, include_notes=True)
    read(client)

    erase(1)

    with SessionLocal() as db:
        record, wording = db.execute(
            select(AccessLog, ConsentText.wording).join(
                ConsentText, ConsentText.version == func.any(AccessLog.consent_versions)
            )
        ).one()
    assert record.patient_id is None
    assert record.clinician_id == 1
    assert record.accessed_at is not None
    assert record.days == [date(2026, 10, 3), date(2026, 10, 5)]
    assert record.notes_shown is True
    assert record.consent_versions == [CONSENT_VERSION]
    assert "You can stop sharing at any time" in wording


def test_doctor_cannot_tell_an_erased_patient_from_an_unknown_one(client: TestClient) -> None:
    add_entry("2026-10-03T08:00:00Z")
    share(client)
    share(client, clinician_id=2)

    erase(1)

    erased = read(client, patient_id=1)
    unknown = read(client, patient_id=99, headers=CLINICIAN_2)
    assert erased.status_code == unknown.status_code == 404
    assert erased.json() == unknown.json() == {"detail": "Not found"}
    assert read(client, patient_id=1, headers=CLINICIAN_1).status_code == 404


def test_erasing_an_unknown_patient_changes_nothing(client: TestClient) -> None:
    add_entry("2026-10-03T08:00:00Z")

    with SessionLocal() as db, pytest.raises(LookupError):
        erase_patient(db, 99)

    assert rows_about(1) == 2  # the patient and their entry


def test_command_only_erases_when_confirmed(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    add_entry("2026-10-03T08:00:00Z", note="Slept badly")
    share(client)
    read(client)

    assert main(["1"]) == 0
    assert rows_about(1) == 4  # dry run: patient, entry, share, access record
    assert main(["1", "--confirm"]) == 0
    assert rows_about(1) == 0
    assert main(["1", "--confirm"]) == 1  # already gone

    output = capsys.readouterr()
    assert "1 diary entries and 1 shares deleted, 1 access records kept" in output.out
    # Counts only: never the patient's name, email or health data.
    for secret in ("Anna", "anna.becker", "Slept badly"):
        assert secret not in output.out + output.err


def test_erased_records_are_still_read_only(client: TestClient) -> None:
    add_entry("2026-10-03T08:00:00Z")
    share(client)
    read(client)
    erase(1)

    with SessionLocal() as db:
        unlinked = db.scalars(select(AccessLog).where(AccessLog.patient_id.is_(None))).one()
        unlinked.patient_id = 2
        with pytest.raises(Exception, match="append-only"):
            db.commit()
