import logging

import pytest
from fastapi.testclient import TestClient


def test_metrics_count_requests_by_route_template(client: TestClient) -> None:
    client.get("/entries", headers={"Authorization": "Bearer patient-1"})

    metrics = client.get("/metrics").text
    assert 'http_requests_total{method="GET",route="/entries",status="200"}' in metrics


def test_telemetry_counts_app_events(client: TestClient) -> None:
    headers = {"Authorization": "Bearer patient-1"}
    assert (
        client.post("/telemetry", json={"event": "diary_opened"}, headers=headers).status_code
        == 204
    )

    assert 'app_events_total{event="diary_opened"}' in client.get("/metrics").text


def test_telemetry_rejects_free_text(client: TestClient) -> None:
    headers = {"Authorization": "Bearer patient-1"}
    for event in ("Anna Becker", "x" * 65, ""):
        assert client.post("/telemetry", json={"event": event}, headers=headers).status_code == 422


def test_share_changes_are_counted(client: TestClient) -> None:
    headers = {"Authorization": "Bearer patient-1"}
    share = {"clinician_id": 1, "from_date": "2026-10-01", "to_date": "2026-10-07"}
    share_id = client.post("/shares", json=share, headers=headers).json()["id"]
    client.post(f"/shares/{share_id}/revoke", headers=headers)

    metrics = client.get("/metrics").text
    assert 'share_changes_total{action="created"}' in metrics
    assert 'share_changes_total{action="revoked"}' in metrics


def test_request_log_has_no_health_data(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="diary.requests")
    entry = {"recorded_at": "2026-10-05T08:30:00Z", "mood": 2, "note": "Panic attack at work"}

    client.post("/entries", json=entry, headers={"Authorization": "Bearer patient-1"})

    assert "POST /entries -> 201" in caplog.text
    assert "Panic attack" not in caplog.text
