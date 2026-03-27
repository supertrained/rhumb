"""Tests for standardized error response envelope (request_id + resolution)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestErrorEnvelope:
    """Every error response must include request_id, error, detail, resolution, status."""

    def test_404_has_standard_fields(self, client):
        """A 404 on a non-existent route returns the standard envelope."""
        resp = client.get("/v1/this-does-not-exist")
        assert resp.status_code == 404
        body = resp.json()
        assert "request_id" in body
        assert "error" in body
        assert "detail" in body
        assert "resolution" in body
        assert "status" in body
        assert body["status"] == 404
        assert body["error"] == "not_found"
        # request_id should be a valid UUID
        uuid.UUID(body["request_id"])

    def test_404_has_x_request_id_header(self, client):
        """X-Request-ID header is present on error responses."""
        resp = client.get("/v1/this-does-not-exist")
        assert "X-Request-ID" in resp.headers
        # Header matches body
        assert resp.headers["X-Request-ID"] == resp.json()["request_id"]

    def test_client_request_id_echoed(self, client):
        """If client sends X-Request-ID, it's echoed back."""
        custom_id = "my-custom-request-123"
        resp = client.get(
            "/v1/this-does-not-exist",
            headers={"X-Request-ID": custom_id},
        )
        assert resp.headers["X-Request-ID"] == custom_id
        assert resp.json()["request_id"] == custom_id

    def test_healthz_has_request_id_header(self, client):
        """Even success responses get X-Request-ID header."""
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers
        uuid.UUID(resp.headers["X-Request-ID"])

    def test_405_method_not_allowed(self, client):
        """Method not allowed returns standard envelope."""
        resp = client.delete("/healthz")
        assert resp.status_code == 405
        body = resp.json()
        assert body["error"] == "method_not_allowed"
        assert "request_id" in body
        assert "resolution" in body

    def test_resolution_is_actionable(self, client):
        """Resolution text is non-empty and provides guidance."""
        resp = client.get("/v1/this-does-not-exist")
        body = resp.json()
        assert len(body["resolution"]) > 10  # Not a stub
        assert "not found" in body["resolution"].lower() or "verify" in body["resolution"].lower()

    def test_500_keeps_cors_headers_for_allowlisted_origin(self):
        """Unhandled errors should still preserve CORS for rhumb.dev."""
        app = create_app()

        @app.get("/boom")
        async def boom():
            raise RuntimeError("boom")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/boom", headers={"Origin": "https://rhumb.dev"})

        assert resp.status_code == 500
        assert resp.headers["access-control-allow-origin"] == "https://rhumb.dev"
        assert "Origin" in resp.headers["vary"]
