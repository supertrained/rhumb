"""Query logging middleware for FastAPI.

Intercepts responses to instrumented routes and logs query metadata
to Supabase ``query_logs`` table via the QueryLogger.

Instrumented routes:
- /v1/search → query_type='search'
- /v1/leaderboard/{category} → query_type='list_by_category'
- /v1/services/{slug} → query_type='score_lookup'

WU 3.5: Usage Analytics Instrumentation.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Dict, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from services.query_logger import extract_agent_id, query_logger

# Route patterns to instrument
# Each entry: (compiled regex, query_type, extractor function)
# Extractor returns (query_text, query_params)

SEARCH_PATTERN = re.compile(r"^/v1/search$")
LEADERBOARD_PATTERN = re.compile(r"^/v1/leaderboard/([^/]+)$")
SERVICE_PATTERN = re.compile(r"^/v1/services/([^/]+)$")


def _extract_search(request: Request, match: re.Match) -> Tuple[str, Dict[str, Any]]:
    """Extract query metadata from search requests."""
    q = request.query_params.get("q", "")
    limit = request.query_params.get("limit", "10")
    category = request.query_params.get("category")
    params: Dict[str, Any] = {"query": q, "limit": int(limit)}
    if category:
        params["category"] = category
    return q, params


def _extract_leaderboard(request: Request, match: re.Match) -> Tuple[str, Dict[str, Any]]:
    """Extract query metadata from leaderboard requests."""
    category = match.group(1)
    limit = request.query_params.get("limit", "10")
    sort = request.query_params.get("sort")
    params: Dict[str, Any] = {"category": category, "limit": int(limit)}
    if sort:
        params["sort"] = sort
    return category, params


def _extract_service(request: Request, match: re.Match) -> Tuple[str, Dict[str, Any]]:
    """Extract query metadata from service detail requests."""
    slug = match.group(1)
    return slug, {"slug": slug}


# Route definitions
INSTRUMENTED_ROUTES = [
    (SEARCH_PATTERN, "search", _extract_search),
    (LEADERBOARD_PATTERN, "list_by_category", _extract_leaderboard),
    (SERVICE_PATTERN, "score_lookup", _extract_service),
]


def _get_result_count_from_body(body: bytes, query_type: str) -> Optional[int]:
    """Try to extract result count from JSON response body."""
    try:
        data = json.loads(body)
        inner = data.get("data", {})

        if query_type == "search":
            results = inner.get("results", [])
            return len(results) if isinstance(results, list) else None
        elif query_type == "list_by_category":
            return inner.get("count")
        elif query_type == "score_lookup":
            # Service detail: 1 if data present, 0 if empty/null
            if inner and inner.get("slug"):
                return 1
            return 0
    except Exception:
        pass
    return None


def _get_result_status(status_code: int, body: bytes, query_type: str) -> str:
    """Determine result status from HTTP status and body."""
    if status_code >= 500:
        return "error"
    if status_code == 404:
        return "not_found"
    if status_code == 429:
        return "rate_limit"
    if status_code >= 400:
        return "error"

    # Check for logical not-found in 200 responses
    try:
        data = json.loads(body)
        if data.get("error"):
            if "not found" in str(data["error"]).lower():
                return "not_found"
            return "error"
    except Exception:
        pass

    return "success"


class QueryLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs instrumented API queries to query_logs table."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Intercept request/response cycle for instrumented routes."""
        # Only instrument GET requests
        if request.method != "GET":
            return await call_next(request)

        # Check if this route is instrumented
        path = request.url.path
        matched = None
        for pattern, query_type, extractor in INSTRUMENTED_ROUTES:
            match = pattern.match(path)
            if match:
                matched = (query_type, extractor, match)
                break

        if matched is None:
            return await call_next(request)

        query_type, extractor, match = matched
        start_time = time.monotonic()

        # Extract request metadata
        query_text, query_params = extractor(request, match)
        user_agent_str = request.headers.get("user-agent")
        agent_id = extract_agent_id(user_agent_str, dict(request.headers))

        # Execute the actual request
        response = await call_next(request)

        # Capture response body for result counting
        # We need to read the body and reconstruct the response
        body_bytes = b""
        async for chunk in response.body_iterator:
            body_bytes += chunk if isinstance(chunk, bytes) else chunk.encode()

        latency_ms = int((time.monotonic() - start_time) * 1000)
        result_count = _get_result_count_from_body(body_bytes, query_type)
        result_status = _get_result_status(response.status_code, body_bytes, query_type)

        # Log the query (non-blocking, fire-and-forget)
        try:
            await query_logger.log(
                source="web",
                query_type=query_type,
                query_text=query_text,
                query_params=query_params,
                agent_id=agent_id,
                user_agent=user_agent_str,
                result_count=result_count,
                result_status=result_status,
                latency_ms=latency_ms,
            )
        except Exception:
            pass  # Never let logging break the endpoint

        # Return reconstructed response with original headers
        return Response(
            content=body_bytes,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
