"""Admin and launch-dashboard authentication dependencies.

Admin routes require ``X-Rhumb-Admin-Key`` to match ``RHUMB_ADMIN_SECRET``.
The internal launch dashboard may also accept a narrower
``X-Rhumb-Launch-Dashboard-Key`` that matches ``RHUMB_LAUNCH_DASHBOARD_KEY``.
If the required secrets are not configured, routes fail closed.
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from config import settings


def _normalize_secret(value: str | None) -> str:
    return value.strip() if value else ""


async def require_admin_key(
    x_rhumb_admin_key: str = Header(default=""),
) -> None:
    """Dependency that enforces admin authentication on protected routes."""
    secret = _normalize_secret(settings.rhumb_admin_secret)
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Admin API is not configured (RHUMB_ADMIN_SECRET not set).",
        )
    if _normalize_secret(x_rhumb_admin_key) != secret:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing admin key.",
        )


async def require_launch_dashboard_access(
    x_rhumb_admin_key: str = Header(default=""),
    x_rhumb_launch_dashboard_key: str = Header(default=""),
) -> None:
    """Allow launch dashboard reads via admin key or narrower dashboard key."""
    admin_secret = _normalize_secret(settings.rhumb_admin_secret)
    dashboard_key = _normalize_secret(settings.rhumb_launch_dashboard_key)
    admin_header = _normalize_secret(x_rhumb_admin_key)
    dashboard_header = _normalize_secret(x_rhumb_launch_dashboard_key)

    if admin_secret and admin_header == admin_secret:
        return
    if dashboard_key and dashboard_header == dashboard_key:
        return
    if not admin_secret and not dashboard_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Launch dashboard is not configured "
                "(RHUMB_ADMIN_SECRET / RHUMB_LAUNCH_DASHBOARD_KEY not set)."
            ),
        )
    raise HTTPException(
        status_code=401,
        detail="Invalid or missing launch dashboard key.",
    )
