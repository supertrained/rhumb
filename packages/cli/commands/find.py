"""`rhumb find` command."""

from __future__ import annotations

from typing import Any

import httpx
import typer

from client import RhumbAPIClient
from formatting import render_output


def _extract_results(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Normalize search payload into query string + list of result objects."""
    data = payload.get("data", payload)

    if not isinstance(data, dict):
        return "", []

    query = str(data.get("query", ""))
    raw_results = data.get("results", [])

    if not isinstance(raw_results, list):
        return query, []

    normalized: list[dict[str, Any]] = []
    for item in raw_results:
        if isinstance(item, dict):
            normalized.append(item)

    return query, normalized


def _render_human(payload: dict[str, Any], fallback_query: str) -> str:
    query, results = _extract_results(payload)
    display_query = query or fallback_query

    lines = [
        f'━━━ Find: "{display_query}" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        "",
        f"  Results: {len(results)}",
    ]

    if not results:
        lines.extend(["", "  No matching services found."])
        return "\n".join(lines)

    for index, result in enumerate(results, start=1):
        slug = str(result.get("service_slug") or result.get("slug") or "unknown")
        name = str(result.get("name") or slug.title())

        score_raw = result.get("aggregate_recommendation_score", result.get("score"))
        score = float(score_raw) if score_raw is not None else None

        tier = result.get("tier")
        confidence_raw = result.get("confidence")
        confidence = float(confidence_raw) if confidence_raw is not None else None

        rationale = (
            result.get("why")
            or result.get("reason")
            or result.get("explanation")
            or ""
        )

        score_text = "N/A" if score is None else f"{score:.1f}"
        tier_text = str(tier) if tier else "N/A"
        confidence_text = "N/A" if confidence is None else f"{confidence:.2f}"

        lines.extend(
            [
                "",
                f"  {index}. {name} ({slug})",
                f"     Score: {score_text} | Tier: {tier_text} | Confidence: {confidence_text}",
            ]
        )

        if rationale:
            lines.append(f"     Why: {str(rationale)}")

    return "\n".join(lines)


def find(
    query: str,
    limit: int = typer.Option(10, "--limit", min=1, max=50, help="Maximum results to return."),
    as_json: bool = typer.Option(False, "--json", help="Return raw JSON payload."),
) -> None:
    """Search services by free-text query."""
    client = RhumbAPIClient()

    try:
        payload = client.get("/search", params={"q": query, "limit": limit})
    except httpx.HTTPStatusError as exc:
        typer.echo(f"API error: {exc}")
        raise typer.Exit(code=1) from exc
    except httpx.HTTPError as exc:
        typer.echo(f"API error: {exc}")
        raise typer.Exit(code=1) from exc

    if as_json:
        typer.echo(render_output(payload, as_json=True))
        return

    typer.echo(_render_human(payload, fallback_query=query))
