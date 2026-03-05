"""`rhumb score` command."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import typer

from client import RhumbAPIClient
from formatting import render_output


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.55:
        return "medium"
    return "low"


def _tier_badge(tier: str) -> str:
    return {
        "L1": "🔵 Emerging",
        "L2": "🟡 Developing",
        "L3": "🟢 Ready",
        "L4": "⭐ Native",
    }.get(tier, tier)


def _bar(score: float, width: int = 10) -> str:
    filled = max(0, min(width, int(round((score / 10) * width))))
    return "█" * filled + "░" * (width - filled)


def _format_timestamp(value: str | None) -> str:
    if not value:
        return "unknown"
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return timestamp.strftime("%Y-%m-%d %H:%M UTC")


def _render_human(payload: dict[str, Any], show_dimensions: bool, mode: str) -> str:
    service_slug = str(payload.get("service_slug", "unknown"))
    aggregate_score = float(
        payload.get("aggregate_recommendation_score", payload.get("score", 0.0))
    )
    execution_score = float(payload.get("execution_score", payload.get("score", 0.0)))
    raw_access_score = payload.get("access_readiness_score")
    access_score = float(raw_access_score) if raw_access_score is not None else None
    score_version = str(payload.get("an_score_version", "0.1"))
    tier = str(payload.get("tier", ""))
    confidence = float(payload.get("confidence", 0.0))
    explanation = str(payload.get("explanation", ""))
    calculated_at = _format_timestamp(payload.get("calculated_at"))

    selected_mode = mode.lower()
    if selected_mode == "execution":
        headline_label = "Execution Score"
        headline_score = execution_score
    elif selected_mode == "access":
        headline_label = "Access Readiness"
        headline_score = access_score if access_score is not None else 0.0
    else:
        headline_label = "AN Score"
        headline_score = aggregate_score

    snapshot = payload.get("dimension_snapshot", {})
    category_scores = snapshot.get("category_scores", {})
    dimensions = snapshot.get("dimensions", {})
    active_failures = snapshot.get("active_failures", [])
    alternatives = snapshot.get("alternatives", [])

    lines = [
        f"━━━ {service_slug.title()} ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        (
            f"  {headline_label}: {headline_score:.1f} {_tier_badge(tier):<16} "
            f"confidence: {_confidence_label(confidence)}"
        ),
        f"  AN Version: {score_version} (mode: {selected_mode})",
        f"  Tested: {calculated_at}",
        "",
        f"  Aggregate Recommendation  {_bar(aggregate_score)}  {aggregate_score:.1f}",
        f"  Execution Score          {_bar(execution_score)}  {execution_score:.1f}",
    ]

    if access_score is None:
        lines.append("  Access Readiness         N/A (missing A1-A6 access dimensions)")
    else:
        lines.append(f"  Access Readiness         {_bar(access_score)}  {access_score:.1f}")

    lines.extend(
        [
            "",
            f'  "{explanation}"',
            "",
        ]
    )

    for label, key in (
        ("Infrastructure", "infrastructure"),
        ("Interface", "interface"),
        ("Operational", "operational"),
    ):
        category_score = float(category_scores.get(key, 0.0))
        lines.append(f"  {label:<14} {_bar(category_score)}  {category_score:.1f}")

    if show_dimensions and isinstance(dimensions, dict):
        lines.append("")
        lines.append("  Dimensions")
        for dimension, value in sorted(dimensions.items()):
            if value is None:
                lines.append(f"    {dimension}: N/A")
            else:
                lines.append(f"    {dimension}: {float(value):.1f}")

    lines.append("")
    lines.append(f"  Active Failures: {len(active_failures)}")
    for failure in active_failures:
        failure_id = str(failure.get("id", "unknown"))
        summary = str(failure.get("summary", ""))
        lines.append(f"  └─ {failure_id}: {summary}")

    if alternatives:
        rendered_alts = ", ".join(
            f"{str(item.get('service', 'unknown')).title()} ({float(item.get('score', 0.0)):.1f})"
            for item in alternatives
        )
        lines.append("")
        lines.append(f"  Alternatives: {rendered_alts}")

    return "\n".join(lines)


def score(
    service: str,
    dimensions: bool = typer.Option(False, "--dimensions", help="Show all dimension scores."),
    mode: str = typer.Option(
        "aggregate",
        "--mode",
        help="Select headline score mode: aggregate, execution, or access.",
        case_sensitive=False,
    ),
    as_json: bool = typer.Option(False, "--json", help="Return raw JSON payload."),
) -> None:
    """Show AN score for a service."""
    client = RhumbAPIClient()

    try:
        payload = client.get(f"/services/{service}/score")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            typer.echo(f"No AN score available for '{service}'.")
            raise typer.Exit(code=1) from exc
        typer.echo(f"API error: {exc}")
        raise typer.Exit(code=1) from exc
    except httpx.HTTPError as exc:
        typer.echo(f"API error: {exc}")
        raise typer.Exit(code=1) from exc

    selected_mode = mode.lower()
    if selected_mode not in {"aggregate", "execution", "access"}:
        typer.echo("Invalid --mode. Use one of: aggregate, execution, access.")
        raise typer.Exit(code=1)

    if as_json:
        typer.echo(render_output(payload, as_json=True))
        return

    typer.echo(_render_human(payload, show_dimensions=dimensions, mode=selected_mode))
