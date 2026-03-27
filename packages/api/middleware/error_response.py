"""Standardized error response middleware.

Wraps all HTTPException and unhandled errors with a machine-actionable
envelope containing:
  - request_id: unique UUID for this request (for correlation)
  - error: the HTTP error type
  - detail: human/agent-readable description
  - resolution: actionable next step for the caller
  - status: HTTP status code

This makes every API error response agent-parseable without changing
any existing `raise HTTPException(...)` call sites.
"""

import logging
import uuid

from cors import build_cors_headers
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# Maps status codes to default resolution hints.
# Route-specific HTTPExceptions can override by passing
# detail as a dict: {"message": "...", "resolution": "..."}
_RESOLUTION_MAP: dict[int, str] = {
    400: "Check the request parameters and try again.",
    401: "Provide a valid API key via X-Rhumb-Key header, or authenticate via OAuth.",
    402: "Payment required. Fund your account at https://rhumb.dev/dashboard or use x402.",
    403: "You don't have access to this resource. Check your agent's service grants.",
    404: "The requested resource was not found. Verify the URL or identifier.",
    405: "This HTTP method is not allowed on this endpoint.",
    409: "Resource conflict. The resource may already exist or be in an incompatible state.",
    422: "Request body validation failed. Check field types and required parameters.",
    429: "Rate limit exceeded. Back off and retry after the Retry-After interval.",
    500: "Internal server error. If this persists, contact team@supertrained.ai.",
    502: "Upstream service error. The proxied API returned an unexpected response.",
    503: "Service temporarily unavailable. Retry with exponential backoff.",
}


def _build_error_body(
    status_code: int,
    detail: str | dict | None,
    request_id: str,
) -> dict:
    """Build the standardized error response body."""
    # Allow routes to pass structured detail with custom resolution
    if isinstance(detail, dict):
        message = detail.get("message", detail.get("detail", str(detail)))
        resolution = detail.get("resolution", _RESOLUTION_MAP.get(status_code, ""))
    else:
        message = detail or "An error occurred."
        resolution = _RESOLUTION_MAP.get(status_code, "")

    # Map status code to a short error type
    error_type = {
        400: "bad_request",
        401: "unauthorized",
        402: "payment_required",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        422: "validation_error",
        429: "rate_limited",
        500: "internal_error",
        502: "bad_gateway",
        503: "service_unavailable",
    }.get(status_code, f"error_{status_code}")

    return {
        "error": error_type,
        "detail": message,
        "resolution": resolution,
        "request_id": request_id,
        "status": status_code,
    }


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handle all HTTPExceptions with standardized error envelope."""
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    body = _build_error_body(exc.status_code, exc.detail, request_id)
    headers = {"X-Request-ID": request_id, **build_cors_headers(request.headers.get("origin"))}

    return JSONResponse(
        status_code=exc.status_code,
        content=body,
        headers=headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors with standardized envelope."""
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    errors = exc.errors()

    body = _build_error_body(422, None, request_id)
    body["detail"] = "Request validation failed."
    body["validation_errors"] = [
        {
            "field": " → ".join(str(loc) for loc in e.get("loc", [])),
            "message": e.get("msg", ""),
            "type": e.get("type", ""),
        }
        for e in errors
    ]
    body["resolution"] = "Fix the validation errors listed above and retry."
    headers = {"X-Request-ID": request_id, **build_cors_headers(request.headers.get("origin"))}

    return JSONResponse(
        status_code=422,
        content=body,
        headers=headers,
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all for unhandled exceptions — never leak stack traces."""
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    logger.exception("Unhandled exception [request_id=%s]", request_id)

    body = _build_error_body(500, "An unexpected error occurred.", request_id)
    headers = {"X-Request-ID": request_id, **build_cors_headers(request.headers.get("origin"))}

    return JSONResponse(
        status_code=500,
        content=body,
        headers=headers,
    )
