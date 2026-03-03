"""Smoke tests for CLI command registration."""

from typer.testing import CliRunner

from main import app

runner = CliRunner()


def test_help() -> None:
    """CLI should expose top-level help."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Rhumb" in result.stdout


def test_score_command() -> None:
    """Score command should run in scaffold mode."""
    result = runner.invoke(app, ["score", "stripe"])
    assert result.exit_code == 0
    assert "score scaffold" in result.stdout
