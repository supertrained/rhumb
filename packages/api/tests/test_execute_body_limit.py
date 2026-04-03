from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from middleware.rate_limit import _buckets


@pytest.fixture(autouse=True)
def _clear_rate_limit_buckets():
    _buckets.clear()
    yield
    _buckets.clear()


@pytest.mark.anyio
async def test_v1_execute_rejects_oversized_inline_payload(monkeypatch):
    monkeypatch.setenv("RHUMB_EXECUTE_MAX_BODY_BYTES", "128")
    app = create_app()
    oversized = json.dumps(
        {
            "provider": "sendgrid",
            "method": "POST",
            "path": "/v3/mail/send",
            "body": {"prompt": "x" * 512},
        }
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/capabilities/email.send/execute",
            content=oversized,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 413
    body = response.json()
    assert body["error"] == "payload_too_large"
    assert body["status"] == 413
    assert body["limit_bytes"] == 128


@pytest.mark.anyio
async def test_v2_execute_rejects_oversized_inline_payload(monkeypatch):
    monkeypatch.setenv("RHUMB_EXECUTE_MAX_BODY_BYTES", "128")
    app = create_app()
    oversized = json.dumps(
        {
            "credential_mode": "auto",
            "interface": "rest",
            "parameters": {"prompt": "x" * 512},
        }
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v2/capabilities/email.send/execute",
            content=oversized,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 413
    body = response.json()
    assert body["error"] == "payload_too_large"
    assert body["status"] == 413
    assert body["limit_bytes"] == 128
