"""Integration tests for proxy route with pool + breaker + latency.

Tests the full proxy pipeline: pool acquire -> breaker check -> route -> metrics.
"""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Bypass constants (must match conftest values)
_BYPASS_AGENT_ID = "00000000-0000-0000-0000-bypass000001"
_BYPASS_KEY = "rhumb_test_bypass_key_0000"

sys.path.insert(0, str(Path(__file__).parent.parent))

import routes.proxy as proxy_module
from routes.proxy import (
    ProxyResponse,
    get_breaker_registry,
    get_latency_tracker,
    get_pool_manager,
    router as proxy_router,
)
from services.proxy_breaker import BreakerRegistry, BreakerState
from services.error_envelope import RhumbError, rhumb_error_handler
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
    test_app.add_exception_handler(RhumbError, rhumb_error_handler)
    test_app.include_router(proxy_router, prefix="/proxy")
    return test_app


@pytest.fixture
def client(app):
    """Create test client with bypass auth header."""
    return TestClient(app, headers={"X-Rhumb-Key": "rhumb_test_bypass_key_0000"})


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
        # Auth enforcement uses real agent_id — check count for the bypass agent
        assert tracker.record_count("stripe", _BYPASS_AGENT_ID) == 1

    def test_response_reports_total_and_upstream_latency(
        self, client, httpx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Response exposes total route latency separately from upstream latency."""
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/v1/customers",
            json={},
            status_code=200,
            headers={},
        )
        perf_values = iter(i / 100 for i in range(30))

        class FakeTime:
            def perf_counter(self) -> float:
                return next(perf_values)

            def time(self) -> float:
                return 123.0

        monkeypatch.setattr(proxy_module, "time", FakeTime())

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
        assert data["upstream_latency_ms"] == pytest.approx(10.0)
        assert data["latency_ms"] == pytest.approx(200.0)
        assert data["latency_ms"] > data["upstream_latency_ms"]

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
        # Auth enforcement uses real agent_id — check the bypass agent's breaker
        breaker = breaker_reg.get("stripe", _BYPASS_AGENT_ID)
        assert breaker.metrics.consecutive_failures == 1

    def test_circuit_open_returns_fail_open(self, client, httpx_mock) -> None:
        """When circuit is OPEN, proxy returns fail_open response without calling provider."""
        # Trigger circuit open by recording failures directly
        import routes.proxy as proxy_module

        proxy_module._breaker_registry = BreakerRegistry()
        # Pre-populate for the bypass agent_id (not "default")
        breaker = proxy_module._breaker_registry.get("stripe", _BYPASS_AGENT_ID)
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
        assert data["upstream_latency_ms"] == 0.0
        assert data["latency_ms"] >= 0.0

    def test_auth_header_forwarded(self, client, httpx_mock) -> None:
        """Vault credential is injected — caller-supplied auth is NOT forwarded."""
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
            headers={"Authorization": "Bearer sk_caller_should_be_dropped"},
        )

        request = httpx_mock.get_request()
        # Vault credential injected — provider gets vault key, not caller's token
        assert "Authorization" in request.headers
        assert request.headers["Authorization"] != "Bearer sk_caller_should_be_dropped"
        assert request.headers["Authorization"].startswith("Bearer ")

    def test_service_not_found_still_works(self, client) -> None:
        """Unknown/ungrantable service returns 403 (ACL fires before registry lookup)."""
        response = client.post(
            "/proxy/",
            json={
                "service": "nonexistent",
                "method": "GET",
                "path": "/v1/test",
            },
        )

        # With auth enforcement, ACL fires before service registry lookup.
        # The bypass agent has no grant for "nonexistent", so 403 is correct.
        assert response.status_code == 403

    def test_route_uses_service_timeout_threshold_override(
        self, client, httpx_mock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Route passes the per-service timeout threshold into breaker creation."""
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/v1/customers",
            json={},
            status_code=200,
            headers={},
        )
        monkeypatch.setitem(proxy_module.SERVICE_REGISTRY["stripe"], "timeout_threshold_ms", 2345.0)

        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/customers",
            },
        )

        assert response.status_code == 200
        breaker = proxy_module.get_breaker_registry().get("stripe", _BYPASS_AGENT_ID)
        assert breaker.timeout_threshold_ms == 2345.0

    def test_exception_path_records_total_route_latency(
        self, client, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exception path records total route latency, not upstream-only time."""

        class RecordingTracker:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            def record(self, **kwargs: Any) -> None:
                self.calls.append(kwargs)

        class FailingClient:
            async def request(self, **kwargs: Any) -> None:
                raise RuntimeError("boom")

        class FailingPool:
            async def acquire(
                self, service: str, agent_id: str, *, base_url: str = ""
            ) -> FailingClient:
                return FailingClient()

            async def release(self, service: str, agent_id: str) -> None:
                return None

        tracker = RecordingTracker()
        perf_values = iter(i / 100 for i in range(30))

        class FakeTime:
            def perf_counter(self) -> float:
                return next(perf_values)

            def time(self) -> float:
                return 123.0

        monkeypatch.setattr(proxy_module, "time", FakeTime())
        monkeypatch.setattr(proxy_module, "get_latency_tracker", lambda: tracker)
        monkeypatch.setattr(proxy_module, "get_pool_manager", lambda: FailingPool())

        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/customers",
            },
        )

        assert response.status_code == 500
        assert tracker.calls
        assert tracker.calls[0]["latency_ms"] == pytest.approx(130.0)


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
        assert data["services_registered"] == len(proxy_module.SERVICE_REGISTRY)
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

        # Pass the bypass agent_id so the metrics endpoint looks at the right bucket
        response = client.get(f"/proxy/metrics/stripe?agent_id={_BYPASS_AGENT_ID}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "latency" in data
        assert data["latency"]["count"] >= 1
        assert data["circuit_state"] == "closed"

    def test_metrics_endpoint_accepts_canonical_alias_backed_service(self, client, httpx_mock) -> None:
        """Per-service metrics should accept canonical public ids for proxy aliases."""
        identity_store = proxy_module._identity_store
        assert identity_store is not None

        import asyncio

        async def _grant() -> None:
            await identity_store.grant_service_access(_BYPASS_AGENT_ID, "pdl")

        asyncio.run(_grant())
        proxy_module._auth_injector_instance.credentials.set_credential(
            "pdl", "api_key", "pdl_test_vault"
        )

        httpx_mock.add_response(
            method="GET",
            url="https://api.peopledatalabs.com/v5/person/enrich",
            json={"status": 200},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        response = client.post(
            "/proxy/",
            json={
                "service": "people-data-labs",
                "method": "GET",
                "path": "/v5/person/enrich",
            },
        )
        assert response.status_code == 200

        metrics = client.get(
            f"/proxy/metrics/people-data-labs?agent_id={_BYPASS_AGENT_ID}"
        )
        assert metrics.status_code == 200
        data = metrics.json()["data"]
        assert data["latency"]["service"] == "people-data-labs"
        assert data["latency"]["count"] >= 1

    def test_metrics_endpoint_rejects_blank_agent_filter_before_metric_reads(self, client) -> None:
        """Blank agent filters should not silently read the default metrics bucket."""
        with patch("routes.proxy.get_latency_tracker") as mock_tracker:
            response = client.get("/proxy/metrics/stripe?agent_id=%20%20")

        assert response.status_code == 400
        payload = response.json()
        assert payload["error"]["code"] == "INVALID_PARAMETERS"
        assert payload["error"]["message"] == "Invalid 'agent_id' filter."
        assert payload["error"]["detail"] == "Provide a non-empty agent_id value or omit the filter."
        mock_tracker.assert_not_called()

    def test_metrics_endpoint_invalid_service(self, client) -> None:
        """Metrics endpoint for invalid service returns a canonical envelope."""
        with patch("routes.proxy.get_latency_tracker") as mock_tracker:
            response = client.get("/proxy/metrics/nonexistent")

        assert response.status_code == 400
        payload = response.json()
        assert payload["error"]["code"] == "INVALID_PARAMETERS"
        assert payload["error"]["message"] == "Invalid 'service' path parameter."
        assert "stripe" in payload["error"]["detail"]
        mock_tracker.assert_not_called()

    def test_metrics_endpoint_rejects_blank_service_before_metric_reads(self, client) -> None:
        """Blank service path values should not open proxy metric stores."""
        with patch("routes.proxy.get_latency_tracker") as mock_tracker:
            response = client.get("/proxy/metrics/%20%20")

        assert response.status_code == 400
        payload = response.json()
        assert payload["error"]["code"] == "INVALID_PARAMETERS"
        assert payload["error"]["message"] == "Invalid 'service' path parameter."
        assert payload["error"]["detail"] == "Provide a non-empty service id."
        mock_tracker.assert_not_called()


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
            breaker = proxy_module._breaker_registry.get("stripe", _BYPASS_AGENT_ID)
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

        breaker = proxy_module._breaker_registry.get("stripe", _BYPASS_AGENT_ID)
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
        assert tracker.record_count("stripe", _BYPASS_AGENT_ID) == 20

        snapshot = tracker.get_snapshot("stripe", _BYPASS_AGENT_ID)
        assert snapshot.count == 20
        assert snapshot.p50_ms > 0
        assert snapshot.p95_ms >= snapshot.p50_ms
        assert snapshot.p99_ms >= snapshot.p95_ms
