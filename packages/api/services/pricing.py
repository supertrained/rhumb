"""Shared pricing catalog loader for API responses."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

PRICING_CANDIDATES = [
    # Canonical source in the monorepo.
    Path(__file__).resolve().parents[2] / "shared" / "pricing.json",
    # Bundled fallback for API-only Docker builds that do not copy sibling packages.
    Path(__file__).resolve().parents[1] / "pricing.json",
]


@lru_cache(maxsize=1)
def get_pricing_catalog() -> dict[str, Any]:
    """Return the current pricing contract from the shared catalog."""
    for pricing_path in PRICING_CANDIDATES:
        if pricing_path.exists():
            with pricing_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)

    searched = ", ".join(str(path) for path in PRICING_CANDIDATES)
    raise FileNotFoundError(f"Pricing catalog not found. Searched: {searched}")
