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


async def supabase_count(path: str) -> int:
    """Count rows matching a PostgREST filter without fetching all data.

    Uses ``Prefer: count=exact`` with a zero-row range to read the total
    from the ``Content-Range`` response header.

    Args:
        path: PostgREST filter path, e.g. ``credit_ledger?org_id=eq.org_1``
    """
    url = f"{settings.supabase_url}/rest/v1/{path}"
    headers = {
        **_get_headers(),
        "Prefer": "count=exact",
        "Range-Unit": "items",
        "Range": "0-0",
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=10.0)
            if resp.status_code not in (200, 206):
                return 0
            content_range = resp.headers.get("content-range", "")
            # Formats: "0-0/142" or "*/0"
            if "/" in content_range:
                total_str = content_range.split("/")[-1]
                if total_str != "*":
                    return int(total_str)
            return 0
    except Exception:
        return 0


async def supabase_patch(path: str, payload: dict[str, Any]) -> Any | None:
    """PATCH (update) rows via Supabase REST API (PostgREST).

    Args:
        path: PostgREST path with filters, e.g.
              ``org_credits?org_id=eq.org_1``
        payload: Fields to update.

    Returns:
        Parsed JSON response (list of updated rows) or None on error.
    """
    url = f"{settings.supabase_url}/rest/v1/{path}"
    headers = {
        **_get_headers(),
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(url, headers=headers, json=payload, timeout=10.0)
            if resp.status_code not in (200, 201, 204):
                return None
            if resp.status_code == 204:
                return []
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
