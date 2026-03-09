"""Integration tests for Round 13 proxy schema detection (Module 4)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from routes.leaderboard import router as leaderboard_router  # noqa: E402
from routes.proxy import admin_router as proxy_admin_router  # noqa: E402
from routes.proxy import router as proxy_router  # noqa: E402


@pytest.fixture
def fresh_schema_state() -> None:
    """Reset proxy/schema singletons and stores between tests."""
    import routes.proxy as proxy_module
    from services.schema_alert_pipeline import reset_alert_dispatcher
    from services.schema_change_detector import reset_schema_change_detector

    proxy_module._pool_manager = None
    proxy_module._breaker_registry = None
    proxy_module._latency_tracker = None
    proxy_module._schema_detector = None
    proxy_module._schema_alert_dispatcher = None
    proxy_module._schema_events = []

    reset_schema_change_detector()
    reset_alert_dispatcher()


@pytest.fixture
def app(fresh_schema_state) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(proxy_router, prefix="/v1/proxy")
    test_app.include_router(proxy_admin_router, prefix="/v1")
    test_app.include_router(leaderboard_router, prefix="/v1")
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestProxySchemaIntegration:
    """Proxy + schema detector + alert/admin endpoints."""

    def test_proxy_stable_schema_response_unaffected_and_fingerprint_stored(
        self, client: TestClient, httpx_mock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/customers",
            json={"id": "cus_1", "email": "a@example.com"},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        response = client.post(
            "/v1/proxy/",
            json={"service": "stripe", "method": "GET", "path": "/customers"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["body"]["id"] == "cus_1"

        admin = client.get("/v1/admin/schema/stripe/customers")
        assert admin.status_code == 200
        latest = admin.json()["data"]["latest_fingerprint"]
        assert latest["hash"] is not None

    def test_proxy_breaking_change_dispatches_alert_async(
        self, client: TestClient, httpx_mock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/customers",
            json={"id": "cus_1", "email": "a@example.com"},
            status_code=200,
            headers={"content-type": "application/json"},
        )
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/customers",
            json={"id": "cus_1"},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        client.post("/v1/proxy/", json={"service": "stripe", "method": "GET", "path": "/customers"})
        second = client.post(
            "/v1/proxy/",
            json={"service": "stripe", "method": "GET", "path": "/customers"},
        )
        assert second.status_code == 200

        alerts = client.get("/v1/admin/schema-alerts?service=stripe&limit=10")
        assert alerts.status_code == 200
        assert alerts.json()["data"]["count"] >= 1

    def test_multiple_calls_same_schema_reuses_baseline(self, client: TestClient, httpx_mock) -> None:
        for _ in range(2):
            httpx_mock.add_response(
                method="GET",
                url="https://api.stripe.com/payment-intents",
                json={"id": "pi_1", "amount": 1000},
                status_code=200,
                headers={"content-type": "application/json"},
            )

        client.post(
            "/v1/proxy/",
            json={"service": "stripe", "method": "GET", "path": "/payment-intents"},
        )
        client.post(
            "/v1/proxy/",
            json={"service": "stripe", "method": "GET", "path": "/payment-intents"},
        )

        import routes.proxy as proxy_module

        detector = proxy_module.get_schema_detector()
        assert len(detector._diff_cache) == 0

    def test_admin_schema_endpoint_returns_latest_fingerprint_and_history(
        self, client: TestClient, httpx_mock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/create-payment-intent",
            json={"id": "pi_1", "amount": 1000},
            status_code=200,
            headers={"content-type": "application/json"},
        )
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/create-payment-intent",
            json={"id": "pi_1", "amount": "1000", "currency": "usd"},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        client.post(
            "/v1/proxy/",
            json={"service": "stripe", "method": "GET", "path": "/create-payment-intent"},
        )
        client.post(
            "/v1/proxy/",
            json={"service": "stripe", "method": "GET", "path": "/create-payment-intent"},
        )

        admin = client.get("/v1/admin/schema/stripe/create-payment-intent")
        data = admin.json()["data"]
        assert data["latest_fingerprint"]["hash"] is not None
        assert len(data["changes"]) >= 1

    def test_leaderboard_applies_schema_stability_multiplier(self, client: TestClient) -> None:
        response = client.get("/v1/leaderboard/email?limit=1")
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        if items:
            assert "freshness_multiplier" in items[0]
            assert items[0]["freshness_multiplier"] >= 1.0

    def test_breaking_change_webhook_payload_shape(self, client: TestClient, httpx_mock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/invoices",
            json={"id": "in_1", "customer": "cus_1"},
            status_code=200,
            headers={"content-type": "application/json"},
        )
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/invoices",
            json={"id": "in_1"},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        client.post("/v1/proxy/", json={"service": "stripe", "method": "GET", "path": "/invoices"})
        client.post("/v1/proxy/", json={"service": "stripe", "method": "GET", "path": "/invoices"})

        alerts = client.get("/v1/admin/schema-alerts?service=stripe&limit=1").json()["data"]["alerts"]
        assert alerts
        detail = alerts[0]["change_detail"]
        assert detail["service"] == "stripe"
        assert detail["endpoint"].startswith("default:")
        assert detail["changes"]

    def test_error_response_schema_isolated_from_success_baseline(
        self, client: TestClient, httpx_mock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/accounts",
            json={"id": "acct_1", "email": "a@example.com"},
            status_code=200,
            headers={"content-type": "application/json"},
        )
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/accounts",
            json={"error": {"message": "boom"}},
            status_code=500,
            headers={"content-type": "application/json"},
        )

        ok = client.post("/v1/proxy/", json={"service": "stripe", "method": "GET", "path": "/accounts"})
        err = client.post("/v1/proxy/", json={"service": "stripe", "method": "GET", "path": "/accounts"})
        assert ok.status_code == 200
        assert err.status_code == 200

        admin = client.get("/v1/admin/schema/stripe/accounts")
        assert admin.status_code == 200
        assert admin.json()["data"]["latest_fingerprint"]["hash"] is not None

    def test_high_volume_calls_do_not_block_proxy(self, client: TestClient, httpx_mock) -> None:
        for _ in range(100):
            httpx_mock.add_response(
                method="GET",
                url="https://api.stripe.com/high-volume",
                json={"ok": True, "id": "x"},
                status_code=200,
                headers={"content-type": "application/json"},
            )

        for _ in range(100):
            response = client.post(
                "/v1/proxy/",
                json={"service": "stripe", "method": "GET", "path": "/high-volume"},
            )
            assert response.status_code == 200

    def test_multi_tenant_alert_isolation(self, client: TestClient, httpx_mock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/tenant-endpoint",
            json={"id": "1", "email": "a@example.com"},
            status_code=200,
            headers={"content-type": "application/json"},
        )
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/tenant-endpoint",
            json={"id": "1"},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        client.post(
            "/v1/proxy/",
            json={"service": "stripe", "method": "GET", "path": "/tenant-endpoint", "agent_id": "agent-a"},
        )
        client.post(
            "/v1/proxy/",
            json={"service": "stripe", "method": "GET", "path": "/tenant-endpoint", "agent_id": "agent-a"},
        )

        schema_a = client.get("/v1/admin/schema/stripe/tenant-endpoint?agent_id=agent-a").json()["data"]
        schema_b = client.get("/v1/admin/schema/stripe/tenant-endpoint?agent_id=agent-b").json()["data"]
        assert schema_a["changes"]
        assert not schema_b["changes"]

    def test_admin_schema_alerts_query_filters(self, client: TestClient, httpx_mock) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/filter-alerts",
            json={"id": "1", "email": "a@example.com"},
            status_code=200,
            headers={"content-type": "application/json"},
        )
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/filter-alerts",
            json={"id": "1"},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        client.post("/v1/proxy/", json={"service": "stripe", "method": "GET", "path": "/filter-alerts"})
        client.post("/v1/proxy/", json={"service": "stripe", "method": "GET", "path": "/filter-alerts"})

        response = client.get("/v1/admin/schema-alerts?service=stripe&severity=breaking&limit=10")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["count"] >= 1
        assert all(alert["service"] == "stripe" for alert in data["alerts"])
