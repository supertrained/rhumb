"""Integration tests for Round 13 proxy schema detection (Module 4)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from routes.leaderboard import router as leaderboard_router  # noqa: E402
from routes.proxy import admin_router as proxy_admin_router  # noqa: E402
from routes.proxy import router as proxy_router  # noqa: E402
import routes.proxy as proxy_module  # noqa: E402

# Must match conftest.BYPASS_AGENT_ID
_BYPASS_AGENT_ID = "00000000-0000-0000-0000-bypass000001"


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
    from services.error_envelope import RhumbError, rhumb_error_handler

    test_app = FastAPI()
    test_app.add_exception_handler(RhumbError, rhumb_error_handler)
    test_app.include_router(proxy_router, prefix="/v1/proxy")
    test_app.include_router(proxy_admin_router, prefix="/v1")
    test_app.include_router(leaderboard_router, prefix="/v1")
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, headers={"X-Rhumb-Key": "rhumb_test_bypass_key_0000"})


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

        # Auth enforcement stores schema under real agent_id, not "default"
        admin = client.get(f"/v1/admin/schema/stripe/customers?agent_id={_BYPASS_AGENT_ID}")
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

        admin = client.get(f"/v1/admin/schema/stripe/create-payment-intent?agent_id={_BYPASS_AGENT_ID}")
        data = admin.json()["data"]
        assert data["latest_fingerprint"]["hash"] is not None
        assert len(data["changes"]) >= 1

    def test_admin_schema_endpoint_trims_valid_agent_id(
        self, client: TestClient, httpx_mock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/trimmed-agent-schema",
            json={"id": "pi_1", "amount": 1000},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        client.post(
            "/v1/proxy/",
            json={"service": "stripe", "method": "GET", "path": "/trimmed-agent-schema"},
        )

        admin = client.get(
            f"/v1/admin/schema/stripe/trimmed-agent-schema?agent_id=%20{_BYPASS_AGENT_ID}%20"
        )

        assert admin.status_code == 200
        data = admin.json()["data"]
        assert data["agent_id"] == _BYPASS_AGENT_ID
        assert data["latest_fingerprint"]["hash"] is not None

    def test_admin_schema_endpoint_rejects_invalid_filters_before_read(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail_if_schema_detector_opens():
            raise AssertionError("schema detector opened before snapshot filter validation")

        monkeypatch.setattr(proxy_module, "get_schema_detector", fail_if_schema_detector_opens)

        blank_service = client.get(f"/v1/admin/schema/%20%20/customers?agent_id={_BYPASS_AGENT_ID}")
        invalid_service = client.get(f"/v1/admin/schema/not-a-service/customers?agent_id={_BYPASS_AGENT_ID}")
        blank_agent = client.get("/v1/admin/schema/stripe/customers?agent_id=%20%20")
        blank_endpoint = client.get(f"/v1/admin/schema/stripe/%20%20?agent_id={_BYPASS_AGENT_ID}")
        too_small = client.get("/v1/admin/schema/stripe/customers?limit=0")
        too_large = client.get("/v1/admin/schema/stripe/customers?limit=51")

        assert blank_service.status_code == 400
        blank_service_payload = blank_service.json()
        assert blank_service_payload["error"]["code"] == "INVALID_PARAMETERS"
        assert blank_service_payload["error"]["message"] == "Invalid 'service' path parameter."
        assert blank_service_payload["error"]["detail"] == "Provide a non-empty service id."
        assert invalid_service.status_code == 400
        invalid_service_payload = invalid_service.json()
        assert invalid_service_payload["error"]["code"] == "INVALID_PARAMETERS"
        assert invalid_service_payload["error"]["message"] == "Invalid 'service' path parameter."
        assert "stripe" in invalid_service_payload["error"]["detail"]
        assert blank_agent.status_code == 400
        blank_agent_payload = blank_agent.json()
        assert blank_agent_payload["error"]["code"] == "INVALID_PARAMETERS"
        assert blank_agent_payload["error"]["message"] == "Invalid 'agent_id' filter."
        assert (
            blank_agent_payload["error"]["detail"]
            == "Provide a non-empty agent_id value or omit the filter."
        )
        assert blank_endpoint.status_code == 400
        blank_endpoint_payload = blank_endpoint.json()
        assert blank_endpoint_payload["error"]["code"] == "INVALID_PARAMETERS"
        assert blank_endpoint_payload["error"]["message"] == "Invalid 'endpoint' filter."
        assert blank_endpoint_payload["error"]["detail"] == "Provide a non-empty endpoint path."
        assert too_small.status_code == 400
        too_small_payload = too_small.json()
        assert too_small_payload["error"]["code"] == "INVALID_PARAMETERS"
        assert too_small_payload["error"]["message"] == "Invalid 'limit' filter."
        assert too_small_payload["error"]["detail"] == "Provide an integer between 1 and 50."
        assert too_large.status_code == 400
        too_large_payload = too_large.json()
        assert too_large_payload["error"]["code"] == "INVALID_PARAMETERS"
        assert too_large_payload["error"]["message"] == "Invalid 'limit' filter."
        assert too_large_payload["error"]["detail"] == "Provide an integer between 1 and 50."

    def test_admin_schema_endpoint_trims_valid_endpoint(
        self, client: TestClient, httpx_mock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/trimmed-endpoint-schema",
            json={"id": "pi_1", "amount": 1000},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        client.post(
            "/v1/proxy/",
            json={"service": "stripe", "method": "GET", "path": "/trimmed-endpoint-schema"},
        )

        admin = client.get(
            f"/v1/admin/schema/stripe/%20trimmed-endpoint-schema%20?agent_id={_BYPASS_AGENT_ID}"
        )

        assert admin.status_code == 200
        data = admin.json()["data"]
        assert data["endpoint"] == "trimmed-endpoint-schema"
        assert data["latest_fingerprint"]["hash"] is not None

    def test_admin_schema_routes_accept_canonical_alias_backed_service_ids(
        self, client: TestClient, httpx_mock
    ) -> None:
        identity_store = proxy_module._identity_store
        assert identity_store is not None

        asyncio.run(identity_store.grant_service_access(_BYPASS_AGENT_ID, "pdl"))
        proxy_module._auth_injector_instance.credentials.set_credential(
            "pdl", "api_key", "pdl_test_vault"
        )

        httpx_mock.add_response(
            method="GET",
            url="https://api.peopledatalabs.com/v5/person/enrich",
            json={"status": 200, "data": {"name": "Acme", "email": "a@example.com"}},
            status_code=200,
            headers={"content-type": "application/json"},
        )
        httpx_mock.add_response(
            method="GET",
            url="https://api.peopledatalabs.com/v5/person/enrich",
            json={"status": 200, "data": {"name": "Acme"}},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        client.post(
            "/v1/proxy/",
            json={"service": "people-data-labs", "method": "GET", "path": "/v5/person/enrich"},
        )
        client.post(
            "/v1/proxy/",
            json={"service": "people-data-labs", "method": "GET", "path": "/v5/person/enrich"},
        )

        admin = client.get(
            f"/v1/admin/schema/people-data-labs/v5/person/enrich?agent_id={_BYPASS_AGENT_ID}"
        )
        assert admin.status_code == 200
        admin_data = admin.json()["data"]
        assert admin_data["service"] == "people-data-labs"
        assert all(event["service"] == "people-data-labs" for event in admin_data["events"])

        alerts = client.get("/v1/admin/schema-alerts?service=people-data-labs&limit=10")
        assert alerts.status_code == 200
        alert_payload = alerts.json()["data"]
        assert alert_payload["count"] >= 1
        assert all(alert["service"] == "people-data-labs" for alert in alert_payload["alerts"])
        assert all(
            alert["change_detail"]["service"] == "people-data-labs"
            for alert in alert_payload["alerts"]
            if isinstance(alert.get("change_detail"), dict) and alert["change_detail"].get("service")
        )

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
        # Auth enforcement: schema endpoint key prefixed with real agent_id, not "default"
        assert detail["endpoint"].startswith(f"{_BYPASS_AGENT_ID}:")
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

        admin = client.get(f"/v1/admin/schema/stripe/accounts?agent_id={_BYPASS_AGENT_ID}")
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

    @pytest.mark.skip(
        reason=(
            "Needs rework: GAP-1 auth enforcement ignores ProxyRequest.agent_id — "
            "agent identity comes from X-Rhumb-Key, not the request body. "
            "Multi-tenant isolation must be tested with two distinct registered "
            "agents and their API keys. Tracked as schema-isolation-test-rework."
        )
    )
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

    def test_admin_schema_alerts_normalize_public_service_alias_filter(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        class FakeAlertDispatcher:
            def query_alerts(self, **kwargs):
                captured.update(kwargs)
                return []

        monkeypatch.setattr(
            proxy_module,
            "get_schema_alert_dispatcher",
            lambda: FakeAlertDispatcher(),
        )

        response = client.get("/v1/admin/schema-alerts?service=%20BrAvE-Search-API%20")

        assert response.status_code == 200
        assert response.json()["data"]["count"] == 0
        assert captured["service"] == "brave-search"

    def test_admin_schema_alerts_reject_unknown_service_filter_before_read(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail_if_alert_store_opens():
            raise AssertionError("schema alert store opened before service validation")

        monkeypatch.setattr(proxy_module, "get_schema_alert_dispatcher", fail_if_alert_store_opens)

        response = client.get("/v1/admin/schema-alerts?service=unknown-service")

        assert response.status_code == 400
        payload = response.json()
        assert payload["error"]["code"] == "INVALID_PARAMETERS"
        assert payload["error"]["message"] == "Invalid 'service' filter."
        assert "brave-search-api" in payload["error"]["detail"]
        assert "people-data-labs" in payload["error"]["detail"]

    def test_admin_schema_alerts_normalize_valid_severity_filter(
        self, client: TestClient, httpx_mock
    ) -> None:
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/filter-alerts-normalized",
            json={"id": "1", "email": "a@example.com"},
            status_code=200,
            headers={"content-type": "application/json"},
        )
        httpx_mock.add_response(
            method="GET",
            url="https://api.stripe.com/filter-alerts-normalized",
            json={"id": "1"},
            status_code=200,
            headers={"content-type": "application/json"},
        )

        client.post(
            "/v1/proxy/",
            json={"service": "stripe", "method": "GET", "path": "/filter-alerts-normalized"},
        )
        client.post(
            "/v1/proxy/",
            json={"service": "stripe", "method": "GET", "path": "/filter-alerts-normalized"},
        )

        response = client.get("/v1/admin/schema-alerts?service=stripe&severity=%20BrEaKiNg%20")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["count"] >= 1
        assert all(alert["severity"] == "breaking" for alert in data["alerts"])

    def test_admin_schema_alerts_reject_invalid_severity_filter(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail_if_alert_store_opens():
            raise AssertionError("schema alert store opened before severity validation")

        monkeypatch.setattr(proxy_module, "get_schema_alert_dispatcher", fail_if_alert_store_opens)

        response = client.get("/v1/admin/schema-alerts?severity=offline")

        assert response.status_code == 400
        payload = response.json()
        assert payload["error"]["code"] == "INVALID_PARAMETERS"
        assert payload["error"]["message"] == "Invalid 'severity' filter."
        assert payload["error"]["detail"] == "Use one of: advisory, non_breaking, breaking."

    def test_admin_schema_alerts_reject_blank_filters_before_read(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail_if_alert_store_opens():
            raise AssertionError("schema alert store opened before filter validation")

        monkeypatch.setattr(proxy_module, "get_schema_alert_dispatcher", fail_if_alert_store_opens)

        blank_service = client.get("/v1/admin/schema-alerts?service=%20%20")
        blank_severity = client.get("/v1/admin/schema-alerts?severity=%20%20")

        assert blank_service.status_code == 400
        blank_service_payload = blank_service.json()
        assert blank_service_payload["error"]["code"] == "INVALID_PARAMETERS"
        assert blank_service_payload["error"]["message"] == "Invalid 'service' filter."
        assert (
            blank_service_payload["error"]["detail"]
            == "Provide a non-empty service value or omit the filter."
        )
        assert blank_severity.status_code == 400
        blank_severity_payload = blank_severity.json()
        assert blank_severity_payload["error"]["code"] == "INVALID_PARAMETERS"
        assert blank_severity_payload["error"]["message"] == "Invalid 'severity' filter."
        assert (
            blank_severity_payload["error"]["detail"]
            == "Provide a non-empty severity value or omit the filter."
        )

    def test_admin_schema_alerts_reject_invalid_limit_before_read(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail_if_alert_store_opens():
            raise AssertionError("schema alert store opened before limit validation")

        monkeypatch.setattr(proxy_module, "get_schema_alert_dispatcher", fail_if_alert_store_opens)

        too_small = client.get("/v1/admin/schema-alerts?limit=0")
        too_large = client.get("/v1/admin/schema-alerts?limit=101")

        assert too_small.status_code == 400
        too_small_payload = too_small.json()
        assert too_small_payload["error"]["code"] == "INVALID_PARAMETERS"
        assert too_small_payload["error"]["message"] == "Invalid 'limit' filter."
        assert too_small_payload["error"]["detail"] == "Provide an integer between 1 and 100."
        assert too_large.status_code == 400
        too_large_payload = too_large.json()
        assert too_large_payload["error"]["code"] == "INVALID_PARAMETERS"
        assert too_large_payload["error"]["message"] == "Invalid 'limit' filter."
        assert too_large_payload["error"]["detail"] == "Provide an integer between 1 and 100."
