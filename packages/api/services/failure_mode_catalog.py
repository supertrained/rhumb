"""Published failure-mode catalog and empty-state honesty.

An empty ``failure_modes`` list is a coverage gap, not a clean bill of health.
When the live table has no rows for a catalogued major service, fall back to
the published research catalog so dogfood discovery stays honest.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).resolve().parents[2] / "shared" / "failure-mode-catalog.json"

UNRESEARCHED_HONESTY = (
    "No failure modes have been captured for this service yet. "
    "An empty list is a coverage gap, not a clean bill of health."
)
REPORTED_HONESTY = (
    "These are active captured failure modes, not a complete incident history."
)
CATALOG_HONESTY = (
    "These failure modes come from Rhumb's published research catalog "
    "because the live failure_modes table has no rows for this service yet. "
    "This is captured research, not a claim that the database is fully populated."
)


@lru_cache(maxsize=1)
def load_failure_mode_catalog() -> dict[str, list[dict[str, Any]]]:
    payload = json.loads(CATALOG_PATH.read_text())
    services = payload.get("services") or {}
    if not isinstance(services, dict):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for slug, rows in services.items():
        if isinstance(rows, list):
            out[str(slug).strip().lower()] = rows
    return out


def catalog_failures(slug: str) -> list[dict[str, Any]]:
    return list(load_failure_mode_catalog().get(str(slug or "").strip().lower(), []))


def resolve_failure_modes(
    slug: str, stored: list[dict[str, Any]] | None
) -> tuple[list[dict[str, Any]], str, str]:
    """Return (rows, coverage, honesty). Prefer live rows; else catalog; else unresearched."""
    if stored:
        return stored, "reported", REPORTED_HONESTY
    seeded = catalog_failures(slug)
    if seeded:
        return seeded, "reported", CATALOG_HONESTY
    return [], "unresearched", UNRESEARCHED_HONESTY
