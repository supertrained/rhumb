"""Admin route authentication dependency.

Gates admin/mutation endpoints behind a shared secret.
Checks the X-Rhumb-Admin-Key header against RHUMB_ADMIN_SECRET.
If RHUMB_ADMIN_SECRET is not configured, all admin routes are denied
(fail-closed, not fail-open).
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from config import settings


async def require_admin_key(
    x_rhumb_admin_key: str = Header(default=""),
) -> None:
    """Dependency that enforces admin authentication on protected routes."""
    secret = settings.rhumb_admin_secret
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Admin API is not configured (RHUMB_ADMIN_SECRET not set).",
        )
    if not x_rhumb_admin_key or x_rhumb_admin_key != secret:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing admin key.",
        )
