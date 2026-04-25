#!/usr/bin/env python3
"""DC90 Month 1 measurement guardrails.

This helper keeps the 15-query x 5-surface scorecard honest before and after
Beacon's manual/UI capture pass. It intentionally does not call GPT-4,
Claude, Perplexity, Gemini, or Copilot APIs; those rows require raw artifacts
from the exact Month 0-comparable answer surfaces.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MONTH_DIR = ROOT / "docs" / "dc90-measurement" / "month1-2026-04"
SCORECARD = MONTH_DIR / "scorecard.csv"
SCHEMA = MONTH_DIR / "scorecard.schema.json"
PREFLIGHT_DIR = MONTH_DIR / "preflight"

EXPECTED_QUERY_IDS = {f"Q{i}" for i in range(1, 16)}
EXPECTED_SURFACES = {"GPT-4", "Claude", "Perplexity", "Gemini", "Copilot"}
PREFLIGHT_URLS = {
    "llms": "https://rhumb.dev/llms.txt",
    "llms_full": "https://rhumb.dev/llms-full.txt",
    "sitemap": "https://rhumb.dev/sitemap.xml",
    "agent_capabilities": "https://rhumb.dev/.well-known/agent-capabilities.json",
    "logo_svg": "https://rhumb.dev/logo.svg",
    "logo_png": "https://rhumb.dev/logo.png",
    "mcp_registry_latest": (
        "https://registry.modelcontextprotocol.io/v0.1/servers/"
        "io.github.supertrained%2Frhumb-mcp/versions/latest"
    ),
    "callable_providers": "https://api.rhumb.dev/v2/providers?status=callable&limit=200",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_scorecard() -> list[dict[str, str]]:
    with SCORECARD.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _allowed_values(schema: dict[str, Any], column: str) -> set[str] | None:
    spec = schema.get("properties", {}).get(column, {})
    values = spec.get("enum")
    if values is None:
        return None
    return {str(value) for value in values}


def validate_scorecard() -> tuple[dict[str, Any], list[str]]:
    schema = _load_json(SCHEMA)
    rows = _load_scorecard()
    errors: list[str] = []
    required = list(schema.get("required", []))

    if len(rows) != 75:
        errors.append(f"expected 75 scorecard rows, found {len(rows)}")

    header = list(rows[0].keys()) if rows else []
    missing_columns = [column for column in required if column not in header]
    if missing_columns:
        errors.append(f"missing required columns: {', '.join(missing_columns)}")

    seen: set[tuple[str, str]] = set()
    query_counter: Counter[str] = Counter()
    surface_counter: Counter[str] = Counter()
    rows_with_artifacts = 0
    rhumb_mentions = 0
    rhumb_mentions_reviewed = 0

    for index, row in enumerate(rows, start=2):
        for column in required:
            value = row.get(column, "")
            if value is None:
                errors.append(f"line {index}: {column} is missing")
                continue
            allowed = _allowed_values(schema, column)
            if allowed is not None and value not in allowed:
                errors.append(
                    f"line {index}: {column}={value!r} is not one of {sorted(allowed)}"
                )

        query_id = row.get("query_id", "")
        surface = row.get("surface", "")
        key = (query_id, surface)
        if key in seen:
            errors.append(f"line {index}: duplicate query/surface row {query_id}/{surface}")
        seen.add(key)
        query_counter[query_id] += 1
        surface_counter[surface] += 1

        artifact_path = row.get("artifact_path", "")
        if "YYYYMMDDTHHMMSSZ" not in artifact_path:
            artifact = ROOT / artifact_path
            if artifact.exists():
                rows_with_artifacts += 1
            else:
                errors.append(f"line {index}: artifact does not exist: {artifact_path}")

        if row.get("rhumb_mentioned") == "yes":
            rhumb_mentions += 1
            if row.get("keel_review_status") == "reviewed":
                rhumb_mentions_reviewed += 1

    for query_id in sorted(EXPECTED_QUERY_IDS):
        if query_counter[query_id] != 5:
            errors.append(f"{query_id} should have 5 surface rows, found {query_counter[query_id]}")
    for surface in sorted(EXPECTED_SURFACES):
        if surface_counter[surface] != 15:
            errors.append(f"{surface} should have 15 query rows, found {surface_counter[surface]}")

    completed_rows = sum(1 for row in rows if row.get("run_at_utc") not in {"", "pending"})
    pending_rows = len(rows) - completed_rows
    rollup = {
        "rows_total": len(rows),
        "rows_completed": completed_rows,
        "rows_pending": pending_rows,
        "rows_with_existing_artifacts": rows_with_artifacts,
        "rhumb_mentions": rhumb_mentions,
        "rhumb_mentions_reviewed_by_keel": rhumb_mentions_reviewed,
        "query_rows": dict(sorted(query_counter.items())),
        "surface_rows": dict(sorted(surface_counter.items())),
    }
    return rollup, errors


def _fetch(url: str, *, timeout: float) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    request = urllib.request.Request(url, headers={"User-Agent": "rhumb-dc90-measurement/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(600_000)
            return {
                "ok": 200 <= response.status < 300,
                "status": response.status,
                "content_type": response.headers.get("content-type", ""),
                "bytes_read": len(body),
                "elapsed_ms": round((datetime.now(timezone.utc) - started).total_seconds() * 1000),
                "body_sample": body[:240].decode("utf-8", errors="replace"),
                "parsed": _parse_json_maybe(body, response.headers.get("content-type", "")),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read(240)
        return {
            "ok": False,
            "status": exc.code,
            "content_type": exc.headers.get("content-type", "") if exc.headers else "",
            "bytes_read": len(body),
            "elapsed_ms": round((datetime.now(timezone.utc) - started).total_seconds() * 1000),
            "error": body.decode("utf-8", errors="replace"),
        }
    except Exception as exc:  # noqa: BLE001 - preflight should report network failures directly.
        return {
            "ok": False,
            "elapsed_ms": round((datetime.now(timezone.utc) - started).total_seconds() * 1000),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _parse_json_maybe(body: bytes, content_type: str) -> Any | None:
    if "json" not in content_type.lower():
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _dig_path(value: Any, path: tuple[str | int, ...]) -> Any:
    for key in path:
        if isinstance(key, int) and isinstance(value, list) and len(value) > key:
            value = value[key]
        elif isinstance(key, str) and isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    return value


def _extract_callable_count(parsed: Any) -> int | None:
    if isinstance(parsed, list):
        return len(parsed)
    if not isinstance(parsed, dict):
        return None
    for key_path in (
        ("providers",),
        ("data", "providers"),
        ("items",),
        ("data", "items"),
        ("results",),
        ("data", "results"),
    ):
        value = _dig_path(parsed, key_path)
        if isinstance(value, list):
            return len(value)
    for key_path in (("count",), ("total",), ("data", "count"), ("data", "total")):
        count = _dig_path(parsed, key_path)
        if isinstance(count, (int, float)):
            return int(count)
    return None


def _extract_registry_version(parsed: Any) -> str | None:
    if not isinstance(parsed, dict):
        return None
    for key_path in (
        ("version",),
        ("package", "version"),
        ("packages", 0, "version"),
        ("server", "version"),
        ("server", "package", "version"),
        ("server", "packages", 0, "version"),
    ):
        value = _dig_path(parsed, key_path)
        if isinstance(value, str):
            return value
    return None


def run_preflight(timeout: float) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rollup, validation_errors = validate_scorecard()
    checks = {name: _fetch(url, timeout=timeout) for name, url in PREFLIGHT_URLS.items()}

    callable_count = _extract_callable_count(checks["callable_providers"].get("parsed"))
    registry_version = _extract_registry_version(checks["mcp_registry_latest"].get("parsed"))
    passed = all(check.get("ok") for check in checks.values()) and not validation_errors
    registry_ok = registry_version in {None, "0.8.2"}
    if not registry_ok:
        passed = False
    callable_count_matches_public_truth = callable_count == 28
    if not callable_count_matches_public_truth:
        passed = False

    artifact = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "purpose": "DC90 Month 1 pre-run drift check; not a 75-row answer-surface capture.",
        "scorecard_rollup": rollup,
        "scorecard_validation_errors": validation_errors,
        "public_checks": checks,
        "derived": {
            "callable_provider_count": callable_count,
            "callable_count_matches_public_truth_28": callable_count_matches_public_truth,
            "mcp_registry_version": registry_version,
            "mcp_registry_expected_version": "0.8.2",
            "mcp_registry_version_ok": registry_ok,
            "all_public_urls_ok": all(check.get("ok") for check in checks.values()),
            "preflight_passed": passed,
        },
        "boundary": (
            "Rows remain pending until raw artifacts are captured from GPT-4, Claude, "
            "Perplexity, Gemini, and Copilot surfaces and Keel reviews Rhumb-mentioned rows."
        ),
    }
    PREFLIGHT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PREFLIGHT_DIR / f"preflight-{timestamp}.json"
    output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact["artifact_path"] = str(output_path.relative_to(ROOT))
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true", help="validate scorecard shape only")
    parser.add_argument("--preflight", action="store_true", help="run public URL drift checks")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout for each preflight URL")
    args = parser.parse_args()

    if not args.validate and not args.preflight:
        parser.error("choose --validate and/or --preflight")

    if args.validate:
        rollup, errors = validate_scorecard()
        print(json.dumps({"scorecard_rollup": rollup, "errors": errors}, indent=2, sort_keys=True))
        if errors:
            return 1

    if args.preflight:
        artifact = run_preflight(timeout=args.timeout)
        print(json.dumps({"artifact_path": artifact["artifact_path"], "derived": artifact["derived"]}, indent=2, sort_keys=True))
        if not artifact["derived"]["preflight_passed"]:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
