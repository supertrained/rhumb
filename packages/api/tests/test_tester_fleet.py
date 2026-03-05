"""Tester fleet battery parser and runner coverage for Round 6."""

from __future__ import annotations

import json

import httpx
import pytest

from db.repository import InMemoryProbeRepository
from schemas.tester_fleet import HttpBatteryStep, SchemaCaptureBatteryStep
from services.tester_fleet import (
    BatteryArtifactWriter,
    BatteryParseError,
    BatteryProbeBridge,
    BatteryRunner,
    load_battery_file,
    parse_battery_yaml,
)


def test_parse_battery_yaml_happy_path_preserves_step_order() -> None:
    """Valid YAML should parse into typed steps with deterministic ordering."""
    battery = parse_battery_yaml(
        """
version: 1
service_slug: stripe
profile: default
steps:
  - id: health
    kind: http
    method: GET
    url: https://api.stripe.com/v1/charges?limit=1
    expect_status: [200]
    timeout_ms: 8000
    retries: 1
  - id: schema
    kind: schema_capture
    source_step: health
    fingerprint: semantic_v2
"""
    )

    assert battery.version == 1
    assert battery.service_slug == "stripe"
    assert [step.id for step in battery.steps] == ["health", "schema"]
    assert isinstance(battery.steps[0], HttpBatteryStep)
    assert isinstance(battery.steps[1], SchemaCaptureBatteryStep)


def test_parse_battery_yaml_rejects_duplicate_step_ids() -> None:
    """Step IDs must be unique so runner outputs remain deterministic."""
    with pytest.raises(BatteryParseError, match="Duplicate step id"):
        parse_battery_yaml(
            """
version: 1
service_slug: stripe
steps:
  - id: health
    kind: http
    method: GET
    url: https://api.stripe.com/v1/charges?limit=1
  - id: health
    kind: schema_capture
    source_step: health
"""
        )


def test_parse_battery_yaml_rejects_unknown_or_future_source_step() -> None:
    """schema_capture/idempotency_check steps must reference an earlier step."""
    with pytest.raises(BatteryParseError, match="unknown or future source_step"):
        parse_battery_yaml(
            """
version: 1
service_slug: stripe
steps:
  - id: schema
    kind: schema_capture
    source_step: health
  - id: health
    kind: http
    method: GET
    url: https://api.stripe.com/v1/charges?limit=1
"""
        )


def test_parse_battery_yaml_rejects_invalid_step_kind() -> None:
    """Only v0 step kinds should be accepted by the parser."""
    with pytest.raises(BatteryParseError, match="Invalid battery definition"):
        parse_battery_yaml(
            """
version: 1
service_slug: stripe
steps:
  - id: weird
    kind: graphql
"""
        )


def test_parse_battery_yaml_requires_http_source_for_idempotency_check() -> None:
    """idempotency_check currently replays HTTP request semantics only."""
    with pytest.raises(BatteryParseError, match="requires source_step"):
        parse_battery_yaml(
            """
version: 1
service_slug: stripe
steps:
  - id: health
    kind: http
    method: GET
    url: https://api.stripe.com/v1/charges?limit=1
  - id: schema
    kind: schema_capture
    source_step: health
  - id: replay
    kind: idempotency_check
    source_step: schema
"""
        )


def test_load_battery_file_parses_fixture(tmp_path) -> None:
    """File loader should delegate through parser and return a valid battery."""
    fixture = tmp_path / "battery.yaml"
    fixture.write_text(
        """
version: 1
service_slug: stripe
steps:
  - id: health
    kind: http
    method: GET
    url: https://api.stripe.com/v1/charges?limit=1
""",
        encoding="utf-8",
    )

    battery = load_battery_file(fixture)
    assert battery.service_slug == "stripe"
    assert len(battery.steps) == 1


def test_run_battery_executes_http_and_schema_capture_steps() -> None:
    """Slice B runner should execute HTTP then derive schema fingerprint from source payload."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "https://api.stripe.com/v1/charges?limit=1"
        return httpx.Response(
            status_code=200,
            json={"object": "list", "data": [{"id": "ch_123", "amount": 1000}]},
        )

    battery = parse_battery_yaml(
        """
version: 1
service_slug: stripe
steps:
  - id: health
    kind: http
    method: GET
    url: https://api.stripe.com/v1/charges?limit=1
    expect_status: [200]
  - id: schema
    kind: schema_capture
    source_step: health
"""
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        artifact = BatteryRunner(client=client).run_battery(battery)

    assert artifact.status == "ok"
    assert artifact.service_slug == "stripe"
    assert artifact.summary.failures == 0
    assert artifact.summary.success_rate == 1.0
    assert artifact.summary.p95_latency_ms is not None

    assert len(artifact.steps) == 2
    assert artifact.steps[0].status == "ok"
    assert artifact.steps[0].response_code == 200

    schema_step_metadata = artifact.steps[1].metadata or {}
    assert artifact.steps[1].status == "ok"
    assert schema_step_metadata["schema_signature_version"] == "v2"
    assert schema_step_metadata["schema_fingerprint_v2"]


def test_run_battery_marks_http_status_mismatch_as_error() -> None:
    """HTTP steps should fail when response code is outside expect_status list."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=503, json={"error": "temporarily unavailable"})

    battery = parse_battery_yaml(
        """
version: 1
service_slug: stripe
steps:
  - id: health
    kind: http
    method: GET
    url: https://api.stripe.com/v1/charges?limit=1
    expect_status: [200]
"""
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        artifact = BatteryRunner(client=client).run_battery(battery)

    assert artifact.status == "error"
    assert artifact.summary.failures == 1
    assert artifact.summary.success_rate == 0.0
    assert artifact.steps[0].status == "error"
    assert artifact.steps[0].response_code == 503
    assert artifact.steps[0].error


def test_run_battery_marks_schema_capture_error_when_source_payload_missing() -> None:
    """schema_capture should fail if source HTTP step never produced payload."""

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    battery = parse_battery_yaml(
        """
version: 1
service_slug: stripe
steps:
  - id: health
    kind: http
    method: GET
    url: https://api.stripe.com/v1/charges?limit=1
    retries: 0
  - id: schema
    kind: schema_capture
    source_step: health
"""
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        artifact = BatteryRunner(client=client).run_battery(battery)

    assert artifact.status == "error"
    assert artifact.summary.failures == 2
    assert artifact.steps[0].status == "error"
    assert artifact.steps[1].status == "error"
    assert artifact.steps[1].error


def test_run_battery_reports_idempotency_step_as_not_implemented_in_slice_b() -> None:
    """Slice B runner should surface clear error for not-yet-implemented idempotency steps."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json={"ok": True})

    battery = parse_battery_yaml(
        """
version: 1
service_slug: stripe
steps:
  - id: health
    kind: http
    method: GET
    url: https://api.stripe.com/v1/charges?limit=1
  - id: replay
    kind: idempotency_check
    source_step: health
"""
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        artifact = BatteryRunner(client=client).run_battery(battery)

    assert artifact.status == "error"
    assert artifact.summary.failures == 1
    assert artifact.steps[0].status == "ok"
    assert artifact.steps[1].status == "error"
    assert artifact.steps[1].error
    assert "not implemented" in artifact.steps[1].error


def test_slice_c_artifact_writer_persists_json_artifact(tmp_path) -> None:
    """Slice C writer should persist a deterministic JSON artifact to disk."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json={"ok": True, "service": "stripe"})

    battery = parse_battery_yaml(
        """
version: 1
service_slug: stripe
profile: smoke
steps:
  - id: health
    kind: http
    method: GET
    url: https://api.stripe.com/v1/charges?limit=1
  - id: schema
    kind: schema_capture
    source_step: health
"""
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        artifact = BatteryRunner(client=client).run_battery(battery)

    writer = BatteryArtifactWriter(output_dir=tmp_path / "artifacts")
    artifact_path = writer.write(artifact)

    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["service_slug"] == "stripe"
    assert payload["profile"] == "smoke"
    assert payload["summary"]["failures"] == 0


def test_slice_c_probe_bridge_builds_tester_fleet_metadata(tmp_path) -> None:
    """Bridge metadata should include tester_fleet payload + probe-compatible keys."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json={"object": "list", "data": [{"id": "x"}]})

    battery = parse_battery_yaml(
        """
version: 1
service_slug: stripe
steps:
  - id: health
    kind: http
    method: GET
    url: https://api.stripe.com/v1/charges?limit=1
  - id: schema
    kind: schema_capture
    source_step: health
"""
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        artifact = BatteryRunner(client=client).run_battery(battery)

    metadata = BatteryProbeBridge.build_probe_metadata(
        artifact,
        artifact_path=tmp_path / "artifacts" / "stripe.json",
    )

    assert metadata["runner"] == "tester-fleet-v0"
    assert metadata["service_slug"] == "stripe"
    assert metadata["tester_fleet"]["status"] == "ok"
    assert metadata["tester_fleet"]["artifact_path"].endswith("stripe.json")
    assert metadata["latency_distribution_ms"]["samples"] == 1
    assert metadata["schema_signature_version"] == "v2"
    assert metadata["schema_fingerprint_v2"]


def test_slice_c_probe_bridge_persists_health_and_schema_records(tmp_path) -> None:
    """Bridge persistence should write health + schema probe rows with tester_fleet metadata."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json={"ok": True, "nested": {"value": 1}})

    battery = parse_battery_yaml(
        """
version: 1
service_slug: stripe
steps:
  - id: health
    kind: http
    method: GET
    url: https://api.stripe.com/v1/charges?limit=1
  - id: schema
    kind: schema_capture
    source_step: health
"""
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        artifact = BatteryRunner(client=client).run_battery(battery)

    writer = BatteryArtifactWriter(output_dir=tmp_path / "artifacts")
    artifact_path = writer.write(artifact)

    repository = InMemoryProbeRepository()
    persisted = BatteryProbeBridge(repository).persist(
        artifact,
        artifact_path=artifact_path,
        trigger_source="tester-fleet-test",
    )

    assert len(persisted) == 2
    probe_types = {probe.probe_type for probe in persisted}
    assert probe_types == {"health", "schema"}

    latest_health = repository.fetch_latest_probe("stripe", probe_type="health")
    latest_schema = repository.fetch_latest_probe("stripe", probe_type="schema")

    assert latest_health is not None
    assert latest_schema is not None
    assert latest_health.trigger_source == "tester-fleet-test"
    assert latest_health.probe_metadata is not None
    assert latest_health.probe_metadata["tester_fleet"]["summary"]["failures"] == 0
    assert (
        latest_schema.response_schema_hash == latest_schema.probe_metadata["schema_fingerprint_v2"]
    )
