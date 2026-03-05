"""`rhumb test-battery` command."""

from __future__ import annotations

from typing import Any

import httpx
import typer

from client import RhumbAPIClient
from formatting import render_output


def _render_human(payload: dict[str, Any], service: str) -> str:
    run = payload.get("run") if isinstance(payload.get("run"), dict) else {}
    summary = run.get("summary") if isinstance(run.get("summary"), dict) else {}

    display_service = str(payload.get("service_slug") or service)
    status = str(run.get("status") or "unknown")
    failures = int(summary.get("failures", 0))
    success_rate = float(summary.get("success_rate", 0.0))
    p95_latency_ms = summary.get("p95_latency_ms")
    artifact_path = str(payload.get("artifact_path", ""))

    persisted_probe_types = payload.get("persisted_probe_types", [])
    if not isinstance(persisted_probe_types, list):
        persisted_probe_types = []

    latency_text = f"{int(p95_latency_ms)} ms" if p95_latency_ms is not None else "N/A"
    probes_text = ", ".join(str(item) for item in persisted_probe_types) or "none"

    lines = [
        f"━━━ Tester Fleet: {display_service} ━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"  Status: {status}",
        f"  Success Rate: {success_rate:.2f}",
        f"  Failures: {failures}",
        f"  P95 Latency: {latency_text}",
        f"  Persisted Probes: {probes_text}",
    ]

    if artifact_path:
        lines.append(f"  Artifact: {artifact_path}")

    return "\n".join(lines)


def test_battery(
    service: str,
    profile: str = typer.Option("default", "--profile", help="Battery profile name."),
    persist_probes: bool = typer.Option(
        True,
        "--persist-probes/--no-persist-probes",
        help="Persist run outputs into probe storage metadata.",
    ),
    trigger_source: str = typer.Option(
        "tester_fleet_cli",
        "--trigger-source",
        help="Trigger source label for persisted probe rows.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Return raw JSON payload."),
) -> None:
    """Run a seeded tester-fleet battery for one service."""
    client = RhumbAPIClient()

    try:
        payload = client.post(
            "/tester-fleet/run",
            json={
                "service_slug": service,
                "profile": profile,
                "persist_probes": persist_probes,
                "trigger_source": trigger_source,
            },
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            typer.echo(f"No battery found for '{service}' (profile '{profile}').")
            raise typer.Exit(code=1) from exc
        typer.echo(f"API error: {exc}")
        raise typer.Exit(code=1) from exc
    except httpx.HTTPError as exc:
        typer.echo(f"API error: {exc}")
        raise typer.Exit(code=1) from exc

    if as_json:
        typer.echo(render_output(payload, as_json=True))
        return

    typer.echo(_render_human(payload, service=service))
