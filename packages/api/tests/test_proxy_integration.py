"""Integration tests for proxy route with pool + breaker + latency.

Tests the full proxy pipeline: pool acquire -> breaker check -> route -> metrics.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from routes.proxy import (
    ProxyResponse,
    get_breaker_registry,
    get_latency_tracker,
    get_pool_manager,
    router as proxy_router,
)
from services.proxy_breaker import BreakerRegistry, BreakerState
from services.proxy_latency import LatencyTracker
from services.proxy_pool import PoolManager


@pytest.fixture
def fresh_state():
    """Reset all global singletons before each test."""
    import routes.proxy as proxy_module

    proxy_module._pool_manager = None
    proxy_module._breaker_registry = None
    proxy_module._latency_tracker = None
    proxy_module._http_client = None
    yield
    # Cleanup: shutdown pool if created
    if proxy_module._pool_manager is not None:
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                pass  # Can't shutdown in running loop
            else:
                loop.run_until_complete(proxy_module._pool_manager.shutdown())
        except RuntimeError:
            pass
    proxy_module._pool_manager = None
    proxy_module._breaker_registry = None
    proxy_module._latency_tracker = None


@pytest.fixture
def app(fresh_state):
    """Create test FastAPI app with proxy router."""
    test_app = FastAPI()
    test_app.include_router(proxy_router, prefix="/proxy")
    return test_app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestIntegrationProxyRequest:
    """Test full proxy request flow with pool + breaker + latency."""

    def test_successful_request_uses_pool(self, client, httpx_mock) -> None:
        """Successful request goes through pool manager."""
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/v1/customers",
            json={"data": []},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/customers",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["fail_open"] is False
        assert data["latency_ms"] >= 0

    def test_request_records_latency(self, client, httpx_mock) -> None:
        """Proxy request records latency in tracker."""
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/v1/customers",
            json={},
            status_code=200,
            headers={},
        )

        client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/customers",
            },
        )

        # Check latency was recorded
        import routes.proxy as proxy_module

        tracker = proxy_module._latency_tracker
        assert tracker is not None
        assert tracker.record_count("stripe") == 1

    def test_5xx_records_breaker_failure(self, client, httpx_mock) -> None:
        """5xx response records a failure in the circuit breaker."""
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/v1/customers",
            json={"error": "Internal Server Error"},
            status_code=500,
            headers={},
        )

        client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/customers",
            },
        )

        import routes.proxy as proxy_module

        breaker_reg = proxy_module._breaker_registry
        assert breaker_reg is not None
        breaker = breaker_reg.get("stripe", "default")
        assert breaker.metrics.consecutive_failures == 1

    def test_circuit_open_returns_fail_open(self, client, httpx_mock) -> None:
        """When circuit is OPEN, proxy returns fail_open response without calling provider."""
        # Trigger circuit open by recording failures directly
        import routes.proxy as proxy_module

        proxy_module._breaker_registry = BreakerRegistry()
        breaker = proxy_module._breaker_registry.get("stripe", "default")
        for _ in range(5):
            breaker.record_failure(status_code=500)

        assert breaker.state == BreakerState.OPEN

        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/customers",
            },
        )

        assert response.status_code == 200  # FastAPI returns 200, body has 503
        data = response.json()
        assert data["fail_open"] is True
        assert data["status_code"] == 503

    def test_auth_header_forwarded(self, client, httpx_mock) -> None:
        """Authorization header is forwarded through the proxy."""
        httpx_mock.add_response(
            method="POST",
            url="https://api.stripe.com/v1/charges",
            json={"id": "ch_123"},
            status_code=200,
            headers={},
        )

        client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "POST",
                "path": "/v1/charges",
                "body": {"amount": 1000},
            },
            headers={"Authorization": "Bearer sk_test_xyz"},
        )

        request = httpx_mock.get_request()
        assert request.headers["Authorization"] == "Bearer sk_test_xyz"

    def test_service_not_found_still_works(self, client) -> None:
        """Invalid service returns 400 without pool/breaker errors."""
        response = client.post(
            "/proxy/",
            json={
                "service": "nonexistent",
                "method": "GET",
                "path": "/v1/test",
            },
        )

        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()


class TestIntegrationStats:
    """Test stats and metrics endpoints with real data."""

    def test_stats_after_requests(self, client, httpx_mock) -> None:
        """Stats endpoint reflects real request data."""
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/v1/customers",
            json={},
            status_code=200,
            headers={},
        )

        # Make a request first
        client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/customers",
            },
        )

        # Check stats
        response = client.get("/proxy/stats")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["services_online"] == 5
        assert data["latency"]["total_calls"] >= 1

    def test_metrics_endpoint_for_service(self, client, httpx_mock) -> None:
        """Per-service metrics endpoint returns latency data."""
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/v1/customers",
            json={},
            status_code=200,
            headers={},
        )

        client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/customers",
            },
        )

        response = client.get("/proxy/metrics/stripe")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "latency" in data
        assert data["latency"]["count"] >= 1
        assert data["circuit_state"] == "closed"

    def test_metrics_endpoint_invalid_service(self, client) -> None:
        """Metrics endpoint for invalid service returns 400."""
        response = client.get("/proxy/metrics/nonexistent")
        assert response.status_code == 400


class TestIntegrationErrorCascade:
    """Test error handling and cascading failures."""

    def test_timeout_error_records_failure(self, client, httpx_mock) -> None:
        """Connection timeout records failure in breaker."""
        import httpx as _httpx

        httpx_mock.add_exception(
            _httpx.ConnectTimeout("Connection timed out"),
            method="GET",
            url="https://api.stripe.com/v1/customers",
        )

        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/customers",
            },
        )

        assert response.status_code == 500

        import routes.proxy as proxy_module

        if proxy_module._breaker_registry:
            breaker = proxy_module._breaker_registry.get("stripe", "default")
            assert breaker.metrics.total_failures >= 1

    def test_cascade_failures_trip_breaker(self, client, httpx_mock) -> None:
        """5 consecutive failures trip the circuit breaker."""
        for _ in range(5):
            httpx_mock.add_response(
                method="GET",
                url="https://api.stripe.com/v1/customers",
                json={"error": "Internal Server Error"},
                status_code=500,
                headers={},
            )

        for _ in range(5):
            client.post(
                "/proxy/",
                json={
                    "service": "stripe",
                    "method": "GET",
                    "path": "/v1/customers",
                },
            )

        import routes.proxy as proxy_module

        breaker = proxy_module._breaker_registry.get("stripe", "default")
        assert breaker.state == BreakerState.OPEN

    def test_breaker_open_then_fail_open(self, client, httpx_mock) -> None:
        """After breaker trips, next request gets fail_open response."""
        for _ in range(5):
            httpx_mock.add_response(
                method="GET",
                url="https://api.stripe.com/v1/customers",
                json={"error": "Internal Server Error"},
                status_code=500,
                headers={},
            )

        # Trip the breaker
        for _ in range(5):
            client.post(
                "/proxy/",
                json={
                    "service": "stripe",
                    "method": "GET",
                    "path": "/v1/customers",
                },
            )

        # Next request should get fail_open
        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/customers",
            },
        )

        data = response.json()
        assert data["fail_open"] is True
        assert data["status_code"] == 503

    def test_metrics_under_load(self, client, httpx_mock) -> None:
        """Metrics remain consistent under load (20 rapid requests)."""
        for _ in range(20):
            httpx_mock.add_response(
                method="GET",
                url="https://api.stripe.com/v1/customers",
                json={},
                status_code=200,
                headers={},
            )

        for _ in range(20):
            client.post(
                "/proxy/",
                json={
                    "service": "stripe",
                    "method": "GET",
                    "path": "/v1/customers",
                },
            )

        import routes.proxy as proxy_module

        tracker = proxy_module._latency_tracker
        assert tracker is not None
        assert tracker.record_count("stripe") == 20

        snapshot = tracker.get_snapshot("stripe")
        assert snapshot.count == 20
        assert snapshot.p50_ms > 0
        assert snapshot.p95_ms >= snapshot.p50_ms
        assert snapshot.p99_ms >= snapshot.p95_ms
