"""Shared Supabase REST API helper for route handlers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from config import settings
from services.cache import TTLCache, build_cache_key
from services.circuit_breaker import CircuitBreaker, CircuitState, ServiceDegradedError
from services.supabase_access import (
    get_app_supabase_headers,
    get_score_publisher_supabase_headers,
    get_score_reader_supabase_headers,
    is_score_truth_target,
)
_SUPABASE_RESOLUTION = "Supabase is temporarily unavailable. Check /status"
_SUPABASE_TIMEOUT_SECONDS = 10.0
_SUPABASE_CACHE = TTLCache(default_ttl=60.0, max_size=1000)
_SUPABASE_BREAKER = CircuitBreaker(
    service_name="Supabase",
    failure_threshold=5,
    recovery_timeout=30.0,
    success_threshold=2,
    resolution=_SUPABASE_RESOLUTION,
)


class _SupabaseRequestError(RuntimeError):
    """Internal error for a failed Supabase HTTP request."""

    def __init__(self, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(f"Supabase request failed with status={status_code}")


class SupabaseWriteUnavailable(RuntimeError):
    """Raised when a required Supabase write cannot be durably recorded."""


def _build_url(path: str) -> str:
    return f"{settings.supabase_url}/rest/v1/{path}"


def _get_read_headers(path: str) -> dict[str, str]:
    """Select the correct read credential surface for a Supabase path."""
    if is_score_truth_target(path):
        return get_score_reader_supabase_headers()
    return get_app_supabase_headers()


def _generic_write_allowed(target: str) -> bool:
    """Generic runtime/control-plane helpers must not mutate score truth."""
    return not is_score_truth_target(target)


def _score_publisher_write_allowed(target: str) -> bool:
    """Score publisher helpers may only touch protected score-truth tables."""
    return is_score_truth_target(target)


def _count_from_response(response: httpx.Response) -> int:
    content_range = response.headers.get("content-range", "")
    if "/" in content_range:
        total_str = content_range.split("/")[-1]
        if total_str != "*":
            return int(total_str)
    return 0


async def _request(
    method: str,
    path: str,
    *,
    expected_status_codes: tuple[int, ...],
    headers: dict[str, str],
    timeout: float = _SUPABASE_TIMEOUT_SECONDS,
    payload: dict[str, Any] | None = None,
    transform: Callable[[httpx.Response], Any],
) -> Any:
    async def _operation() -> Any:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=_build_url(path),
                headers=headers,
                json=payload,
                timeout=timeout,
            )
        if response.status_code not in expected_status_codes:
            raise _SupabaseRequestError(response.status_code)
        return transform(response)

    return await _SUPABASE_BREAKER.call(_operation)


async def cached_query(
    table: str,
    query_fn: Callable[[], Awaitable[Any]],
    cache_key: str,
    ttl: float | None = None,
) -> Any | None:
    """Run a query through the TTL cache with breaker-aware fallback."""
    key = build_cache_key(table, cache_key)

    if _SUPABASE_BREAKER.state == CircuitState.OPEN:
        cached_value = _SUPABASE_CACHE.get(key)
        if cached_value is not None:
            return cached_value
        raise ServiceDegradedError(
            service_name="Supabase",
            resolution=_SUPABASE_RESOLUTION,
        )

    try:
        result = await query_fn()
    except ServiceDegradedError:
        cached_value = _SUPABASE_CACHE.get(key)
        if cached_value is not None:
            return cached_value
        raise

    if result is not None:
        _SUPABASE_CACHE.set(key, result, ttl=ttl)
    return result


def reset_supabase_resilience() -> None:
    """Reset the shared Supabase cache and circuit breaker."""
    _SUPABASE_CACHE.clear()
    _SUPABASE_BREAKER.reset()


def get_supabase_cache() -> TTLCache:
    """Return the shared Supabase cache instance."""
    return _SUPABASE_CACHE


def get_supabase_breaker() -> CircuitBreaker:
    """Return the shared Supabase circuit breaker."""
    return _SUPABASE_BREAKER


async def supabase_fetch(path: str) -> Any | None:
    """Fetch from Supabase REST API (PostgREST).

    Args:
        path: PostgREST path, e.g. 'services?select=slug,name&order=name.asc'

    Returns:
        Parsed JSON response or None on error.
    """
    try:
        return await _request(
            "GET",
            path,
            expected_status_codes=(200,),
            headers=_get_read_headers(path),
            transform=lambda response: response.json(),
        )
    except (httpx.HTTPError, _SupabaseRequestError, ValueError):
        return None


async def supabase_count(path: str) -> int:
    """Count rows matching a PostgREST filter without fetching all data.

    Uses ``Prefer: count=exact`` with a zero-row range to read the total
    from the ``Content-Range`` response header.

    Args:
        path: PostgREST filter path, e.g. ``credit_ledger?org_id=eq.org_1``
    """
    headers = {
        **_get_read_headers(path),
        "Prefer": "count=exact",
        "Range-Unit": "items",
        "Range": "0-0",
    }
    try:
        return int(
            await _request(
                "GET",
                path,
                expected_status_codes=(200, 206),
                headers=headers,
                transform=_count_from_response,
            )
        )
    except (httpx.HTTPError, _SupabaseRequestError, ValueError):
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
    if not _generic_write_allowed(path):
        return None

    headers = {
        **get_app_supabase_headers(),
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    try:
        return await _request(
            "PATCH",
            path,
            expected_status_codes=(200, 201, 204),
            headers=headers,
            payload=payload,
            transform=lambda response: [] if response.status_code == 204 else response.json(),
        )
    except (httpx.HTTPError, _SupabaseRequestError, ValueError):
        return None


async def supabase_insert(table: str, payload: dict[str, Any]) -> bool:
    """Insert a row into a Supabase table via PostgREST."""
    if not _generic_write_allowed(table):
        return False

    headers = {
        **get_app_supabase_headers(),
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    try:
        await _request(
            "POST",
            table,
            expected_status_codes=(200, 201, 204),
            headers=headers,
            payload=payload,
            transform=lambda response: response.status_code in (200, 201, 204),
        )
        return True
    except (httpx.HTTPError, _SupabaseRequestError, ValueError):
        return False


async def supabase_insert_required(table: str, payload: dict[str, Any]) -> None:
    """Insert a row and raise if the durable write cannot be recorded."""
    if not await supabase_insert(table, payload):
        raise SupabaseWriteUnavailable(f"Required insert failed for table={table}")


async def supabase_patch_required(path: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Patch rows and raise if the durable write cannot be recorded."""
    result = await supabase_patch(path, payload)
    if result is None:
        raise SupabaseWriteUnavailable(f"Required patch failed for path={path}")
    return result


async def supabase_insert_returning(
    table: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """Insert a row and return the created record (with server-generated fields).

    Uses ``Prefer: return=representation`` so PostgREST sends back the full row
    including any default/generated columns (e.g. ``id``, ``created_at``).

    Returns the first created row dict, or None on error.
    """
    if not _generic_write_allowed(table):
        return None

    headers = {
        **get_app_supabase_headers(),
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    try:
        data = await _request(
            "POST",
            table,
            expected_status_codes=(200, 201),
            headers=headers,
            payload=payload,
            transform=lambda response: response.json(),
        )
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return None
    except (httpx.HTTPError, _SupabaseRequestError, ValueError):
        return None


async def supabase_score_patch(path: str, payload: dict[str, Any]) -> Any | None:
    """Patch score-truth rows via the publisher-only credential surface."""
    if not _score_publisher_write_allowed(path):
        return None

    headers = {
        **get_score_publisher_supabase_headers(),
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    try:
        return await _request(
            "PATCH",
            path,
            expected_status_codes=(200, 201, 204),
            headers=headers,
            payload=payload,
            transform=lambda response: [] if response.status_code == 204 else response.json(),
        )
    except (httpx.HTTPError, _SupabaseRequestError, ValueError):
        return None


async def supabase_score_insert(table: str, payload: dict[str, Any]) -> bool:
    """Insert a score-truth row via the publisher-only credential surface."""
    if not _score_publisher_write_allowed(table):
        return False

    headers = {
        **get_score_publisher_supabase_headers(),
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    try:
        await _request(
            "POST",
            table,
            expected_status_codes=(200, 201, 204),
            headers=headers,
            payload=payload,
            transform=lambda response: response.status_code in (200, 201, 204),
        )
        return True
    except (httpx.HTTPError, _SupabaseRequestError, ValueError):
        return False


async def supabase_score_insert_returning(
    table: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """Insert a score-truth row and return the created record.

    This is the dedicated publisher-only write surface for `scores` and
    `score_audit_chain` so future score writers do not route through the
    generic app/control-plane helper path.
    """
    if not _score_publisher_write_allowed(table):
        return None

    headers = {
        **get_score_publisher_supabase_headers(),
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    try:
        data = await _request(
            "POST",
            table,
            expected_status_codes=(200, 201),
            headers=headers,
            payload=payload,
            transform=lambda response: response.json(),
        )
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return None
    except (httpx.HTTPError, _SupabaseRequestError, ValueError):
        return None


async def supabase_score_insert_required(table: str, payload: dict[str, Any]) -> None:
    """Insert a score-truth row and raise if the durable write cannot be recorded."""
    try:
        ok = await supabase_score_insert(table, payload)
    except Exception as exc:
        raise SupabaseWriteUnavailable(
            f"Required score insert failed for table={table}"
        ) from exc
    if not ok:
        raise SupabaseWriteUnavailable(f"Required score insert failed for table={table}")


async def supabase_score_patch_required(
    path: str,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Patch score-truth rows and raise if the durable write cannot be recorded."""
    try:
        result = await supabase_score_patch(path, payload)
    except Exception as exc:
        raise SupabaseWriteUnavailable(
            f"Required score patch failed for path={path}"
        ) from exc
    if result is None:
        raise SupabaseWriteUnavailable(f"Required score patch failed for path={path}")
    return result


async def supabase_score_insert_returning_required(
    table: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Insert a score-truth row, return it, and raise on failure."""
    try:
        result = await supabase_score_insert_returning(table, payload)
    except Exception as exc:
        raise SupabaseWriteUnavailable(
            f"Required score insert-returning failed for table={table}"
        ) from exc
    if result is None:
        raise SupabaseWriteUnavailable(
            f"Required score insert-returning failed for table={table}"
        )
    return result
