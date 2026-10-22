from fastapi.testclient import TestClient

from app.api import CONSENT_VERSION
from app.db import SessionLocal
from app.models import Share

PATIENT_1 = {"Authorization": "Bearer patient-1"}
PATIENT_2 = {"Authorization": "Bearer patient-2"}
CLINICIAN_1 = {"Authorization": "Bearer clinician-1"}
SHARE = {"clinician_id": 1, "from_date": "2026-10-01", "to_date": "2026-10-07"}


def test_patient_shares_their_diary(client: TestClient) -> None:
    response = client.post("/shares", json=SHARE, headers=PATIENT_1)

    assert response.status_code == 201
    share = response.json()
    assert set(share) == {
        "id",
        "clinician_id",
        "from_date",
        "to_date",
        "include_notes",
        "created_at",
        "revoked_at",
    }
    assert share["clinician_id"] == 1
    assert (share["from_date"], share["to_date"]) == ("2026-10-01", "2026-10-07")
    assert share["include_notes"] is False
    assert share["revoked_at"] is None
    assert share["created_at"].endswith("Z")


def test_share_keeps_the_patients_time_zone_and_consent_version(client: TestClient) -> None:
    share_id = client.post("/shares", json=SHARE, headers=PATIENT_2).json()["id"]

    with SessionLocal() as db:
        share = db.get_one(Share, share_id)
        assert share.timezone == "Europe/Lisbon"
        assert share.consent_version == CONSENT_VERSION


def test_notes_are_shared_only_when_asked(client: TestClient) -> None:
    share = client.post("/shares", json={**SHARE, "include_notes": True}, headers=PATIENT_1)

    assert share.json()["include_notes"] is True


def test_a_single_day_can_be_shared(client: TestClient) -> None:
    single_day = {**SHARE, "to_date": SHARE["from_date"]}

    assert client.post("/shares", json=single_day, headers=PATIENT_1).status_code == 201


def test_rejects_invalid_shares(client: TestClient) -> None:
    for invalid in (
        {**SHARE, "from_date": "2026-10-08"},  # ends before it starts
        {**SHARE, "clinician_id": 99},  # unknown clinician
        {**SHARE, "to_date": "next week"},
        {"clinician_id": 1, "from_date": "2026-10-01"},
    ):
        assert client.post("/shares", json=invalid, headers=PATIENT_1).status_code == 422

    assert client.get("/shares", headers=PATIENT_1).json() == []


def test_shares_are_newest_first_and_only_the_patients_own(client: TestClient) -> None:
    first = client.post("/shares", json=SHARE, headers=PATIENT_1).json()
    second = client.post("/shares", json={**SHARE, "clinician_id": 2}, headers=PATIENT_1).json()
    client.post("/shares", json=SHARE, headers=PATIENT_2)

    shares = client.get("/shares", headers=PATIENT_1).json()
    assert [s["id"] for s in shares] == [second["id"], first["id"]]


def test_patient_revokes_a_share(client: TestClient) -> None:
    share_id = client.post("/shares", json=SHARE, headers=PATIENT_1).json()["id"]

    revoked = client.post(f"/shares/{share_id}/revoke", headers=PATIENT_1)

    assert revoked.status_code == 200
    assert revoked.json()["id"] == share_id
    assert revoked.json()["revoked_at"] is not None
    assert client.get("/shares", headers=PATIENT_1).json()[0]["revoked_at"] is not None


def test_revoking_twice_keeps_the_first_time(client: TestClient) -> None:
    share_id = client.post("/shares", json=SHARE, headers=PATIENT_1).json()["id"]

    first = client.post(f"/shares/{share_id}/revoke", headers=PATIENT_1).json()
    second = client.post(f"/shares/{share_id}/revoke", headers=PATIENT_1)

    assert second.status_code == 200
    assert second.json()["revoked_at"] == first["revoked_at"]


def test_patient_cannot_revoke_someone_elses_share(client: TestClient) -> None:
    share_id = client.post("/shares", json=SHARE, headers=PATIENT_1).json()["id"]

    others = client.post(f"/shares/{share_id}/revoke", headers=PATIENT_2)
    missing = client.post("/shares/999/revoke", headers=PATIENT_2)

    assert others.status_code == missing.status_code == 404
    assert others.json() == missing.json() == {"detail": "Not found"}
    assert client.get("/shares", headers=PATIENT_1).json()[0]["revoked_at"] is None


def test_sharing_is_for_patients_only(client: TestClient) -> None:
    assert client.post("/shares", json=SHARE, headers=CLINICIAN_1).status_code == 403
    assert client.get("/shares", headers=CLINICIAN_1).status_code == 403
    assert client.post("/shares/1/revoke", headers=CLINICIAN_1).status_code == 403
    assert client.get("/shares").status_code == 401
