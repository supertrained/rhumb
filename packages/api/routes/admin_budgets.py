"""Admin endpoint for monitoring upstream provider budgets.

Exposes our free-tier API credit usage so we can see exposure
before it becomes a problem. Protected by admin key.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from routes.admin_auth import require_admin_key
from services.service_slugs import normalize_proxy_slug, public_service_slug
from services.upstream_budget import get_all_provider_budgets, get_provider_usage

_WARN_THRESHOLD = 0.80
_CRITICAL_THRESHOLD = 0.95

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def _public_budget_provider(provider: str | None) -> str:
    return public_service_slug(provider) or str(provider or "").strip().lower()


def _runtime_budget_provider(provider: str) -> str:
    public_provider = _public_budget_provider(provider)
    return normalize_proxy_slug(public_provider) or public_provider


def _budget_status(used: int, limit: int | None) -> tuple[float, str]:
    if limit is None:
        return 0.0, "untracked"
    if limit == 0:
        return 0.0, "pay_per_use"

    percentage = used / limit if limit > 0 else 0.0
    if percentage >= 1.0:
        return round(percentage, 4), "exhausted"
    if percentage >= _CRITICAL_THRESHOLD:
        return round(percentage, 4), "critical"
    if percentage >= _WARN_THRESHOLD:
        return round(percentage, 4), "warning"
    return round(percentage, 4), "ok"


def _public_budget_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        provider = _public_budget_provider(row.get("provider"))
        if not provider:
            continue

        entry = merged.setdefault(
            provider,
            {
                "provider": provider,
                "used": 0,
                "limit": None,
                "unit": "unknown",
                "reset": "unknown",
                "durable": True,
                "reason": "",
            },
        )
        entry["used"] = int(entry["used"]) + int(row.get("used") or 0)

        row_limit = row.get("limit")
        current_limit = entry.get("limit")
        if row_limit is not None:
            row_limit = int(row_limit)
            if current_limit is None or (int(current_limit) == 0 and row_limit > 0):
                entry["limit"] = row_limit
            elif int(current_limit) > 0 and row_limit > 0:
                entry["limit"] = max(int(current_limit), row_limit)
            elif int(current_limit) == 0 and row_limit == 0:
                entry["limit"] = 0

        unit = str(row.get("unit") or "").strip()
        if unit and unit != "unknown":
            entry["unit"] = unit

        reset = str(row.get("reset") or "").strip()
        if reset and reset != "unknown":
            entry["reset"] = reset

        entry["durable"] = bool(entry["durable"]) and bool(row.get("durable", False))

        reasons = [
            part
            for part in [str(entry.get("reason") or "").strip(), str(row.get("reason") or "").strip()]
            if part
        ]
        entry["reason"] = "; ".join(dict.fromkeys(reasons))

    public_rows: list[dict[str, Any]] = []
    for provider in sorted(merged):
        row = merged[provider]
        percentage, status = _budget_status(int(row["used"]), row.get("limit"))
        public_rows.append(
            {
                **row,
                "percentage": percentage,
                "status": status,
            }
        )
    return public_rows


@router.get("/upstream-budgets", dependencies=[Depends(require_admin_key)])
async def list_upstream_budgets() -> dict:
    """Return budget status for all managed providers.

    Statuses: ok, warning (>80%), critical (>95%), exhausted (100%),
    pay_per_use (no free tier), untracked.
    """
    budgets = _public_budget_rows(await get_all_provider_budgets())
    exhausted = [b for b in budgets if b["status"] == "exhausted"]
    critical = [b for b in budgets if b["status"] == "critical"]
    warning = [b for b in budgets if b["status"] == "warning"]

    return {
        "data": budgets,
        "summary": {
            "total_providers": len(budgets),
            "exhausted": len(exhausted),
            "critical": len(critical),
            "warning": len(warning),
            "exhausted_providers": [b["provider"] for b in exhausted],
            "critical_providers": [b["provider"] for b in critical],
        },
        "kill_switches": {
            "info": "Set these env vars on Railway to control execution",
            "MANAGED_EXECUTION_ENABLED": "Set to 'false' to block ALL execution (nuclear option)",
            "MANAGED_ONLY_KILL": "Set to 'true' to block managed execution only (allows BYOK)",
        },
    }


@router.get("/upstream-budgets/{provider}", dependencies=[Depends(require_admin_key)])
async def get_provider_budget(provider: str) -> dict:
    """Return budget status for a specific provider."""
    budget = await get_provider_usage(_runtime_budget_provider(provider))
    public_rows = _public_budget_rows([budget])
    return {"data": public_rows[0] if public_rows else budget}
