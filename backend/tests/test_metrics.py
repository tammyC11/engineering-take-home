import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.main import app

CLINICIAN_ROUTE = "/clinician/patients/{patient_id}/entries"


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


def test_crashes_are_counted_as_server_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def crash(*_: object) -> None:
        raise RuntimeError("database is gone")

    labels = {"method": "GET", "route": CLINICIAN_ROUTE, "status": "500"}
    before = REGISTRY.get_sample_value("http_requests_total", labels) or 0
    errors_before = REGISTRY.get_sample_value("clinician_reads_total", {"outcome": "error"})
    with TestClient(app, raise_server_exceptions=False) as client:
        share = {"clinician_id": 1, "from_date": "2026-10-01", "to_date": "2026-10-07"}
        client.post("/shares", json=share, headers={"Authorization": "Bearer patient-1"})
        monkeypatch.setattr("app.api.search_window", crash)

        response = client.get(
            "/clinician/patients/1/entries", headers={"Authorization": "Bearer clinician-1"}
        )

    assert response.status_code == 500
    assert "database is gone" not in response.text
    assert REGISTRY.get_sample_value("http_requests_total", labels) == before + 1
    after = REGISTRY.get_sample_value("clinician_reads_total", {"outcome": "error"})
    assert after == errors_before + 1


def test_alerted_series_start_at_zero(client: TestClient) -> None:
    # Without this, the first errors after a restart show no increase and never alert.
    metrics = client.get("/metrics").text
    assert f'http_requests_total{{method="GET",route="{CLINICIAN_ROUTE}",status="401"}}' in metrics
    assert (
        'http_requests_total{method="POST",route="/shares/{share_id}/revoke",status="500"}'
        in metrics
    )
    assert (
        "access_log_write_failures_total 0.0" in metrics
        or "access_log_write_failures_total" in metrics
    )
