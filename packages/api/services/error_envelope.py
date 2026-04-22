"""Canonical error envelope for Resolve v2.

Every error response uses the same envelope across all three layers.
This module defines the error code registry, envelope construction,
and FastAPI exception handlers that produce spec-compliant errors.

Spec reference: RESOLVE-PRODUCT-SPEC-2026-03-30, Section 1.5
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ── Error Code Registry ──


class ErrorCategory(str, Enum):
    CLIENT = "client"
    AUTH = "auth"
    POLICY = "policy"
    PROVIDER = "provider"
    ROUTING = "routing"
    RECIPE = "recipe"
    INTERNAL = "internal"
    INFRA = "infra"


@dataclass(frozen=True)
class ErrorCodeDef:
    """Definition of a canonical error code."""

    code: str
    category: ErrorCategory
    http_status: int
    retryable: bool
    description: str
    default_retry_after_ms: int | None = None


# The canonical error code registry from the Resolve spec
ERROR_CODES: dict[str, ErrorCodeDef] = {
    "INVALID_PARAMETERS": ErrorCodeDef(
        code="INVALID_PARAMETERS",
        category=ErrorCategory.CLIENT,
        http_status=400,
        retryable=False,
        description="Schema validation failed",
    ),
    "MISSING_REQUIRED_FIELD": ErrorCodeDef(
        code="MISSING_REQUIRED_FIELD",
        category=ErrorCategory.CLIENT,
        http_status=400,
        retryable=False,
        description="Required parameter absent",
    ),
    "CAPABILITY_NOT_FOUND": ErrorCodeDef(
        code="CAPABILITY_NOT_FOUND",
        category=ErrorCategory.CLIENT,
        http_status=404,
        retryable=False,
        description="Capability ID does not exist",
    ),
    "PROVIDER_NOT_FOUND": ErrorCodeDef(
        code="PROVIDER_NOT_FOUND",
        category=ErrorCategory.CLIENT,
        http_status=404,
        retryable=False,
        description="Provider ID does not exist",
    ),
    "RECIPE_NOT_FOUND": ErrorCodeDef(
        code="RECIPE_NOT_FOUND",
        category=ErrorCategory.CLIENT,
        http_status=404,
        retryable=False,
        description="Recipe ID does not exist",
    ),
    "RECEIPT_NOT_FOUND": ErrorCodeDef(
        code="RECEIPT_NOT_FOUND",
        category=ErrorCategory.CLIENT,
        http_status=404,
        retryable=False,
        description="Receipt ID does not exist",
    ),
    "EXPLANATION_NOT_FOUND": ErrorCodeDef(
        code="EXPLANATION_NOT_FOUND",
        category=ErrorCategory.CLIENT,
        http_status=404,
        retryable=False,
        description="Explanation ID does not exist",
    ),
    "CREDENTIAL_INVALID": ErrorCodeDef(
        code="CREDENTIAL_INVALID",
        category=ErrorCategory.AUTH,
        http_status=401,
        retryable=False,
        description="API key invalid or expired",
    ),
    "CREDENTIAL_MISSING": ErrorCodeDef(
        code="CREDENTIAL_MISSING",
        category=ErrorCategory.AUTH,
        http_status=401,
        retryable=False,
        description="Authorization header absent",
    ),
    "PERMISSION_DENIED": ErrorCodeDef(
        code="PERMISSION_DENIED",
        category=ErrorCategory.AUTH,
        http_status=403,
        retryable=False,
        description="API key lacks required permission",
    ),
    "BUDGET_EXCEEDED": ErrorCodeDef(
        code="BUDGET_EXCEEDED",
        category=ErrorCategory.POLICY,
        http_status=402,
        retryable=False,
        description="Call would exceed cost ceiling",
    ),
    "RATE_LIMITED": ErrorCodeDef(
        code="RATE_LIMITED",
        category=ErrorCategory.POLICY,
        http_status=429,
        retryable=True,
        description="Rhumb-level rate limit hit",
        default_retry_after_ms=60000,
    ),
    "PROVIDER_RATE_LIMITED": ErrorCodeDef(
        code="PROVIDER_RATE_LIMITED",
        category=ErrorCategory.PROVIDER,
        http_status=429,
        retryable=True,
        description="Provider rate limit hit",
        default_retry_after_ms=5000,
    ),
    "APPROVAL_REQUIRED": ErrorCodeDef(
        code="APPROVAL_REQUIRED",
        category=ErrorCategory.POLICY,
        http_status=202,
        retryable=False,
        description="Call requires manual approval",
    ),
    "PROVIDER_ERROR": ErrorCodeDef(
        code="PROVIDER_ERROR",
        category=ErrorCategory.PROVIDER,
        http_status=502,
        retryable=True,
        description="Provider returned 5xx",
        default_retry_after_ms=2000,
    ),
    "PROVIDER_UNAVAILABLE": ErrorCodeDef(
        code="PROVIDER_UNAVAILABLE",
        category=ErrorCategory.PROVIDER,
        http_status=503,
        retryable=True,
        description="Provider health check failing",
        default_retry_after_ms=5000,
    ),
    "NO_PROVIDER_AVAILABLE": ErrorCodeDef(
        code="NO_PROVIDER_AVAILABLE",
        category=ErrorCategory.ROUTING,
        http_status=503,
        retryable=True,
        description="All providers unavailable",
        default_retry_after_ms=10000,
    ),
    "PROVIDER_TIMEOUT": ErrorCodeDef(
        code="PROVIDER_TIMEOUT",
        category=ErrorCategory.PROVIDER,
        http_status=504,
        retryable=True,
        description="Provider did not respond",
        default_retry_after_ms=5000,
    ),
    "NORMALIZATION_ERROR": ErrorCodeDef(
        code="NORMALIZATION_ERROR",
        category=ErrorCategory.INTERNAL,
        http_status=500,
        retryable=False,
        description="Response normalization failed",
    ),
    "RECIPE_STEP_FAILED": ErrorCodeDef(
        code="RECIPE_STEP_FAILED",
        category=ErrorCategory.RECIPE,
        http_status=422,
        retryable=False,
        description="Recipe step(s) failed",
    ),
    "RECIPE_BUDGET_EXCEEDED": ErrorCodeDef(
        code="RECIPE_BUDGET_EXCEEDED",
        category=ErrorCategory.RECIPE,
        http_status=402,
        retryable=False,
        description="Recipe cost exceeded budget",
    ),
    "TIMEOUT": ErrorCodeDef(
        code="TIMEOUT",
        category=ErrorCategory.INFRA,
        http_status=504,
        retryable=True,
        description="Overall request timeout",
        default_retry_after_ms=5000,
    ),
    "INTERNAL_ERROR": ErrorCodeDef(
        code="INTERNAL_ERROR",
        category=ErrorCategory.INTERNAL,
        http_status=500,
        retryable=True,
        description="Rhumb internal error",
        default_retry_after_ms=1000,
    ),
    "PAYMENT_REQUIRED": ErrorCodeDef(
        code="PAYMENT_REQUIRED",
        category=ErrorCategory.POLICY,
        http_status=402,
        retryable=False,
        description="Payment required — insufficient credits or x402 payment needed",
    ),
    "PAYMENT_VERIFICATION_FAILED": ErrorCodeDef(
        code="PAYMENT_VERIFICATION_FAILED",
        category=ErrorCategory.POLICY,
        http_status=402,
        retryable=False,
        description="x402 payment verification failed",
    ),
    "BILLING_UNAVAILABLE": ErrorCodeDef(
        code="BILLING_UNAVAILABLE",
        category=ErrorCategory.INFRA,
        http_status=503,
        retryable=True,
        description="Billing system temporarily unavailable",
        default_retry_after_ms=30000,
    ),
    "EXECUTION_DISABLED": ErrorCodeDef(
        code="EXECUTION_DISABLED",
        category=ErrorCategory.INFRA,
        http_status=503,
        retryable=True,
        description="Execution temporarily disabled for maintenance",
        default_retry_after_ms=60000,
    ),
    "TX_REPLAY_REJECTED": ErrorCodeDef(
        code="TX_REPLAY_REJECTED",
        category=ErrorCategory.POLICY,
        http_status=409,
        retryable=False,
        description="Transaction hash already used — replay rejected",
    ),
}

_DOCS_BASE_URL = "https://rhumb.dev/docs/failure-modes"

_ERROR_CODE_DOC_FRAGMENTS: dict[str, str] = {
    "BILLING_UNAVAILABLE": "billing-unavailable",
    "CREDENTIAL_INVALID": "credential-invalid",
    "EXECUTION_DISABLED": "managed-execution-disabled",
    "NO_PROVIDER_AVAILABLE": "provider-selection-fails",
    "PAYMENT_REQUIRED": "x402-settlement-failure",
    "PAYMENT_VERIFICATION_FAILED": "x402-settlement-failure",
    "PROVIDER_ERROR": "provider-down",
    "PROVIDER_RATE_LIMITED": "quota-exceeded",
    "PROVIDER_TIMEOUT": "provider-down",
    "PROVIDER_UNAVAILABLE": "provider-down",
    "RATE_LIMITED": "quota-exceeded",
}


def _docs_url_for_code(code: str) -> str:
    fragment = _ERROR_CODE_DOC_FRAGMENTS.get(code)
    if fragment:
        return f"{_DOCS_BASE_URL}#{fragment}"
    return _DOCS_BASE_URL


# ── Error Envelope Construction ──


@dataclass
class ProviderErrorContext:
    """Provider-specific error context included in the envelope."""

    id: str
    http_status: int | None = None
    provider_error_code: str | None = None
    provider_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"id": self.id}
        if self.http_status is not None:
            d["http_status"] = self.http_status
        if self.provider_error_code is not None:
            d["provider_error_code"] = self.provider_error_code
        if self.provider_message is not None:
            d["provider_message"] = self.provider_message
        return d


def build_error_envelope(
    code: str,
    *,
    message: str | None = None,
    detail: str | None = None,
    request_id: str | None = None,
    receipt_id: str | None = None,
    provider: ProviderErrorContext | None = None,
    retry_after_ms: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a canonical error envelope per the Resolve spec.

    Args:
        code: Error code from the registry (e.g. 'PROVIDER_ERROR')
        message: Human-readable error message (defaults to code description)
        detail: Detailed error context
        request_id: Request ID for correlation
        receipt_id: Receipt ID if a receipt was created for this execution
        provider: Provider-specific error context
        retry_after_ms: Override default retry delay
        extra: Additional fields to merge into the error object

    Returns:
        Dict matching the canonical error envelope shape.
    """
    code_def = ERROR_CODES.get(code)
    if code_def is None:
        # Fallback for unknown codes — treat as internal error
        code_def = ERROR_CODES["INTERNAL_ERROR"]
        logger.warning("Unknown error code '%s', falling back to INTERNAL_ERROR", code)

    effective_retry = retry_after_ms
    if effective_retry is None and code_def.retryable:
        effective_retry = code_def.default_retry_after_ms

    envelope: dict[str, Any] = {
        "code": code_def.code,
        "category": code_def.category.value,
        "message": message or code_def.description,
        "retryable": code_def.retryable,
        "request_id": request_id or f"req_{uuid.uuid4().hex[:24]}",
        "docs_url": _docs_url_for_code(code_def.code),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if detail:
        envelope["detail"] = detail
    if receipt_id:
        envelope["receipt_id"] = receipt_id
    if effective_retry is not None:
        envelope["retry_after_ms"] = effective_retry
    if provider:
        envelope["provider"] = provider.to_dict()
    if extra:
        envelope.update(extra)

    return {"error": envelope}


def error_response(
    code: str,
    *,
    message: str | None = None,
    detail: str | None = None,
    request_id: str | None = None,
    receipt_id: str | None = None,
    provider: ProviderErrorContext | None = None,
    retry_after_ms: int | None = None,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a JSONResponse with the canonical error envelope.

    Automatically resolves HTTP status from the error code registry.
    """
    code_def = ERROR_CODES.get(code, ERROR_CODES["INTERNAL_ERROR"])
    body = build_error_envelope(
        code,
        message=message,
        detail=detail,
        request_id=request_id,
        receipt_id=receipt_id,
        provider=provider,
        retry_after_ms=retry_after_ms,
        extra=extra,
    )

    response_headers = dict(headers) if headers else {}
    if code_def.retryable and (retry_after_ms or code_def.default_retry_after_ms):
        retry_seconds = ((retry_after_ms or code_def.default_retry_after_ms) or 1000) // 1000
        response_headers.setdefault("Retry-After", str(max(retry_seconds, 1)))

    return JSONResponse(
        status_code=code_def.http_status,
        content=body,
        headers=response_headers or None,
    )


# ── Custom Exception ──


class RhumbError(Exception):
    """Structured error that produces a canonical error envelope.

    Raise this instead of FastAPI's HTTPException when you want the
    response to match the Resolve v2 error spec.
    """

    def __init__(
        self,
        code: str,
        *,
        message: str | None = None,
        detail: str | None = None,
        receipt_id: str | None = None,
        provider: ProviderErrorContext | None = None,
        retry_after_ms: int | None = None,
        extra: dict[str, Any] | None = None,
    ):
        self.code = code
        self.message = message
        self.detail = detail
        self.receipt_id = receipt_id
        self.provider = provider
        self.retry_after_ms = retry_after_ms
        self.extra = extra
        super().__init__(message or code)


async def rhumb_error_handler(request: Request, exc: RhumbError) -> JSONResponse:
    """FastAPI exception handler for RhumbError.

    Register this with:
        app.add_exception_handler(RhumbError, rhumb_error_handler)
    """
    request_id = getattr(request.state, "request_id", None) or f"req_{uuid.uuid4().hex[:24]}"
    return error_response(
        exc.code,
        message=exc.message,
        detail=exc.detail,
        request_id=request_id,
        receipt_id=exc.receipt_id,
        provider=exc.provider,
        retry_after_ms=exc.retry_after_ms,
        extra=exc.extra,
    )


# ── Helper: classify upstream provider errors ──


def classify_upstream_error(
    provider_id: str,
    http_status: int,
    *,
    provider_error_code: str | None = None,
    provider_message: str | None = None,
) -> tuple[str, ProviderErrorContext]:
    """Classify an upstream provider HTTP error into a canonical code.

    Returns (error_code, provider_context).
    """
    provider_ctx = ProviderErrorContext(
        id=provider_id,
        http_status=http_status,
        provider_error_code=provider_error_code,
        provider_message=provider_message,
    )

    if http_status == 429:
        return "PROVIDER_RATE_LIMITED", provider_ctx
    if http_status == 401 or http_status == 403:
        return "CREDENTIAL_INVALID", provider_ctx
    if http_status == 404:
        return "PROVIDER_NOT_FOUND", provider_ctx
    if http_status == 408 or http_status == 504:
        return "PROVIDER_TIMEOUT", provider_ctx
    if 500 <= http_status < 600:
        return "PROVIDER_ERROR", provider_ctx
    if 400 <= http_status < 500:
        return "INVALID_PARAMETERS", provider_ctx

    return "PROVIDER_ERROR", provider_ctx


# ── Helper: extract request_id from FastAPI request ──


def get_request_id(request: Request) -> str:
    """Get or generate a request ID."""
    return getattr(request.state, "request_id", None) or f"req_{uuid.uuid4().hex[:24]}"
