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
        "execution_score": 9.1,
        "access_readiness_score": 8.4,
        "aggregate_recommendation_score": 8.9,
        "an_score_version": "0.2",
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
    assert "AN Version: 0.2 (mode: aggregate)" in result.stdout
    assert "Aggregate Recommendation" in result.stdout
    assert "Execution Score" in result.stdout
    assert "Access Readiness" in result.stdout
    assert "confidence: high" in result.stdout
    assert "Infrastructure" in result.stdout
    assert "Active Failures: 1" in result.stdout


def test_score_command_execution_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Score command should support execution mode headline selection."""

    def fake_get(
        self: RhumbAPIClient, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert path == "/services/stripe/score"
        assert params is None
        return _sample_score_payload()

    monkeypatch.setattr(RhumbAPIClient, "get", fake_get)
    result = runner.invoke(app, ["score", "stripe", "--mode", "execution"])

    assert result.exit_code == 0
    assert "Execution Score: 9.1" in result.stdout
    assert "AN Version: 0.2 (mode: execution)" in result.stdout


def test_score_command_access_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Score command should support access mode headline selection."""

    def fake_get(
        self: RhumbAPIClient, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert path == "/services/stripe/score"
        assert params is None
        return _sample_score_payload()

    monkeypatch.setattr(RhumbAPIClient, "get", fake_get)
    result = runner.invoke(app, ["score", "stripe", "--mode", "access"])

    assert result.exit_code == 0
    assert "Access Readiness: 8.4" in result.stdout
    assert "AN Version: 0.2 (mode: access)" in result.stdout


def test_score_command_invalid_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Score command should reject unsupported mode values."""

    def fake_get(
        self: RhumbAPIClient, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return _sample_score_payload()

    monkeypatch.setattr(RhumbAPIClient, "get", fake_get)
    result = runner.invoke(app, ["score", "stripe", "--mode", "foo"])

    assert result.exit_code == 1
    assert "Invalid --mode" in result.stdout


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
    assert '"execution_score": 9.1' in result.stdout
    assert '"access_readiness_score": 8.4' in result.stdout


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
