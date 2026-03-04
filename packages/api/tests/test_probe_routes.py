"""Probe route coverage for WU 1.2."""

from __future__ import annotations

import pytest

from db.repository import InMemoryProbeRepository
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
