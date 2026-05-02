"""Tester fleet route coverage for Slice D CLI/API integration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from db.repository import InMemoryProbeRepository
from schemas.tester_fleet import BatteryRunArtifact, BatteryRunSummary, BatteryStepResult
from services.probes import ProbeService


def _seed_battery_file(path: Path, *, service_slug: str = "stripe") -> None:
    path.write_text(
        f"""
version: 1
service_slug: {service_slug}
steps:
  - id: health
    kind: http
    method: GET
    url: https://example.com/health
  - id: schema
    kind: schema_capture
    source_step: health
""",
        encoding="utf-8",
    )


def _stub_artifact(service_slug: str = "stripe") -> BatteryRunArtifact:
    now = datetime.now(timezone.utc)
    return BatteryRunArtifact(
        service_slug=service_slug,
        battery_version=1,
        profile="default",
        started_at=now,
        completed_at=now,
        status="ok",
        steps=[
            BatteryStepResult(
                id="health",
                kind="http",
                status="ok",
                latency_ms=42,
                response_code=200,
                metadata={"attempts": 1, "retries": 0},
            ),
            BatteryStepResult(
                id="schema",
                kind="schema_capture",
                status="ok",
                metadata={
                    "source_step": "health",
                    "schema_signature_version": "v2",
                    "schema_fingerprint_v2": "deadbeef",
                    "schema_descriptor": {"type": "object", "keys": ["ok"]},
                },
            ),
        ],
        summary=BatteryRunSummary(success_rate=1.0, p95_latency_ms=42, failures=0),
    )


def test_run_tester_fleet_battery_returns_404_when_missing(client) -> None:
    """Route should return 404 when no seeded battery exists for requested service/profile."""
    response = client.post(
        "/v1/tester-fleet/run",
        json={"service_slug": "does-not-exist", "profile": "default"},
    )

    assert response.status_code == 404
    assert "No battery found" in response.json()["detail"]


def test_run_tester_fleet_battery_rejects_blank_service_slug_before_battery_lookup(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank service slugs should not open the seeded-battery lookup path."""
    from routes import tester_fleet as tester_fleet_routes

    def fail_lookup(service_slug, profile):  # pragma: no cover - should not run
        raise AssertionError("battery lookup should not be opened")

    monkeypatch.setattr(tester_fleet_routes, "_resolve_battery_file", fail_lookup)

    response = client.post(
        "/v1/tester-fleet/run",
        json={"service_slug": "   ", "profile": "default"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "INVALID_PARAMETERS"
    assert payload["error"]["message"] == "Invalid 'service_slug' field."
    assert payload["error"]["detail"] == "Provide a non-empty service_slug value."


def test_run_tester_fleet_battery_rejects_non_object_payload_before_battery_lookup(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-object request bodies should not open seeded-battery lookup."""
    from routes import tester_fleet as tester_fleet_routes

    def fail_lookup(service_slug, profile):  # pragma: no cover - should not run
        raise AssertionError("battery lookup should not be opened")

    monkeypatch.setattr(tester_fleet_routes, "_resolve_battery_file", fail_lookup)

    response = client.post("/v1/tester-fleet/run", json=["stripe"])

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "INVALID_PARAMETERS"
    assert payload["error"]["message"] == "Invalid tester-fleet payload."
    assert payload["error"]["detail"] == "Provide a JSON object payload."


@pytest.mark.parametrize(
    ("field_name", "field_value", "expected_detail"),
    [
        ("service_slug", ["stripe"], "Provide service_slug as a string."),
        ("profile", {"name": "default"}, "Provide profile as a string."),
        ("trigger_source", 123, "Provide trigger_source as a string."),
        ("persist_probes", "sometimes", "Provide persist_probes as a boolean value."),
    ],
)
def test_run_tester_fleet_battery_rejects_malformed_fields_before_battery_lookup(
    client,
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    field_value,
    expected_detail: str,
) -> None:
    """Malformed tester-fleet fields should reject before lookup/run/persistence."""
    from routes import tester_fleet as tester_fleet_routes

    def fail_lookup(service_slug, profile):  # pragma: no cover - should not run
        raise AssertionError("battery lookup should not be opened")

    monkeypatch.setattr(tester_fleet_routes, "_resolve_battery_file", fail_lookup)
    body = {
        "service_slug": "stripe",
        "profile": "default",
        "trigger_source": "tester-fleet-route-test",
    }
    body[field_name] = field_value

    response = client.post("/v1/tester-fleet/run", json=body)

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "INVALID_PARAMETERS"
    assert payload["error"]["message"] == f"Invalid '{field_name}' field."
    assert payload["error"]["detail"] == expected_detail


def test_run_tester_fleet_battery_rejects_blank_profile_before_battery_lookup(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank profiles should not broaden into the default seeded-battery lookup."""
    from routes import tester_fleet as tester_fleet_routes

    def fail_lookup(service_slug, profile):  # pragma: no cover - should not run
        raise AssertionError("battery lookup should not be opened")

    monkeypatch.setattr(tester_fleet_routes, "_resolve_battery_file", fail_lookup)

    response = client.post(
        "/v1/tester-fleet/run",
        json={"service_slug": "stripe", "profile": "   "},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "INVALID_PARAMETERS"
    assert payload["error"]["message"] == "Invalid 'profile' field."
    assert payload["error"]["detail"] == "Provide a non-empty tester-fleet profile value."


def test_run_tester_fleet_battery_rejects_blank_trigger_source_before_run(
    client,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Blank trigger_source values should fail before running or persisting probes."""
    from routes import tester_fleet as tester_fleet_routes

    battery_file = tmp_path / "stripe-health.yaml"
    _seed_battery_file(battery_file)

    class FailingRunner:
        def run_battery(self, battery):  # pragma: no cover - should not run
            raise AssertionError("battery runner should not be opened")

    monkeypatch.setattr(
        tester_fleet_routes,
        "_resolve_battery_file",
        lambda service_slug, profile: battery_file,
    )
    monkeypatch.setattr(tester_fleet_routes, "BatteryRunner", FailingRunner)

    response = client.post(
        "/v1/tester-fleet/run",
        json={
            "service_slug": "stripe",
            "profile": "default",
            "trigger_source": "   ",
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "INVALID_PARAMETERS"
    assert payload["error"]["message"] == "Invalid 'trigger_source' field."
    assert payload["error"]["detail"] == "Provide a non-empty trigger_source value."


def test_run_tester_fleet_battery_runs_and_persists_probe_bridge(
    client,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Route should run battery, write artifact, and persist health/schema probe rows."""
    from routes import tester_fleet as tester_fleet_routes

    battery_file = tmp_path / "stripe-health.yaml"
    _seed_battery_file(battery_file)

    class StubRunner:
        def run_battery(self, battery):
            return _stub_artifact(service_slug=battery.service_slug)

    repository = InMemoryProbeRepository()
    probe_service = ProbeService(repository=repository)

    monkeypatch.setattr(
        tester_fleet_routes,
        "_resolve_battery_file",
        lambda service_slug, profile: battery_file,
    )
    monkeypatch.setattr(tester_fleet_routes, "_artifacts_dir", lambda: tmp_path / "artifacts")
    monkeypatch.setattr(tester_fleet_routes, "BatteryRunner", StubRunner)
    monkeypatch.setattr(tester_fleet_routes, "get_probe_service", lambda: probe_service)

    response = client.post(
        "/v1/tester-fleet/run",
        json={
            "service_slug": "stripe",
            "profile": "default",
            "persist_probes": True,
            "trigger_source": "tester-fleet-route-test",
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body["service_slug"] == "stripe"
    assert body["run"]["status"] == "ok"
    assert body["run"]["summary"]["failures"] == 0
    assert Path(body["artifact_path"]).exists()
    assert sorted(body["persisted_probe_types"]) == ["health", "schema"]
    assert len(body["persisted_probe_ids"]) == 2

    latest_health = repository.fetch_latest_probe("stripe", probe_type="health")
    latest_schema = repository.fetch_latest_probe("stripe", probe_type="schema")

    assert latest_health is not None
    assert latest_schema is not None
    assert latest_health.trigger_source == "tester-fleet-route-test"
    assert latest_schema.probe_metadata is not None
    assert latest_schema.probe_metadata["tester_fleet"]["summary"]["failures"] == 0


def test_run_tester_fleet_battery_supports_no_persist(
    client,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Route should skip probe persistence when persist_probes=false."""
    from routes import tester_fleet as tester_fleet_routes

    battery_file = tmp_path / "stripe-health.yaml"
    _seed_battery_file(battery_file)

    class StubRunner:
        def run_battery(self, battery):
            return _stub_artifact(service_slug=battery.service_slug)

    repository = InMemoryProbeRepository()
    probe_service = ProbeService(repository=repository)

    monkeypatch.setattr(
        tester_fleet_routes,
        "_resolve_battery_file",
        lambda service_slug, profile: battery_file,
    )
    monkeypatch.setattr(tester_fleet_routes, "_artifacts_dir", lambda: tmp_path / "artifacts")
    monkeypatch.setattr(tester_fleet_routes, "BatteryRunner", StubRunner)
    monkeypatch.setattr(tester_fleet_routes, "get_probe_service", lambda: probe_service)

    response = client.post(
        "/v1/tester-fleet/run",
        json={
            "service_slug": "stripe",
            "profile": "default",
            "persist_probes": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["persisted_probe_ids"] == []
    assert body["persisted_probe_types"] == []
    assert repository.fetch_latest_probe("stripe", probe_type="health") is None


def test_run_tester_fleet_battery_canonicalizes_alias_backed_service_slug(
    client,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Route should resolve alias-backed battery files and persist canonical probe ids."""
    from routes import tester_fleet as tester_fleet_routes

    battery_file = tmp_path / "brave-search-health.yaml"
    _seed_battery_file(battery_file, service_slug="brave-search")

    class StubRunner:
        def run_battery(self, battery):
            return _stub_artifact(service_slug=battery.service_slug)

    repository = InMemoryProbeRepository()
    probe_service = ProbeService(repository=repository)

    monkeypatch.setattr(tester_fleet_routes, "_batteries_dir", lambda: tmp_path)
    monkeypatch.setattr(tester_fleet_routes, "_artifacts_dir", lambda: tmp_path / "artifacts")
    monkeypatch.setattr(tester_fleet_routes, "BatteryRunner", StubRunner)
    monkeypatch.setattr(tester_fleet_routes, "get_probe_service", lambda: probe_service)

    response = client.post(
        "/v1/tester-fleet/run",
        json={
            "service_slug": "Brave-Search-Api",
            "profile": "default",
            "persist_probes": True,
            "trigger_source": "tester-fleet-route-test",
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body["service_slug"] == "brave-search-api"
    assert body["run"]["service_slug"] == "brave-search-api"
    assert body["battery_file"].endswith("brave-search-health.yaml")
    assert Path(body["artifact_path"]).name.startswith("brave-search-api-default-v1-")

    latest_health = repository.fetch_latest_probe("brave-search-api", probe_type="health")
    latest_schema = repository.fetch_latest_probe("brave-search-api", probe_type="schema")

    assert latest_health is not None
    assert latest_schema is not None
    assert repository.fetch_latest_probe("brave-search", probe_type="health") is None
    assert latest_health.probe_metadata is not None
    assert latest_health.probe_metadata["service_slug"] == "brave-search-api"
    assert latest_schema.probe_metadata is not None
    assert latest_schema.probe_metadata["service_slug"] == "brave-search-api"
