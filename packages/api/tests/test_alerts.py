"""Alert route coverage for probe-derived drift primitives."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from db.repository import InMemoryProbeRepository
from services.error_envelope import RhumbError


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


def test_alerts_route_canonicalizes_alias_backed_watched_service_ids(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Alias-backed watched services should emit canonical public ids on /v1/alerts."""
    from routes import scores as score_routes
    from services.probe_scheduler import ProbeSpec

    score_routes.get_probe_repository.cache_clear()
    repository = InMemoryProbeRepository()

    repository.save_probe(
        service_slug="brave-search-api",
        probe_type="schema",
        status="ok",
        response_schema_hash="schema-old",
        probe_metadata={"schema_fingerprint_v2": "schema-old"},
    )
    repository.save_probe(
        service_slug="brave-search-api",
        probe_type="schema",
        status="ok",
        response_schema_hash="schema-new",
        probe_metadata={"schema_fingerprint_v2": "schema-new"},
    )

    monkeypatch.setattr(score_routes, "get_probe_repository", lambda: repository)
    monkeypatch.setattr(
        score_routes,
        "DEFAULT_PROBE_SPECS",
        (ProbeSpec(service_slug="brave-search"),),
    )

    response = client.get("/v1/alerts")
    assert response.status_code == 200

    body = response.json()
    alerts = body["data"]["alerts"]
    schema_alert = next(alert for alert in alerts if alert["type"] == "schema_drift")
    assert schema_alert["service_slug"] == "brave-search-api"
    assert schema_alert["title"] == "Schema drift detected for brave-search-api"


def test_alerts_route_reads_alias_backed_probe_history_for_canonical_watched_service(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Canonical watched services should still read historical alias-backed probe rows."""
    from routes import scores as score_routes
    from services.probe_scheduler import ProbeSpec

    score_routes.get_probe_repository.cache_clear()
    repository = InMemoryProbeRepository()

    repository.save_probe(
        service_slug="brave-search",
        probe_type="health",
        status="ok",
        latency_ms=90,
        probe_metadata={"latency_distribution_ms": {"p50": 80, "p95": 100, "p99": 120}},
    )
    repository.save_probe(
        service_slug="brave-search",
        probe_type="health",
        status="ok",
        latency_ms=210,
        probe_metadata={"latency_distribution_ms": {"p50": 170, "p95": 210, "p99": 260}},
    )

    monkeypatch.setattr(score_routes, "get_probe_repository", lambda: repository)
    monkeypatch.setattr(
        score_routes,
        "DEFAULT_PROBE_SPECS",
        (ProbeSpec(service_slug="brave-search-api"),),
    )

    response = client.get("/v1/alerts")
    assert response.status_code == 200

    body = response.json()
    alerts = body["data"]["alerts"]
    latency_alert = next(alert for alert in alerts if alert["type"] == "latency_regression")
    assert latency_alert["service_slug"] == "brave-search-api"
    assert latency_alert["title"] == "Latency regression for brave-search-api"


def test_alerts_route_merges_mixed_alias_and_canonical_probe_history_for_canonical_watched_service(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Canonical watched services should stitch mixed alias-backed probe history into one public alert."""
    from routes import scores as score_routes
    from services.probe_scheduler import ProbeSpec

    score_routes.get_probe_repository.cache_clear()
    repository = InMemoryProbeRepository()

    repository.save_probe(
        service_slug="brave-search",
        probe_type="schema",
        status="ok",
        response_schema_hash="schema-old",
        probe_metadata={"schema_fingerprint_v2": "schema-old"},
    )
    repository.save_probe(
        service_slug="brave-search-api",
        probe_type="schema",
        status="ok",
        response_schema_hash="schema-new",
        probe_metadata={"schema_fingerprint_v2": "schema-new"},
    )

    monkeypatch.setattr(score_routes, "get_probe_repository", lambda: repository)
    monkeypatch.setattr(
        score_routes,
        "DEFAULT_PROBE_SPECS",
        (ProbeSpec(service_slug="brave-search-api"),),
    )

    response = client.get("/v1/alerts")
    assert response.status_code == 200

    body = response.json()
    alerts = body["data"]["alerts"]
    schema_alert = next(alert for alert in alerts if alert["type"] == "schema_drift")
    assert schema_alert["service_slug"] == "brave-search-api"
    assert schema_alert["title"] == "Schema drift detected for brave-search-api"
    assert schema_alert["details"]["latest_fingerprint"] == "schema-new"
    assert schema_alert["details"]["previous_fingerprint"] == "schema-old"
    assert schema_alert["details"]["latest_probe_id"]
    assert schema_alert["details"]["previous_probe_id"]


def test_alerts_route_rejects_invalid_limit_directly() -> None:
    """Blanket alert queries should fail fast on out-of-range limits."""
    from routes import scores as score_routes

    with pytest.raises(RhumbError) as exc_info:
        score_routes._validated_alert_limit(0)

    assert exc_info.value.code == "INVALID_PARAMETERS"
    assert exc_info.value.message == "Invalid 'limit' filter."
    assert exc_info.value.detail == "Provide an integer between 1 and 100."


def test_alerts_http_rejects_invalid_limit_with_canonical_envelope() -> None:
    """HTTP callers should get the canonical 400 envelope for invalid alert limits."""
    from app import create_app
    from routes import scores as score_routes

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            score_routes,
            "get_probe_repository",
            lambda: pytest.fail("get_probe_repository should not run on rejected input"),
        )

        client = TestClient(create_app())
        response = client.get("/v1/alerts", params={"limit": 101})

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "INVALID_PARAMETERS"
    assert payload["error"]["message"] == "Invalid 'limit' filter."
    assert payload["error"]["detail"] == "Provide an integer between 1 and 100."


def test_alerts_http_rejects_malformed_limits_before_probe_reads() -> None:
    """Malformed alert limits should reject canonically before probe repository reads."""
    from app import create_app
    from routes import scores as score_routes

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            score_routes,
            "get_probe_repository",
            lambda: pytest.fail("get_probe_repository should not run on rejected input"),
        )

        client = TestClient(create_app())
        responses = [
            client.get("/v1/alerts", params={"limit": value})
            for value in ("ten", "true", " ", "0", "101")
        ]

    for response in responses:
        assert response.status_code == 400
        payload = response.json()
        assert payload["error"]["code"] == "INVALID_PARAMETERS"
        assert payload["error"]["message"] == "Invalid 'limit' filter."
        assert payload["error"]["detail"] == "Provide an integer between 1 and 100."


def test_alerts_http_normalizes_padded_limit_before_probe_reads() -> None:
    """Padded numeric alert limits should parse before generating alerts."""
    from app import create_app
    from routes import scores as score_routes

    observed: dict[str, int] = {}

    class FakeAlertService:
        def __init__(self, *, repository, watched_services):
            self.repository = repository
            self.watched_services = watched_services

        def generate_alerts(self, *, limit: int):
            observed["limit"] = limit
            return []

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(score_routes, "get_probe_repository", lambda: object())
        monkeypatch.setattr(score_routes, "ProbeAlertService", FakeAlertService)

        client = TestClient(create_app())
        response = client.get("/v1/alerts", params={"limit": " 07 "})

    assert response.status_code == 200
    assert observed["limit"] == 7
