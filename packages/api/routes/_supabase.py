"""Shared Supabase REST API helper for route handlers."""

from typing import Any

import httpx

from config import settings

_HEADERS: dict[str, str] | None = None


def _get_headers() -> dict[str, str]:
    """Build Supabase REST API headers (cached)."""
    global _HEADERS
    if _HEADERS is None:
        _HEADERS = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
        }
    return _HEADERS


async def supabase_fetch(path: str) -> Any | None:
    """Fetch from Supabase REST API (PostgREST).

    Args:
        path: PostgREST path, e.g. 'services?select=slug,name&order=name.asc'

    Returns:
        Parsed JSON response or None on error.
    """
    url = f"{settings.supabase_url}/rest/v1/{path}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=_get_headers(), timeout=10.0)
            if resp.status_code != 200:
                return None
            return resp.json()
    except Exception:
        return None


async def supabase_insert(table: str, payload: dict[str, Any]) -> bool:
    """Insert a row into a Supabase table via PostgREST."""
    url = f"{settings.supabase_url}/rest/v1/{table}"
    headers = {
        **_get_headers(),
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
            return resp.status_code in (200, 201, 204)
    except Exception:
        return False
