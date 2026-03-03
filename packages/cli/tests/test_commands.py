"""CLI command coverage with mocked API responses."""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from client import RhumbAPIClient
from main import app

runner = CliRunner()


def _sample_score_payload() -> dict[str, Any]:
    return {
        "service_slug": "stripe",
        "score": 8.9,
        "confidence": 0.95,
        "tier": "L4",
        "tier_label": "Native",
        "explanation": "Stripe scores 8.9 because structured JSON but OAuth refresh still needs browser auth.",
        "calculated_at": "2026-03-03T22:11:00+00:00",
        "dimension_snapshot": {
            "category_scores": {
                "infrastructure": 8.9,
                "interface": 9.1,
                "operational": 8.7,
            },
            "dimensions": {
                "I1": 9.5,
                "I2": 9.0,
                "F1": 9.0,
                "O3": 8.0,
            },
            "active_failures": [
                {
                    "id": "AF-oauth-redirect",
                    "summary": "Token refresh requires browser redirect",
                }
            ],
            "alternatives": [
                {"service": "square", "score": 7.4},
                {"service": "braintree", "score": 6.8},
            ],
        },
    }


def test_help() -> None:
    """CLI should expose top-level help."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Rhumb" in result.stdout


def test_score_command_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Score command should render the human-readable score card."""

    def fake_get(
        self: RhumbAPIClient, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert path == "/services/stripe/score"
        assert params is None
        return _sample_score_payload()

    monkeypatch.setattr(RhumbAPIClient, "get", fake_get)
    result = runner.invoke(app, ["score", "stripe"])

    assert result.exit_code == 0
    assert "AN Score: 8.9" in result.stdout
    assert "confidence: high" in result.stdout
    assert "Infrastructure" in result.stdout
    assert "Active Failures: 1" in result.stdout


def test_score_command_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Score command should support --json mode."""

    def fake_get(
        self: RhumbAPIClient, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert path == "/services/stripe/score"
        assert params is None
        return _sample_score_payload()

    monkeypatch.setattr(RhumbAPIClient, "get", fake_get)
    result = runner.invoke(app, ["score", "stripe", "--json"])

    assert result.exit_code == 0
    assert '"service_slug": "stripe"' in result.stdout
    assert '"score": 8.9' in result.stdout


def test_score_command_dimension_breakdown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Score command should render individual dimensions when requested."""

    def fake_get(
        self: RhumbAPIClient, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert path == "/services/stripe/score"
        assert params is None
        return _sample_score_payload()

    monkeypatch.setattr(RhumbAPIClient, "get", fake_get)
    result = runner.invoke(app, ["score", "stripe", "--dimensions"])

    assert result.exit_code == 0
    assert "Dimensions" in result.stdout
    assert "I1: 9.5" in result.stdout
    assert "O3: 8.0" in result.stdout
