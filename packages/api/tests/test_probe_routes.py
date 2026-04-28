"""Probe route coverage for WU 1.2."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from db.repository import InMemoryProbeRepository, StoredProbe
from services.probe_scheduler import ProbeScheduler, ProbeSpec
from services.probes import ProbeService


def test_probe_run_and_latest_fetch_round_trip(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /v1/probes/run should persist and GET latest should return that result."""
    from routes import probes as probe_routes

    probe_routes.get_probe_service.cache_clear()
    probe_routes.get_probe_scheduler.cache_clear()

    repository = InMemoryProbeRepository()
    service = ProbeService(repository=repository)
    monkeypatch.setattr(probe_routes, "get_probe_service", lambda: service)

    run_response = client.post(
        "/v1/probes/run",
        json={
            "service_slug": "stripe",
            "probe_type": "health",
            "trigger_source": "internal-test",
            "sample_count": 3,
        },
    )
    assert run_response.status_code == 200

    run_body = run_response.json()
    assert run_body["service_slug"] == "stripe"
    assert run_body["probe_type"] == "health"
    assert run_body["status"] == "ok"
    assert run_body["probe_id"]
    assert run_body["run_id"]
    assert run_body["metadata"]["latency_distribution_ms"]["p50"] >= 0
    assert run_body["metadata"]["latency_distribution_ms"]["p95"] >= 0
    assert run_body["metadata"]["latency_distribution_ms"]["p99"] >= 0

    latest_response = client.get("/v1/services/stripe/probes/latest")
    assert latest_response.status_code == 200

    latest_body = latest_response.json()
    assert latest_body["probe_id"] == run_body["probe_id"]
    assert latest_body["run_id"] == run_body["run_id"]
    assert latest_body["trigger_source"] == "internal-test"


def test_probe_routes_canonicalize_alias_backed_service_slugs(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Alias-backed probe writes and reads should stay on canonical public ids."""
    from routes import probes as probe_routes

    probe_routes.get_probe_service.cache_clear()
    probe_routes.get_probe_scheduler.cache_clear()

    repository = InMemoryProbeRepository()
    service = ProbeService(repository=repository)
    monkeypatch.setattr(probe_routes, "get_probe_service", lambda: service)

    run_response = client.post(
        "/v1/probes/run",
        json={
            "service_slug": "Brave-Search",
            "probe_type": "health",
            "trigger_source": "internal-test",
        },
    )
    assert run_response.status_code == 200

    run_body = run_response.json()
    assert run_body["service_slug"] == "brave-search-api"
    assert run_body["metadata"]["service_slug"] == "brave-search-api"
    assert run_body["raw_response"]["service_slug"] == "brave-search-api"

    latest_response = client.get("/v1/services/brave-search-api/probes/latest")
    assert latest_response.status_code == 200

    latest_body = latest_response.json()
    assert latest_body["probe_id"] == run_body["probe_id"]
    assert latest_body["service_slug"] == "brave-search-api"
    assert latest_body["metadata"]["service_slug"] == "brave-search-api"
    assert latest_body["raw_response"]["service_slug"] == "brave-search-api"


def test_latest_probe_recanonicalizes_legacy_alias_backed_stored_rows(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy stored probe rows should still read back on canonical public ids."""
    from routes import probes as probe_routes

    probe_routes.get_probe_service.cache_clear()
    probe_routes.get_probe_scheduler.cache_clear()

    repository = InMemoryProbeRepository()
    legacy_probe = repository.save_probe(
        service_slug="Brave-Search",
        probe_type="health",
        status="ok",
        latency_ms=42,
        response_code=200,
        response_schema_hash="schema_legacy",
        raw_response={
            "message": "Probe runner scaffold executed",
            "service_slug": "Brave-Search",
            "probe_type": "health",
        },
        probe_metadata={
            "runner": "scaffold",
            "service_slug": "Brave-Search",
            "probe_type": "health",
        },
        trigger_source="legacy-import",
        runner_version="scaffold-v1",
    )
    service = ProbeService(repository=repository)
    monkeypatch.setattr(probe_routes, "get_probe_service", lambda: service)

    latest_response = client.get("/v1/services/brave-search-api/probes/latest")
    assert latest_response.status_code == 200

    latest_body = latest_response.json()
    assert latest_body["probe_id"] == str(legacy_probe.id)
    assert latest_body["service_slug"] == "brave-search-api"
    assert latest_body["metadata"]["service_slug"] == "brave-search-api"
    assert latest_body["raw_response"]["service_slug"] == "brave-search-api"


def test_latest_probe_canonicalizes_same_service_alias_text_for_canonical_rows(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Canonical probe rows should still rewrite self-alias text in nested payloads."""
    from routes import probes as probe_routes

    probe_routes.get_probe_service.cache_clear()
    probe_routes.get_probe_scheduler.cache_clear()

    repository = InMemoryProbeRepository()
    latest_probe = repository.save_probe(
        service_slug="brave-search-api",
        probe_type="health",
        status="ok",
        latency_ms=38,
        response_code=200,
        response_schema_hash="schema_same_alias",
        raw_response={
            "message": "Legacy brave-search probe passed after brave-search retry.",
            "detail": {
                "summary": "brave-search recovered for the public health check.",
            },
            "service_slug": "brave-search-api",
        },
        probe_metadata={
            "runner": "scaffold",
            "service_slug": "brave-search-api",
            "notes": ["brave-search stabilized before this sample."],
        },
        trigger_source="legacy-import",
        runner_version="scaffold-v1",
    )
    service = ProbeService(repository=repository)
    monkeypatch.setattr(probe_routes, "get_probe_service", lambda: service)

    latest_response = client.get("/v1/services/brave-search-api/probes/latest")
    assert latest_response.status_code == 200

    latest_body = latest_response.json()
    assert latest_body["probe_id"] == str(latest_probe.id)
    assert latest_body["service_slug"] == "brave-search-api"
    assert latest_body["metadata"]["service_slug"] == "brave-search-api"
    assert latest_body["metadata"]["notes"] == [
        "brave-search-api stabilized before this sample.",
    ]
    assert latest_body["raw_response"]["service_slug"] == "brave-search-api"
    assert latest_body["raw_response"]["message"] == (
        "Legacy brave-search-api probe passed after brave-search-api retry."
    )
    assert latest_body["raw_response"]["detail"]["summary"] == (
        "brave-search-api recovered for the public health check."
    )
    assert "brave-search-api-api" not in latest_body["raw_response"]["message"]


def test_scheduler_dry_run_accepts_alias_filters_and_serializes_canonical_service_ids(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scheduler dry-run should match alias-backed specs by canonical ids and report canonical keys."""
    from routes import probes as probe_routes

    probe_routes.get_probe_service.cache_clear()
    probe_routes.get_probe_scheduler.cache_clear()

    scheduler = ProbeScheduler(
        probe_service=ProbeService(repository=InMemoryProbeRepository()),
        specs=[ProbeSpec(service_slug="brave-search")],
    )
    monkeypatch.setattr(probe_routes, "get_probe_scheduler", lambda: scheduler)

    response = client.post(
        "/v1/probes/schedule/run",
        json={"service_slugs": ["brave-search-api"], "dry_run": True},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["selected_services"] == ["brave-search-api"]
    assert sorted(body["cadence_by_service"].keys()) == ["brave-search-api"]


@pytest.mark.parametrize(
    ("probe_type", "expected_behavior"),
    [
        ("auth", "Target should reject unauthenticated requests (401/403)"),
        ("schema", "Target response schema hash should remain stable"),
    ],
)
def test_probe_run_supports_auth_and_schema_probe_types(
    client,
    monkeypatch: pytest.MonkeyPatch,
    probe_type: str,
    expected_behavior: str,
) -> None:
    """Auth/schema probes should store their type-specific scaffold metadata."""
    from routes import probes as probe_routes

    probe_routes.get_probe_service.cache_clear()
    probe_routes.get_probe_scheduler.cache_clear()
    monkeypatch.setattr(
        probe_routes,
        "get_probe_service",
        lambda: ProbeService(repository=InMemoryProbeRepository()),
    )

    response = client.post(
        "/v1/probes/run",
        json={
            "service_slug": "stripe",
            "probe_type": probe_type,
            "trigger_source": "internal-test",
        },
    )
    assert response.status_code == 200

    body = response.json()
    assert body["probe_type"] == probe_type
    assert body["metadata"]["probe_type"] == probe_type
    assert body["raw_response"]["expected_behavior"] == expected_behavior

    if probe_type == "schema":
        assert body["metadata"]["schema_signature_version"] == "v2"
        assert body["metadata"]["schema_fingerprint_v2"]
        assert body["response_schema_hash"] == body["metadata"]["schema_fingerprint_v2"]


def test_latest_probe_returns_404_when_missing(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET latest probe should return 404 when a service has no probe history."""
    from routes import probes as probe_routes

    probe_routes.get_probe_service.cache_clear()
    probe_routes.get_probe_scheduler.cache_clear()
    monkeypatch.setattr(
        probe_routes,
        "get_probe_service",
        lambda: ProbeService(repository=InMemoryProbeRepository()),
    )

    response = client.get("/v1/services/unknown/probes/latest")
    assert response.status_code == 404


def test_latest_probe_missing_canonicalizes_alias_input(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing latest-probe reads should report canonical public ids for alias inputs."""
    from routes import probes as probe_routes

    probe_routes.get_probe_service.cache_clear()
    probe_routes.get_probe_scheduler.cache_clear()
    monkeypatch.setattr(
        probe_routes,
        "get_probe_service",
        lambda: ProbeService(repository=InMemoryProbeRepository()),
    )

    response = client.get("/v1/services/Brave-Search/probes/latest")
    assert response.status_code == 404

    body = response.json()
    assert body["detail"] == "No probe result found for service 'brave-search-api'"


def test_latest_probe_rejects_blank_service_slug_before_repository_read(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank latest-probe service path values should fail before opening probe storage."""
    from routes import probes as probe_routes

    probe_routes.get_probe_service.cache_clear()
    probe_routes.get_probe_scheduler.cache_clear()

    def fail_probe_service() -> ProbeService:
        raise AssertionError("probe repository should not be opened")

    monkeypatch.setattr(probe_routes, "get_probe_service", fail_probe_service)

    response = client.get("/v1/services/%20/probes/latest")

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'service_slug' path parameter."
    assert body["error"]["detail"] == "Provide a non-empty service slug from GET /v1/services."


def test_latest_probe_rejects_blank_probe_type_before_repository_read(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank probe_type filters should not broaden latest-probe reads."""
    from routes import probes as probe_routes

    probe_routes.get_probe_service.cache_clear()
    probe_routes.get_probe_scheduler.cache_clear()

    def fail_probe_service() -> ProbeService:
        raise AssertionError("probe repository should not be opened")

    monkeypatch.setattr(probe_routes, "get_probe_service", fail_probe_service)

    response = client.get("/v1/services/stripe/probes/latest", params={"probe_type": "   "})

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'probe_type' filter."
    assert body["error"]["detail"] == "Provide a non-empty probe_type value or omit the filter."


def test_scheduler_entrypoint_runs_seed_specs(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /v1/probes/schedule/run should execute selected seed specs."""
    from routes import probes as probe_routes

    probe_routes.get_probe_service.cache_clear()
    probe_routes.get_probe_scheduler.cache_clear()

    repository = InMemoryProbeRepository()
    service = ProbeService(repository=repository)
    scheduler = ProbeScheduler(
        probe_service=service,
        specs=[
            ProbeSpec(service_slug="stripe"),
            ProbeSpec(service_slug="openai"),
            ProbeSpec(service_slug="hubspot"),
        ],
    )

    monkeypatch.setattr(probe_routes, "get_probe_service", lambda: service)
    monkeypatch.setattr(probe_routes, "get_probe_scheduler", lambda: scheduler)

    response = client.post(
        "/v1/probes/schedule/run",
        json={"service_slugs": ["stripe", "openai"], "sample_count": 3},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["total_specs"] == 3
    assert body["selected_services"] == ["stripe", "openai"]
    assert body["executed"] == 2
    assert body["succeeded"] == 2
    assert body["failed"] == 0
    assert len(body["probe_ids"]) == 2
    assert body["by_service"]["stripe"] == "ok"
    assert body["by_service"]["openai"] == "ok"
    assert body["cadence_by_service"]["stripe"]["base_interval_minutes"] == 30
    assert body["cadence_by_service"]["stripe"]["next_interval_minutes"] >= 5
    assert body["cadence_by_service"]["stripe"]["next_interval_minutes"] <= 1440

    latest_response = client.get("/v1/services/stripe/probes/latest")
    assert latest_response.status_code == 200


def test_scheduler_entrypoint_supports_dry_run(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """Dry run should return selected seed specs without executing probes."""
    from routes import probes as probe_routes

    probe_routes.get_probe_service.cache_clear()
    probe_routes.get_probe_scheduler.cache_clear()

    scheduler = ProbeScheduler(
        probe_service=ProbeService(repository=InMemoryProbeRepository()),
        specs=[ProbeSpec(service_slug="stripe"), ProbeSpec(service_slug="openai")],
    )
    monkeypatch.setattr(probe_routes, "get_probe_scheduler", lambda: scheduler)

    response = client.post(
        "/v1/probes/schedule/run",
        json={"service_slugs": ["stripe"], "dry_run": True},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["total_specs"] == 2
    assert body["selected_services"] == ["stripe"]
    assert body["executed"] == 0
    assert body["succeeded"] == 0
    assert body["failed"] == 0
    assert body["probe_ids"] == []
    assert body["cadence_by_service"]["stripe"]["base_interval_minutes"] == 30


def test_scheduler_guardrails_apply_interval_floor_and_failure_backoff(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cadence policy should clamp base interval and back off on repeated failures."""
    from routes import probes as probe_routes

    class StubProbeService:
        async def run_probe(
            self,
            service_slug: str,
            probe_type: str = "health",
            target_url: str | None = None,
            payload: dict | None = None,
            trigger_source: str = "internal",
            sample_count: int = 1,
        ) -> StoredProbe:
            return StoredProbe(
                id=uuid4(),
                run_id=uuid4(),
                service_slug=service_slug,
                probe_type=probe_type,
                status="error",
                latency_ms=180,
                response_code=500,
                response_schema_hash=None,
                raw_response={"error": "boom"},
                probe_metadata={"latency_distribution_ms": {"p50": 180, "p95": 220, "p99": 260}},
                runner_version="scaffold-v1",
                trigger_source=trigger_source,
                probed_at=datetime.now(timezone.utc),
            )

        def list_recent_probes(
            self,
            service_slug: str,
            probe_type: str | None = None,
            limit: int = 10,
        ) -> list[StoredProbe]:
            now = datetime.now(timezone.utc)
            return [
                StoredProbe(
                    id=uuid4(),
                    run_id=uuid4(),
                    service_slug=service_slug,
                    probe_type=probe_type or "health",
                    status="error",
                    latency_ms=250,
                    response_code=500,
                    response_schema_hash=None,
                    raw_response={"error": "recent-failure-1"},
                    probe_metadata=None,
                    runner_version="scaffold-v1",
                    trigger_source="scheduler",
                    probed_at=now,
                ),
                StoredProbe(
                    id=uuid4(),
                    run_id=uuid4(),
                    service_slug=service_slug,
                    probe_type=probe_type or "health",
                    status="error",
                    latency_ms=240,
                    response_code=500,
                    response_schema_hash=None,
                    raw_response={"error": "recent-failure-2"},
                    probe_metadata=None,
                    runner_version="scaffold-v1",
                    trigger_source="scheduler",
                    probed_at=now,
                ),
            ]

    probe_routes.get_probe_service.cache_clear()
    probe_routes.get_probe_scheduler.cache_clear()

    scheduler = ProbeScheduler(
        probe_service=StubProbeService(),
        specs=[ProbeSpec(service_slug="stripe")],
    )
    monkeypatch.setattr(probe_routes, "get_probe_scheduler", lambda: scheduler)

    response = client.post(
        "/v1/probes/schedule/run",
        json={"service_slugs": ["stripe"], "base_interval_minutes": 1},
    )
    assert response.status_code == 200

    body = response.json()
    cadence = body["cadence_by_service"]["stripe"]
    assert cadence["base_interval_minutes"] == 5
    assert cadence["consecutive_failures"] == 2
    assert cadence["next_interval_minutes"] == 20
