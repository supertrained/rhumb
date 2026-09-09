"""Published failure-mode catalog and empty-state honesty.

An empty ``failure_modes`` list is a coverage gap, not a clean bill of health.
When the live table has no rows for a catalogued major service, fall back to
the published research catalog so dogfood discovery stays honest.

The catalog file is loaded from the API package first so Railway/Docker
images that only copy ``packages/api`` still work. A missing or unreadable
catalog must never 500 public ``/failures`` — that is ``coverage: unresearched``.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()
CATALOG_CANDIDATES = (
    _HERE.parents[1] / "failure-mode-catalog.json",
    _HERE.parents[2] / "shared" / "failure-mode-catalog.json",
)
CATALOG_PATH = CATALOG_CANDIDATES[0]

UNRESEARCHED_HONESTY = (
    "No failure modes have been captured for this service yet. "
    "An empty list is a coverage gap, not a clean bill of health."
)
REPORTED_HONESTY = "These are active captured failure modes, not a complete incident history."
CATALOG_HONESTY = (
    "These failure modes come from Rhumb's published research catalog "
    "because the live failure_modes table has no rows for this service yet. "
    "This is captured research, not a claim that the database is fully populated."
)


def _parse_catalog_payload(payload: Any) -> dict[str, list[dict[str, Any]]]:
    services = payload.get("services") if isinstance(payload, dict) else None
    if not isinstance(services, dict):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for slug, rows in services.items():
        if isinstance(rows, list):
            out[str(slug).strip().lower()] = [row for row in rows if isinstance(row, dict)]
    return out


@lru_cache(maxsize=1)
def load_failure_mode_catalog() -> dict[str, list[dict[str, Any]]]:
    for path in CATALOG_CANDIDATES:
        try:
            if not path.is_file():
                continue
            return _parse_catalog_payload(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Failed to load failure-mode catalog from %s: %s", path, exc)
    logger.warning("No readable failure-mode catalog found; empty lists stay unresearched")
    return {}


def catalog_failures(slug: str) -> list[dict[str, Any]]:
    try:
        return list(load_failure_mode_catalog().get(str(slug or "").strip().lower(), []))
    except Exception:
        logger.exception("failure-mode catalog lookup failed for %s", slug)
        return []


def resolve_failure_modes(
    slug: str, stored: list[dict[str, Any]] | None
) -> tuple[list[dict[str, Any]], str, str]:
    """Return (rows, coverage, honesty). Prefer live rows; else catalog; else unresearched."""
    try:
        if isinstance(stored, list) and stored:
            return [row for row in stored if isinstance(row, dict)], "reported", REPORTED_HONESTY
        seeded = catalog_failures(slug)
        if seeded:
            return seeded, "reported", CATALOG_HONESTY
    except Exception:
        logger.exception("resolve_failure_modes failed for %s; using unresearched empty list", slug)
    return [], "unresearched", UNRESEARCHED_HONESTY
