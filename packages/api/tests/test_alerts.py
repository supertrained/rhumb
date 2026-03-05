"""Alert route coverage for probe-derived drift primitives."""

from __future__ import annotations

import pytest

from db.repository import InMemoryProbeRepository


@pytest.fixture
def probe_repository() -> InMemoryProbeRepository:
    return InMemoryProbeRepository()


def test_alerts_route_emits_schema_drift_alert(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """Schema fingerprint changes should surface as schema_drift alerts."""
    from routes import scores as score_routes

    score_routes.get_probe_repository.cache_clear()
    repository = InMemoryProbeRepository()

    repository.save_probe(
        service_slug="stripe",
        probe_type="schema",
        status="ok",
        response_schema_hash="schema-old",
        probe_metadata={"schema_fingerprint_v2": "schema-old"},
    )
    repository.save_probe(
        service_slug="stripe",
        probe_type="schema",
        status="ok",
        response_schema_hash="schema-new",
        probe_metadata={"schema_fingerprint_v2": "schema-new"},
    )

    monkeypatch.setattr(score_routes, "get_probe_repository", lambda: repository)

    response = client.get("/v1/alerts")
    assert response.status_code == 200

    body = response.json()
    alerts = body["data"]["alerts"]
    assert any(alert["type"] == "schema_drift" for alert in alerts)


def test_alerts_route_emits_latency_regression_alert(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Health probe p95 regressions should emit latency_regression alerts."""
    from routes import scores as score_routes

    score_routes.get_probe_repository.cache_clear()
    repository = InMemoryProbeRepository()

    repository.save_probe(
        service_slug="openai",
        probe_type="health",
        status="ok",
        latency_ms=90,
        probe_metadata={"latency_distribution_ms": {"p50": 80, "p95": 100, "p99": 120}},
    )
    repository.save_probe(
        service_slug="openai",
        probe_type="health",
        status="ok",
        latency_ms=210,
        probe_metadata={"latency_distribution_ms": {"p50": 170, "p95": 210, "p99": 260}},
    )

    monkeypatch.setattr(score_routes, "get_probe_repository", lambda: repository)

    response = client.get("/v1/alerts")
    assert response.status_code == 200

    body = response.json()
    alerts = body["data"]["alerts"]
    assert any(alert["type"] == "latency_regression" for alert in alerts)
