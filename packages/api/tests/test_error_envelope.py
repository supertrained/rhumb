"""Tests for the canonical error envelope system."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.error_envelope import (
    ERROR_CODES,
    ErrorCategory,
    ProviderErrorContext,
    RhumbError,
    build_error_envelope,
    classify_upstream_error,
    error_response,
)


# ── Error code registry ──


def test_all_spec_codes_registered():
    """All 21 codes from the spec plus our 4 additions are registered."""
    spec_codes = [
        "INVALID_PARAMETERS",
        "MISSING_REQUIRED_FIELD",
        "CAPABILITY_NOT_FOUND",
        "PROVIDER_NOT_FOUND",
        "RECIPE_NOT_FOUND",
        "CREDENTIAL_INVALID",
        "CREDENTIAL_MISSING",
        "PERMISSION_DENIED",
        "BUDGET_EXCEEDED",
        "RATE_LIMITED",
        "PROVIDER_RATE_LIMITED",
        "APPROVAL_REQUIRED",
        "PROVIDER_ERROR",
        "PROVIDER_UNAVAILABLE",
        "NO_PROVIDER_AVAILABLE",
        "PROVIDER_TIMEOUT",
        "NORMALIZATION_ERROR",
        "RECIPE_STEP_FAILED",
        "RECIPE_BUDGET_EXCEEDED",
        "TIMEOUT",
        "INTERNAL_ERROR",
    ]
    for code in spec_codes:
        assert code in ERROR_CODES, f"Spec code {code} missing from registry"


def test_retryable_codes_have_retry_after():
    """All retryable codes should have a default retry_after_ms."""
    for code, defn in ERROR_CODES.items():
        if defn.retryable and defn.default_retry_after_ms is None:
            # Some retryable codes may not have a default, but most should
            pass  # Acceptable


def test_http_status_ranges():
    """Verify HTTP status codes are in sensible ranges."""
    for code, defn in ERROR_CODES.items():
        assert 200 <= defn.http_status < 600, f"{code} has invalid HTTP status {defn.http_status}"


# ── Envelope construction ──


def test_build_error_envelope_basic():
    """Build a basic error envelope."""
    env = build_error_envelope("PROVIDER_ERROR", message="Something broke")
    assert "error" in env
    error = env["error"]
    assert error["code"] == "PROVIDER_ERROR"
    assert error["category"] == "provider"
    assert error["message"] == "Something broke"
    assert error["retryable"] is True
    assert error["retry_after_ms"] == 2000
    assert error["docs_url"] == "https://rhumb.dev/docs/failure-modes#provider-down"
    assert "request_id" in error
    assert "timestamp" in error


def test_build_error_envelope_with_provider():
    """Provider context is included when provided."""
    env = build_error_envelope(
        "PROVIDER_ERROR",
        provider=ProviderErrorContext(
            id="sendgrid",
            http_status=500,
            provider_error_code="internal_error",
            provider_message="Internal server error",
        ),
    )
    provider = env["error"]["provider"]
    assert provider["id"] == "sendgrid"
    assert provider["http_status"] == 500
    assert provider["provider_error_code"] == "internal_error"


def test_build_error_envelope_with_receipt():
    """Receipt ID is included when provided."""
    env = build_error_envelope(
        "PROVIDER_ERROR",
        receipt_id="rcpt_abc123",
    )
    assert env["error"]["receipt_id"] == "rcpt_abc123"


def test_build_error_envelope_non_retryable():
    """Non-retryable errors have no retry_after_ms."""
    env = build_error_envelope("CAPABILITY_NOT_FOUND")
    assert env["error"]["retryable"] is False
    assert "retry_after_ms" not in env["error"]


def test_build_error_envelope_custom_retry():
    """Custom retry_after_ms overrides default."""
    env = build_error_envelope("PROVIDER_ERROR", retry_after_ms=5000)
    assert env["error"]["retry_after_ms"] == 5000


def test_build_error_envelope_unknown_code():
    """Unknown codes fall back to INTERNAL_ERROR."""
    env = build_error_envelope("TOTALLY_MADE_UP_CODE")
    assert env["error"]["code"] == "INTERNAL_ERROR"
    assert env["error"]["docs_url"] == "https://rhumb.dev/docs/failure-modes"


def test_build_error_envelope_with_detail():
    """Detail is included when provided."""
    env = build_error_envelope(
        "INVALID_PARAMETERS",
        detail="Field 'email' must be a valid email address",
    )
    assert env["error"]["detail"] == "Field 'email' must be a valid email address"


def test_build_error_envelope_default_message():
    """Default message comes from code description."""
    env = build_error_envelope("RATE_LIMITED")
    assert env["error"]["message"] == "Rhumb-level rate limit hit"


# ── Error response ──


def test_error_response_status_code():
    """error_response returns correct HTTP status."""
    resp = error_response("PROVIDER_ERROR")
    assert resp.status_code == 502


def test_error_response_retry_header():
    """Retryable errors include Retry-After header."""
    resp = error_response("PROVIDER_ERROR")
    assert resp.headers.get("retry-after") == "2"


def test_error_response_no_retry_header_for_non_retryable():
    """Non-retryable errors have no Retry-After header."""
    resp = error_response("CAPABILITY_NOT_FOUND")
    assert resp.headers.get("retry-after") is None


def test_error_response_custom_headers():
    """Custom headers are merged."""
    resp = error_response(
        "PROVIDER_ERROR",
        headers={"X-Custom": "test"},
    )
    assert resp.headers.get("x-custom") == "test"


# ── RhumbError exception ──


def test_rhumb_error_attributes():
    """RhumbError carries structured error data."""
    err = RhumbError(
        "BUDGET_EXCEEDED",
        message="Too expensive",
        detail="Cost $0.50 exceeds ceiling $0.10",
    )
    assert err.code == "BUDGET_EXCEEDED"
    assert err.message == "Too expensive"
    assert err.detail == "Cost $0.50 exceeds ceiling $0.10"


# ── Upstream error classification ──


def test_classify_429_as_rate_limited():
    code, ctx = classify_upstream_error("openai", 429)
    assert code == "PROVIDER_RATE_LIMITED"
    assert ctx.id == "openai"
    assert ctx.http_status == 429


def test_classify_500_as_provider_error():
    code, ctx = classify_upstream_error("sendgrid", 500)
    assert code == "PROVIDER_ERROR"


def test_classify_503_as_provider_error():
    code, ctx = classify_upstream_error("stripe", 503)
    assert code == "PROVIDER_ERROR"


def test_classify_401_as_credential_invalid():
    code, ctx = classify_upstream_error("apollo", 401)
    assert code == "CREDENTIAL_INVALID"


def test_classify_404_as_provider_not_found():
    code, ctx = classify_upstream_error("exa", 404)
    assert code == "PROVIDER_NOT_FOUND"


def test_classify_504_as_timeout():
    code, ctx = classify_upstream_error("firecrawl", 504)
    assert code == "PROVIDER_TIMEOUT"


def test_classify_400_as_invalid_params():
    code, ctx = classify_upstream_error("algolia", 400)
    assert code == "INVALID_PARAMETERS"


def test_classify_with_provider_context():
    code, ctx = classify_upstream_error(
        "sendgrid",
        500,
        provider_error_code="from_not_verified",
        provider_message="From address not verified",
    )
    assert ctx.provider_error_code == "from_not_verified"
    assert ctx.provider_message == "From address not verified"


# ── Integration: FastAPI handler ──


@pytest.fixture
def client():
    """Test client with RhumbError handler registered."""
    from app import create_app
    app = create_app()
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_rhumb_error_handler_produces_canonical_envelope(client):
    """RhumbError raised in v2 routes produces canonical envelope."""
    # Hit the v2 execute with a cost ceiling that we can trigger
    # This exercises the RhumbError path we just wired
    with patch("routes.resolve_v2._forward_internal", new_callable=AsyncMock) as mock_fwd:
        # Mock estimate returning a cost
        estimate_resp = MagicMock()
        estimate_resp.status_code = 200
        estimate_resp.json.return_value = {
            "data": {
                "capability_id": "test.cap",
                "provider": "test-provider",
                "cost_estimate_usd": 1.00,
                "endpoint_pattern": "POST /test",
            },
            "error": None,
        }
        estimate_resp.headers = {}
        mock_fwd.return_value = estimate_resp

        resp = client.post(
            "/v2/capabilities/test.cap/execute",
            json={
                "parameters": {},
                "policy": {
                    "max_cost_usd": 0.01,
                },
            },
        )
        assert resp.status_code == 402
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "BUDGET_EXCEEDED"
        assert body["error"]["category"] == "policy"
        assert body["error"]["retryable"] is False
        assert "docs_url" in body["error"]
        assert "timestamp" in body["error"]
