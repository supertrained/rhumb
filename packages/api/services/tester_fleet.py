"""Parser utilities for tester fleet battery YAML definitions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from schemas.tester_fleet import BatteryDefinition


class BatteryParseError(ValueError):
    """Raised when a battery definition cannot be parsed or validated."""


def parse_battery_yaml(raw_yaml: str) -> BatteryDefinition:
    """Parse and validate a tester fleet battery definition from YAML text."""
    try:
        payload = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise BatteryParseError(f"Invalid YAML syntax: {exc}") from exc

    if payload is None:
        raise BatteryParseError("Battery YAML is empty")

    if not isinstance(payload, dict):
        raise BatteryParseError("Battery YAML root must be an object")

    return _validate_payload(payload)


def load_battery_file(path: str | Path) -> BatteryDefinition:
    """Read, parse, and validate a battery YAML file from disk."""
    file_path = Path(path)
    try:
        raw_yaml = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BatteryParseError(f"Unable to read battery file '{file_path}': {exc}") from exc

    return parse_battery_yaml(raw_yaml)


def _validate_payload(payload: dict[str, Any]) -> BatteryDefinition:
    try:
        return BatteryDefinition.model_validate(payload)
    except ValidationError as exc:
        raise BatteryParseError(f"Invalid battery definition: {exc}") from exc
