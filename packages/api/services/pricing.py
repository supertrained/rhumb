"""Shared pricing catalog loader for API responses."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

PRICING_PATH = Path(__file__).resolve().parents[2] / "shared" / "pricing.json"


@lru_cache(maxsize=1)
def get_pricing_catalog() -> dict[str, Any]:
    """Return the current pricing contract from the shared catalog."""
    with PRICING_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)
