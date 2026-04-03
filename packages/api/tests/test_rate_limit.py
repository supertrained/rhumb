"""Tests for the rate-limit middleware."""

import time

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from middleware.rate_limit import RateLimitMiddleware
from middleware.request_id import RequestIDMiddleware


@pytest.fixture
def client(monkeypatch):
    """Fresh app for each test (clean rate-limit buckets).

    Disables the durable DB path so tests verify in-memory rate-limit
    semantics without interference from Supabase connection failures.
    """
    import middleware.rate_limit as rl
    rl._buckets.clear()
    rl._last_cleanup = time.monotonic()

    # Prevent the middleware from trying to connect to Supabase
    _original_get_durable = RateLimitMiddleware._get_durable

    async def _no_durable(self):
        return None

    monkeypatch.setattr(RateLimitMiddleware, "_get_durable", _no_durable)

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestIDMiddleware)

    @app.get("/v1/services")
    async def list_services():
        return {"services": []}

    @app.get("/v1/auth/providers")
    async def auth_providers():
        return {"providers": []}

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return TestClient(app)


class TestRateLimitHeaders:
    """Rate limit headers are present on responses."""

    def test_read_endpoint_has_rate_limit_headers(self, client):
        resp = client.get("/v1/services")
        assert resp.headers.get("X-RateLimit-Limit") == "120"
        assert "X-RateLimit-Remaining" in resp.headers
        assert "X-RateLimit-Reset" in resp.headers

    def test_health_endpoint_has_generous_limit(self, client):
        resp = client.get("/healthz")
        assert resp.headers.get("X-RateLimit-Limit") == "300"


class TestRateLimitEnforcement:
    """Rate limits are enforced correctly."""

    def test_auth_endpoint_limited_at_10_per_minute(self, client):
        """Auth endpoints should return 429 after 10 requests."""
        for i in range(10):
            resp = client.get("/v1/auth/providers")
            assert resp.status_code != 429, f"Blocked too early on request {i+1}"

        # 11th request should be rate limited
        resp = client.get("/v1/auth/providers")
        assert resp.status_code == 429
        body = resp.json()
        assert body["error"] == "rate_limit_exceeded"
        assert "retry_after" in body
        assert "request_id" in body
        assert "resolution" in body
        assert resp.headers.get("Retry-After")

    def test_read_endpoint_allows_120_per_minute(self, client):
        """Public read endpoints should allow 120 requests before 429."""
        for i in range(120):
            resp = client.get("/v1/services")
            if resp.status_code == 429:
                pytest.fail(f"Rate limited too early on request {i+1}")

        # 121st should be limited
        resp = client.get("/v1/services")
        assert resp.status_code == 429

    def test_remaining_decrements(self, client):
        """X-RateLimit-Remaining should decrement with each request."""
        r1 = client.get("/v1/services")
        r2 = client.get("/v1/services")
        rem1 = int(r1.headers["X-RateLimit-Remaining"])
        rem2 = int(r2.headers["X-RateLimit-Remaining"])
        assert rem2 == rem1 - 1


class TestRateLimitBypass:
    """Certain paths bypass rate limiting."""

    def test_options_not_rate_limited(self, client):
        """CORS preflight (OPTIONS) should never be rate limited."""
        for _ in range(20):
            resp = client.options("/v1/services")
            assert resp.status_code != 429


class TestRateLimitErrorFormat:
    """429 responses follow our standard error envelope."""

    def test_429_has_standard_fields(self, client):
        """429 response should include error, message, resolution, request_id."""
        # Exhaust auth limit
        for _ in range(10):
            client.get("/v1/auth/providers")

        resp = client.get("/v1/auth/providers")
        assert resp.status_code == 429
        body = resp.json()
        assert "error" in body
        assert "message" in body
        assert "resolution" in body
        assert "request_id" in body
        assert "retry_after" in body
        assert int(resp.headers["Retry-After"]) > 0
