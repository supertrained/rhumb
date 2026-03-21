"""Admin endpoint for monitoring upstream provider budgets.

Exposes our free-tier API credit usage so we can see exposure
before it becomes a problem. Protected by admin key.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from routes.admin_auth import require_admin_key
from services.upstream_budget import get_all_provider_budgets, get_provider_usage

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/upstream-budgets", dependencies=[Depends(require_admin_key)])
async def list_upstream_budgets() -> dict:
    """Return budget status for all managed providers.

    Statuses: ok, warning (>80%), critical (>95%), exhausted (100%),
    pay_per_use (no free tier), untracked.
    """
    budgets = get_all_provider_budgets()
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
    return {"data": get_provider_usage(provider)}
