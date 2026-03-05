"""Tester fleet battery parser coverage for Round 6 Slice A."""

from __future__ import annotations

import pytest

from schemas.tester_fleet import HttpBatteryStep, SchemaCaptureBatteryStep
from services.tester_fleet import BatteryParseError, load_battery_file, parse_battery_yaml


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
