from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import DiaryEntry, Patient

PATIENT_1 = {"Authorization": "Bearer patient-1"}  # Europe/Berlin
PATIENT_2 = {"Authorization": "Bearer patient-2"}
CLINICIAN_1 = {"Authorization": "Bearer clinician-1"}  # Dr. Lena Hofmann
CLINICIAN_2 = {"Authorization": "Bearer clinician-2"}
WEEK = {"clinician_id": 1, "from_date": "2026-10-01", "to_date": "2026-10-07"}


def add_entry(
    recorded_at: str, patient_id: int = 1, note: str | None = "Private", **kw: Any
) -> int:
    with SessionLocal() as db:
        entry = DiaryEntry(
            patient_id=patient_id,
            recorded_at=datetime.fromisoformat(recorded_at),
            mood=3,
            symptoms=["headache"],
            note=note,
            **kw,
        )
        db.add(entry)
        db.commit()
        return entry.id


def share(client: TestClient, headers: dict[str, str] = PATIENT_1, **overrides: Any) -> int:
    response = client.post("/shares", json={**WEEK, **overrides}, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def read(client: TestClient, patient_id: int = 1, headers: dict[str, str] = CLINICIAN_1) -> Any:
    return client.get(f"/clinician/patients/{patient_id}/entries", headers=headers)


def test_doctor_reads_shared_entries_without_notes(client: TestClient) -> None:
    entry_id = add_entry("2026-10-03T08:00:00Z", note="Slept badly")
    share(client)

    response = read(client)

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": entry_id,
            "recorded_at": "2026-10-03T08:00:00Z",
            "mood": 3,
            "symptoms": ["headache"],
            "note": None,
        }
    ]


def test_notes_are_shown_only_when_the_patient_includes_them(client: TestClient) -> None:
    add_entry("2026-10-03T08:00:00Z", note="Slept badly")
    share(client, include_notes=True)

    assert read(client).json()[0]["note"] == "Slept badly"


def test_period_is_in_the_patients_own_days(client: TestClient) -> None:
    # Berlin is UTC+2 in early October.
    add_entry("2026-09-30T21:30:00Z")  # 30 Sep, 23:30
    first_day = add_entry("2026-09-30T22:30:00Z")  # 1 Oct, 00:30
    last_day = add_entry("2026-10-07T21:30:00Z")  # 7 Oct, 23:30
    add_entry("2026-10-07T22:30:00Z")  # 8 Oct, 00:30
    add_entry("2026-10-03T08:00:00Z", patient_id=2)  # someone else's diary
    share(client)

    assert [e["id"] for e in read(client).json()] == [last_day, first_day]


def test_app_v1_entries_are_read_as_local_time(client: TestClient) -> None:
    # Stored as local wall-clock time labelled UTC.
    late_evening = add_entry("2026-10-07T23:50:00Z", source="app-v1")  # 7 Oct, 23:50 in Berlin
    add_entry("2026-09-30T23:30:00Z", source="app-v1")  # 30 Sep, 23:30 in Berlin
    share(client)

    entries = read(client).json()

    assert [e["id"] for e in entries] == [late_evening]
    assert entries[0]["recorded_at"] == "2026-10-07T21:50:00Z"


def test_share_keeps_the_time_zone_it_was_given_with(client: TestClient) -> None:
    share(client)
    with SessionLocal() as db:
        db.execute(update(Patient).where(Patient.id == 1).values(timezone="America/New_York"))
        db.commit()
    add_entry("2026-10-07T23:30:00Z")  # 8 Oct in Berlin, still 7 Oct in New York

    assert read(client).json() == []


def test_overlapping_shares_show_a_note_if_any_covering_share_includes_notes(
    client: TestClient,
) -> None:
    add_entry("2026-10-02T08:00:00Z", note="Tuesday")
    add_entry("2026-10-03T08:00:00Z", note="Wednesday")
    share(client)
    with_notes = share(client, from_date="2026-10-03", to_date="2026-10-03", include_notes=True)

    assert [e["note"] for e in read(client).json()] == ["Wednesday", None]

    client.post(f"/shares/{with_notes}/revoke", headers=PATIENT_1)
    assert [e["note"] for e in read(client).json()] == [None, None]


def test_revoking_stops_access(client: TestClient) -> None:
    add_entry("2026-10-03T08:00:00Z")
    share_id = share(client)
    assert read(client).status_code == 200

    client.post(f"/shares/{share_id}/revoke", headers=PATIENT_1)

    assert read(client).status_code == 404


def test_every_refusal_looks_the_same(client: TestClient) -> None:
    add_entry("2026-10-03T08:00:00Z")
    add_entry("2026-10-03T08:00:00Z", patient_id=2)
    share(client, clinician_id=2)  # patient 1 shares with Dr. Braun only
    revoked = share(client, headers=PATIENT_2)  # patient 2 shares with Dr. Hofmann, then stops
    client.post(f"/shares/{revoked}/revoke", headers=PATIENT_2)

    refusals = [
        read(client, patient_id=99),  # no such patient
        read(client, patient_id=1),  # shared with another doctor
        read(client, patient_id=2),  # revoked
        read(client, patient_id=2, headers=CLINICIAN_2),  # never shared
    ]

    assert {r.status_code for r in refusals} == {404}
    assert {r.content for r in refusals} == {b'{"detail":"Not found"}'}


def test_active_share_without_entries_is_an_empty_list(client: TestClient) -> None:
    share(client)

    assert read(client).json() == []
    assert client.get("/access-log", headers=PATIENT_1).json() == []


def test_clinician_route_is_for_clinicians_only(client: TestClient) -> None:
    assert read(client, headers=PATIENT_1).status_code == 403


def test_patient_sees_who_read_their_diary(client: TestClient) -> None:
    first = add_entry("2026-10-03T08:00:00Z")
    second = add_entry("2026-10-05T08:00:00Z")
    share(client)
    share(client, clinician_id=2, from_date="2026-10-05")
    read(client)
    read(client, headers=CLINICIAN_2)

    log = client.get("/access-log", headers=PATIENT_1).json()

    assert [set(record) for record in log] == [
        {"clinician_id", "clinician_name", "accessed_at", "entry_ids"}
    ] * 2
    assert [(r["clinician_name"], r["entry_ids"]) for r in log] == [
        ("Dr. Felix Braun", [second]),
        ("Dr. Lena Hofmann", [second, first]),
    ]
    assert client.get("/access-log", headers=PATIENT_2).json() == []
    assert client.get("/access-log", headers=CLINICIAN_1).status_code == 403


def test_refused_reads_are_not_logged(client: TestClient) -> None:
    add_entry("2026-10-03T08:00:00Z")

    read(client)

    assert client.get("/access-log", headers=PATIENT_1).json() == []


def test_no_data_leaves_when_the_read_cannot_be_logged(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_entry("2026-10-03T08:00:00Z", note="Slept badly")
    share(client, include_notes=True)
    failures_before = REGISTRY.get_sample_value("access_log_write_failures_total")

    def broken_commit(self: Session) -> None:
        raise SQLAlchemyError("INSERT INTO access_log ... secret details")

    monkeypatch.setattr(Session, "commit", broken_commit)
    response = read(client)
    monkeypatch.undo()

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert REGISTRY.get_sample_value("access_log_write_failures_total") == failures_before + 1
    assert client.get("/access-log", headers=PATIENT_1).json() == []
