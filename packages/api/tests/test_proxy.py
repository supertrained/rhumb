"""Tests for proxy router (Slice A: Router Foundation)."""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from routes.proxy import router as proxy_router


@pytest.fixture
def app():
    """Create test FastAPI app with proxy router."""
    app = FastAPI()
    app.include_router(proxy_router, prefix="/proxy")
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestProxyRouter:
    """Test suite for proxy router functionality."""

    def test_list_services(self, client):
        """Test listing available services."""
        response = client.get("/proxy/services")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert "services" in data["data"]
        assert len(data["data"]["services"]) > 0
        assert "stripe" in [s["name"] for s in data["data"]["services"]]

    def test_service_registry_structure(self, client):
        """Test that service registry has correct structure."""
        response = client.get("/proxy/services")
        data = response.json()
        for service in data["data"]["services"]:
            assert "name" in service
            assert "domain" in service
            assert "auth_type" in service
            assert "rate_limit" in service

    @patch("routes.proxy.httpx.AsyncClient.request")
    def test_proxy_successful_request(self, mock_request, client):
        """Test successful proxy request."""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "cus_123", "email": "test@example.com"}
        mock_response.headers = {"content-type": "application/json"}
        mock_request.return_value = mock_response

        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/customers/cus_123",
                "body": None,
                "params": None,
                "headers": None,
            },
            headers={"Authorization": "Bearer sk_test_123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status_code"] == 200
        assert data["service"] == "stripe"
        assert data["path"] == "/v1/customers/cus_123"
        assert data["latency_ms"] >= 0

    @patch("routes.proxy.httpx.AsyncClient.request")
    def test_proxy_latency_measurement(self, mock_request, client):
        """Test that latency is measured correctly."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.headers = {}
        mock_request.return_value = mock_response

        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/customers",
                "body": None,
                "params": None,
                "headers": None,
            },
        )

        data = response.json()
        assert "latency_ms" in data
        assert data["latency_ms"] >= 0

    def test_proxy_service_not_found(self, client):
        """Test error when service not found."""
        response = client.post(
            "/proxy/",
            json={
                "service": "nonexistent",
                "method": "GET",
                "path": "/v1/test",
                "body": None,
                "params": None,
                "headers": None,
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "Service 'nonexistent' not found" in data["detail"]

    @patch("routes.proxy.httpx.AsyncClient.request")
    def test_proxy_auth_header_injection(self, mock_request, client):
        """Test that Authorization header is properly injected."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.headers = {}
        mock_request.return_value = mock_response

        auth_token = "Bearer sk_test_12345"
        client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "POST",
                "path": "/v1/customers",
                "body": {"email": "test@example.com"},
                "params": None,
                "headers": None,
            },
            headers={"Authorization": auth_token},
        )

        # Verify that the Authorization header was passed to the mock request
        called_headers = mock_request.call_args[1]["headers"]
        assert "Authorization" in called_headers
        assert called_headers["Authorization"] == auth_token

    @patch("routes.proxy.httpx.AsyncClient.request")
    def test_proxy_custom_headers(self, mock_request, client):
        """Test that custom headers are preserved."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.headers = {}
        mock_request.return_value = mock_response

        custom_headers = {"X-Custom-Header": "custom-value"}
        client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "POST",
                "path": "/v1/customers",
                "body": None,
                "params": None,
                "headers": custom_headers,
            },
        )

        called_headers = mock_request.call_args[1]["headers"]
        assert "X-Custom-Header" in called_headers
        assert called_headers["X-Custom-Header"] == "custom-value"

    @patch("routes.proxy.httpx.AsyncClient.request")
    def test_proxy_response_body_parsing_json(self, mock_request, client):
        """Test JSON response body parsing."""
        expected_body = {"id": "ch_123", "amount": 1000}
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = expected_body
        mock_response.headers = {"content-type": "application/json"}
        mock_request.return_value = mock_response

        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "POST",
                "path": "/v1/charges",
                "body": {"amount": 1000},
                "params": None,
                "headers": None,
            },
        )

        data = response.json()
        assert data["body"] == expected_body

    @patch("routes.proxy.httpx.AsyncClient.request")
    def test_proxy_response_body_parsing_text(self, mock_request, client):
        """Test fallback to text response parsing."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.text = "Plain text response"
        mock_response.headers = {}
        mock_request.return_value = mock_response

        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/test",
                "body": None,
                "params": None,
                "headers": None,
            },
        )

        data = response.json()
        assert data["body"] == "Plain text response"

    @patch("routes.proxy.httpx.AsyncClient.request")
    def test_proxy_error_response(self, mock_request, client):
        """Test proxy error handling."""
        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "Unauthorized"}
        mock_response.headers = {"content-type": "application/json"}
        mock_request.return_value = mock_response

        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                "method": "GET",
                "path": "/v1/customers",
                "body": None,
                "params": None,
                "headers": None,
            },
        )

        # Proxy should forward the error response as-is
        data = response.json()
        assert data["status_code"] == 401
        assert data["body"]["error"] == "Unauthorized"

    def test_proxy_stats_endpoint(self, client):
        """Test proxy stats endpoint."""
        response = client.get("/proxy/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is None
        assert "services_online" in data["data"]
        assert data["data"]["services_online"] > 0


class TestProxyRequest:
    """Test ProxyRequest schema validation."""

    def test_proxy_request_required_fields(self, client):
        """Test that required fields are enforced."""
        response = client.post(
            "/proxy/",
            json={
                "service": "stripe",
                # Missing method and path
            },
        )
        assert response.status_code == 422  # Validation error

    def test_proxy_request_valid(self, client):
        """Test valid proxy request structure."""
        with patch("routes.proxy.httpx.AsyncClient.request") as mock_request:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            response = client.post(
                "/proxy/",
                json={
                    "service": "stripe",
                    "method": "POST",
                    "path": "/v1/customers",
                    "body": {"email": "test@example.com"},
                    "params": {"limit": 10},
                    "headers": {"X-Custom": "value"},
                },
            )
            assert response.status_code == 200
