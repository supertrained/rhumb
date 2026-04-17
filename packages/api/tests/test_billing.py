"""Round 12 billing and metering tests (WU 2.3)."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from app import create_app
from routes.admin_billing import set_test_billing_stores
from schemas.agent_identity import AgentIdentityStore, reset_identity_store
from services.agent_usage_analytics import AgentUsageAnalytics, reset_usage_analytics
from services.billing_aggregation import BillingAggregator, TAX_RATE, reset_billing_aggregator
from services.free_tier_quota import (
    FREE_TIER_LIMIT,
    FreeTierQuotaManager,
    reset_free_tier_quota_manager,
)
from services.spend_cap import (
    DEFAULT_MONTHLY_SPEND_CAP_USD,
    SpendCapManager,
    reset_spend_cap_manager,
)
from services.stripe_integration import (
    MockStripeClient,
    StripeIntegrationManager,
    reset_stripe_integration_manager,
)
from services.usage_metering import (
    COST_PER_CALL_USD,
    MeteredUsageEvent,
    UsageMeterEngine,
    reset_usage_meter_engine,
)


def _run(coro):  # type: ignore[no-untyped-def]
    """Run async test helper in a dedicated event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _seed_meter_events(
    usage_meter: UsageMeterEngine,
    agent_id: str,
    service: str,
    count: int,
    result: str = "success",
    latency_ms: float = 100.0,
    response_size_bytes: int = 500,
) -> None:
    """Seed in-memory meter events without async overhead."""
    now = datetime.now(tz=UTC)
    for _ in range(count):
        usage_meter._events.append(  # noqa: SLF001
            MeteredUsageEvent(
                event_id=str(uuid.uuid4()),
                agent_id=agent_id,
                service=service,
                result=result,
                latency_ms=latency_ms,
                response_size_bytes=response_size_bytes,
                created_at=now,
            )
        )


def _set_custom_attrs(
    identity_store: AgentIdentityStore,
    agent_id: str,
    attrs: dict[str, object],
) -> None:
    """Set custom attributes directly in in-memory identity store."""
    identity_store._mem_agents[agent_id]["custom_attributes"] = json.dumps(attrs)  # noqa: SLF001


@pytest.fixture(autouse=True)
def _reset_singletons() -> Generator[None, None, None]:
    """Reset singletons and route test stores between tests."""
    reset_identity_store()
    reset_usage_analytics()
    reset_usage_meter_engine()
    reset_spend_cap_manager()
    reset_free_tier_quota_manager()
    reset_billing_aggregator()
    reset_stripe_integration_manager()
    set_test_billing_stores(None, None, None)
    yield
    reset_identity_store()
    reset_usage_analytics()
    reset_usage_meter_engine()
    reset_spend_cap_manager()
    reset_free_tier_quota_manager()
    reset_billing_aggregator()
    reset_stripe_integration_manager()
    set_test_billing_stores(None, None, None)


@pytest.fixture
def identity_store() -> AgentIdentityStore:
    """In-memory identity store."""
    return AgentIdentityStore(supabase_client=None)


@pytest.fixture
def usage_analytics(identity_store: AgentIdentityStore) -> AgentUsageAnalytics:
    """In-memory usage analytics."""
    return AgentUsageAnalytics(identity_store=identity_store)


@pytest.fixture
def usage_meter(
    identity_store: AgentIdentityStore,
    usage_analytics: AgentUsageAnalytics,
) -> UsageMeterEngine:
    """In-memory usage meter engine."""
    return UsageMeterEngine(usage_analytics=usage_analytics, identity_store=identity_store)


@pytest.fixture
def spend_cap_manager(
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> SpendCapManager:
    """Spend cap manager fixture."""
    return SpendCapManager(usage_meter=usage_meter, identity_store=identity_store)


@pytest.fixture
def free_tier_manager(
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> FreeTierQuotaManager:
    """Free tier quota manager fixture."""
    return FreeTierQuotaManager(usage_meter=usage_meter, identity_store=identity_store)


@pytest.fixture
def billing_aggregator(usage_meter: UsageMeterEngine) -> BillingAggregator:
    """Billing aggregator fixture."""
    return BillingAggregator(usage_meter=usage_meter)


@pytest.fixture
def stripe_manager() -> StripeIntegrationManager:
    """Stripe integration fixture with mock client."""
    return StripeIntegrationManager(stripe_client=MockStripeClient())


@pytest.fixture
def admin_client(
    usage_meter: UsageMeterEngine,
    billing_aggregator: BillingAggregator,
    stripe_manager: StripeIntegrationManager,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """FastAPI client wired with billing test stores + admin auth."""
    monkeypatch.setenv("RHUMB_ADMIN_SECRET", "test-admin-secret")
    # Reload settings so the env var is picked up
    from config import settings as _settings
    _settings.rhumb_admin_secret = "test-admin-secret"
    set_test_billing_stores(usage_meter, billing_aggregator, stripe_manager)
    app = create_app()
    client = TestClient(app)
    client.headers["X-Rhumb-Admin-Key"] = "test-admin-secret"
    return client


def _register_agent(identity_store: AgentIdentityStore, organization_id: str = "org_1") -> str:
    """Register a test agent and return its agent_id."""
    agent_id, _ = _run(
        identity_store.register_agent(
            name="billing-agent",
            organization_id=organization_id,
        )
    )
    return agent_id


# ── Usage metering tests ─────────────────────────────────────────────


def test_record_metered_call_success(usage_meter: UsageMeterEngine, identity_store: AgentIdentityStore) -> None:
    agent_id = _register_agent(identity_store)
    _run(usage_meter.record_metered_call(agent_id, "openai", True, 120.0, 1024))

    summary = _run(usage_meter.get_monthly_usage(agent_id, datetime.now(tz=UTC).strftime("%Y-%m")))
    assert summary.total_calls == 1
    assert summary.cost_estimate == pytest.approx(0.001)


def test_record_metered_call_failure(usage_meter: UsageMeterEngine, identity_store: AgentIdentityStore) -> None:
    agent_id = _register_agent(identity_store)
    _run(usage_meter.record_metered_call(agent_id, "openai", False, 200.0, 512))

    snapshot = _run(usage_meter.get_usage_snapshot(agent_id, "openai", 7))
    assert snapshot is not None
    assert snapshot.failed_count == 1
    assert snapshot.success_count == 0


def test_usage_snapshot_single_service(
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store)
    _seed_meter_events(usage_meter, agent_id, "anthropic", 3, result="success", latency_ms=150.0)
    _seed_meter_events(usage_meter, agent_id, "anthropic", 1, result="error", latency_ms=350.0)
    _seed_meter_events(usage_meter, agent_id, "anthropic", 1, result="rate_limited", latency_ms=50.0)

    snapshot = _run(usage_meter.get_usage_snapshot(agent_id, "anthropic", 30))
    assert snapshot is not None
    assert snapshot.call_count == 5
    assert snapshot.success_count == 3
    assert snapshot.failed_count == 1
    assert snapshot.rate_limited_count == 1
    assert snapshot.avg_response_size_bytes == pytest.approx(500.0)


def test_usage_snapshot_empty_returns_none(
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store)
    snapshot = _run(usage_meter.get_usage_snapshot(agent_id, "openai", 7))
    assert snapshot is None


def test_monthly_usage_single_agent(
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store)
    _seed_meter_events(usage_meter, agent_id, "openai", 10)

    summary = _run(usage_meter.get_monthly_usage(agent_id, datetime.now(tz=UTC).strftime("%Y-%m")))
    assert summary.total_calls == 10
    assert summary.by_service["openai"].call_count == 10
    assert summary.cost_estimate == pytest.approx(0.01)


def test_monthly_usage_multiple_services(
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store)
    _seed_meter_events(usage_meter, agent_id, "openai", 3)
    _seed_meter_events(usage_meter, agent_id, "anthropic", 2)

    summary = _run(usage_meter.get_monthly_usage(agent_id, datetime.now(tz=UTC).strftime("%Y-%m")))
    assert summary.total_calls == 5
    assert summary.by_service["openai"].call_count == 3
    assert summary.by_service["anthropic"].call_count == 2


def test_org_monthly_usage_aggregation(
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_a = _register_agent(identity_store, "org_x")
    agent_b = _register_agent(identity_store, "org_x")
    _seed_meter_events(usage_meter, agent_a, "openai", 4)
    _seed_meter_events(usage_meter, agent_b, "openai", 6)

    org_summary = _run(
        usage_meter.get_org_monthly_usage("org_x", datetime.now(tz=UTC).strftime("%Y-%m"))
    )
    assert org_summary.total_calls == 10
    assert org_summary.by_service["openai"].call_count == 10
    assert len(org_summary.by_agent) == 2


def test_percentile_calculation(
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store)
    latencies = [100.0, 200.0, 300.0, 400.0, 500.0]
    for latency in latencies:
        _seed_meter_events(usage_meter, agent_id, "openai", 1, latency_ms=latency)

    snapshot = _run(usage_meter.get_usage_snapshot(agent_id, "openai", 7))
    assert snapshot is not None
    assert snapshot.p50_latency_ms == 300.0
    assert snapshot.p95_latency_ms == 500.0
    assert snapshot.p99_latency_ms == 500.0


# ── Spend cap tests ──────────────────────────────────────────────────


def test_spend_within_limit_no_alert(
    spend_cap_manager: SpendCapManager,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store)
    _set_custom_attrs(identity_store, agent_id, {"monthly_spend_cap_usd": 1.0})
    _seed_meter_events(usage_meter, agent_id, "openai", 100)

    allowed, alert = _run(spend_cap_manager.check_spend_cap(agent_id))
    assert allowed is True
    assert alert is None


def test_spend_at_80_percent_warning(
    spend_cap_manager: SpendCapManager,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store)
    _set_custom_attrs(identity_store, agent_id, {"monthly_spend_cap_usd": 0.01})
    _seed_meter_events(usage_meter, agent_id, "openai", 8)

    allowed, alert = _run(spend_cap_manager.check_spend_cap(agent_id))
    assert allowed is True
    assert alert is not None
    assert alert.alert_type == "warning"
    assert alert.percent_used == pytest.approx(80.0)


def test_spend_exceeds_limit_blocked(
    spend_cap_manager: SpendCapManager,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store)
    _set_custom_attrs(identity_store, agent_id, {"monthly_spend_cap_usd": 0.002})
    _seed_meter_events(usage_meter, agent_id, "openai", 3)

    allowed, alert = _run(spend_cap_manager.check_spend_cap(agent_id))
    assert allowed is False
    assert alert is not None
    assert alert.alert_type == "critical"


def test_default_spend_cap_100(
    spend_cap_manager: SpendCapManager,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store)
    allowed, alert = _run(spend_cap_manager.check_spend_cap(agent_id))

    assert allowed is True
    assert alert is None

    # Verify default constant is used by implementation contract.
    assert DEFAULT_MONTHLY_SPEND_CAP_USD == 100.0


def test_custom_spend_cap(
    spend_cap_manager: SpendCapManager,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store)
    _set_custom_attrs(identity_store, agent_id, {"monthly_spend_cap_usd": 2.0})
    _seed_meter_events(usage_meter, agent_id, "openai", 1500)

    allowed, alert = _run(spend_cap_manager.check_spend_cap(agent_id))
    assert allowed is True
    assert alert is None


# ── Free tier tests ──────────────────────────────────────────────────


def test_free_tier_active_no_stripe(
    free_tier_manager: FreeTierQuotaManager,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store)
    assert _run(free_tier_manager.is_free_tier(agent_id)) is True


def test_free_tier_always_blocked_when_limit_zero(
    free_tier_manager: FreeTierQuotaManager,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    """With FREE_TIER_LIMIT=0, any free-tier usage is blocked (no free executions)."""
    agent_id = _register_agent(identity_store)
    # Even zero usage should block because limit is 0
    allowed, remaining = _run(free_tier_manager.check_quota(agent_id))
    assert allowed is False
    assert remaining == 0


def test_free_tier_quota_exceeded_with_usage(
    free_tier_manager: FreeTierQuotaManager,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store)
    _seed_meter_events(usage_meter, agent_id, "openai", FREE_TIER_LIMIT + 10)

    allowed, remaining = _run(free_tier_manager.check_quota(agent_id))
    assert allowed is False
    assert remaining == 0


def test_paid_tier_bypasses_quota(
    free_tier_manager: FreeTierQuotaManager,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store)
    _set_custom_attrs(identity_store, agent_id, {"stripe_customer_id": "cus_test123"})
    _seed_meter_events(usage_meter, agent_id, "openai", FREE_TIER_LIMIT + 500)

    allowed, remaining = _run(free_tier_manager.check_quota(agent_id))
    assert allowed is True
    assert remaining == -1


# ── Billing tests ────────────────────────────────────────────────────


def test_generate_invoice_single_agent(
    billing_aggregator: BillingAggregator,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store, "org_bill")
    _seed_meter_events(usage_meter, agent_id, "openai", 10)

    invoice = _run(
        billing_aggregator.generate_invoice(
            organization_id="org_bill",
            month=datetime.now(tz=UTC).strftime("%Y-%m"),
        )
    )
    assert invoice.organization_id == "org_bill"
    assert invoice.subtotal == pytest.approx(0.01)


def test_generate_invoice_multiple_agents(
    billing_aggregator: BillingAggregator,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_a = _register_agent(identity_store, "org_multi")
    agent_b = _register_agent(identity_store, "org_multi")
    _seed_meter_events(usage_meter, agent_a, "openai", 5)
    _seed_meter_events(usage_meter, agent_b, "openai", 7)

    invoice = _run(
        billing_aggregator.generate_invoice("org_multi", datetime.now(tz=UTC).strftime("%Y-%m"))
    )
    assert invoice.subtotal == pytest.approx(0.012)


def test_invoice_line_items_by_service(
    billing_aggregator: BillingAggregator,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store, "org_line")
    _seed_meter_events(usage_meter, agent_id, "openai", 3)
    _seed_meter_events(usage_meter, agent_id, "anthropic", 2)

    invoice = _run(
        billing_aggregator.generate_invoice("org_line", datetime.now(tz=UTC).strftime("%Y-%m"))
    )
    by_service = {line.service: line for line in invoice.line_items}
    assert by_service["openai"].call_count == 3
    assert by_service["anthropic"].call_count == 2


def test_invoice_line_items_canonicalize_alias_backed_service_ids(
    billing_aggregator: BillingAggregator,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store, "org_line_alias")
    _seed_meter_events(usage_meter, agent_id, "brave-search", 2)
    _seed_meter_events(usage_meter, agent_id, "brave-search-api", 1)

    invoice = _run(
        billing_aggregator.generate_invoice(
            "org_line_alias", datetime.now(tz=UTC).strftime("%Y-%m")
        )
    )
    by_service = {line.service: line for line in invoice.line_items}
    assert by_service["brave-search-api"].call_count == 3
    assert "brave-search" not in by_service


def test_invoice_tax_calculation(
    billing_aggregator: BillingAggregator,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store, "org_tax")
    _seed_meter_events(usage_meter, agent_id, "openai", 100)

    invoice = _run(
        billing_aggregator.generate_invoice("org_tax", datetime.now(tz=UTC).strftime("%Y-%m"))
    )
    assert invoice.tax == pytest.approx(invoice.subtotal * TAX_RATE)
    assert invoice.total == pytest.approx(invoice.subtotal + invoice.tax)


def test_invoice_stored_as_draft(
    billing_aggregator: BillingAggregator,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store, "org_draft")
    _seed_meter_events(usage_meter, agent_id, "openai", 1)

    invoice = _run(
        billing_aggregator.generate_invoice("org_draft", datetime.now(tz=UTC).strftime("%Y-%m"))
    )
    listed = billing_aggregator.list_invoices("org_draft")
    assert invoice.status == "draft"
    assert len(listed) == 1
    assert listed[0].invoice_id == invoice.invoice_id


# ── Stripe tests (mock only) ────────────────────────────────────────


def test_create_stripe_customer(stripe_manager: StripeIntegrationManager) -> None:
    customer_id = stripe_manager.create_or_get_customer("org_1", "Acme", "ops@acme.ai")
    assert customer_id.startswith("cus_")


def test_get_existing_customer(stripe_manager: StripeIntegrationManager) -> None:
    first = stripe_manager.create_or_get_customer("org_1", "Acme", "ops@acme.ai")
    second = stripe_manager.create_or_get_customer("org_1", "Acme", "ops@acme.ai")
    assert first == second


def test_create_payment_intent(stripe_manager: StripeIntegrationManager) -> None:
    intent = stripe_manager.create_payment_intent("org_1", 1234, "inv_1")
    assert intent["payment_intent_id"].startswith("pi_")
    assert "client_secret" in intent


def test_confirm_payment_success(stripe_manager: StripeIntegrationManager) -> None:
    intent = stripe_manager.create_payment_intent("org_1", 500, "inv_2")
    ok = stripe_manager.confirm_payment(intent["payment_intent_id"])
    assert ok is True


def test_confirm_payment_failure(stripe_manager: StripeIntegrationManager) -> None:
    ok = stripe_manager.confirm_payment("pi_missing")
    assert ok is False


# ── Admin route tests ────────────────────────────────────────────────


def test_get_usage_report(
    admin_client: TestClient,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store, "org_route_usage")
    _seed_meter_events(usage_meter, agent_id, "openai", 9)

    month = datetime.now(tz=UTC).strftime("%Y-%m")
    response = admin_client.get(
        "/v1/admin/billing/usage",
        params={"organization_id": "org_route_usage", "month": month},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_calls"] == 9


def test_get_usage_report_canonicalizes_alias_backed_service_ids(
    admin_client: TestClient,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store, "org_route_usage_alias")
    _seed_meter_events(usage_meter, agent_id, "pdl", 2)
    _seed_meter_events(usage_meter, agent_id, "people-data-labs", 1)

    month = datetime.now(tz=UTC).strftime("%Y-%m")
    response = admin_client.get(
        "/v1/admin/billing/usage",
        params={"organization_id": "org_route_usage_alias", "month": month},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["by_service"]["people-data-labs"]["call_count"] == 3
    assert "pdl" not in payload["by_service"]


def test_list_invoices_empty(admin_client: TestClient) -> None:
    response = admin_client.get(
        "/v1/admin/billing/invoices",
        params={"organization_id": "org_empty"},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_generate_invoice_endpoint(
    admin_client: TestClient,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store, "org_generate")
    _seed_meter_events(usage_meter, agent_id, "openai", 4)

    month = datetime.now(tz=UTC).strftime("%Y-%m")
    response = admin_client.post(
        "/v1/admin/billing/invoices/generate",
        json={"organization_id": "org_generate", "month": month},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "draft"
    assert payload["subtotal"] == pytest.approx(4 * COST_PER_CALL_USD)


def test_send_invoice_endpoint(
    admin_client: TestClient,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store, "org_send")
    _seed_meter_events(usage_meter, agent_id, "openai", 3)

    month = datetime.now(tz=UTC).strftime("%Y-%m")
    generate = admin_client.post(
        "/v1/admin/billing/invoices/generate",
        json={"organization_id": "org_send", "month": month},
    )
    invoice_id = generate.json()["invoice_id"]

    send = admin_client.post(f"/v1/admin/billing/invoices/{invoice_id}/send")
    assert send.status_code == 200
    payload = send.json()
    assert payload["status"] == "sent"
    assert payload["payment_intent"]["payment_intent_id"].startswith("pi_")


def test_forecast_spend(
    admin_client: TestClient,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store, "org_forecast")
    _seed_meter_events(usage_meter, agent_id, "openai", 14)

    response = admin_client.get(
        "/v1/admin/billing/forecast",
        params={"organization_id": "org_forecast"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["window_calls"] == 14
    assert payload["projected_monthly_spend"] == pytest.approx((14 / 7) * 30 * COST_PER_CALL_USD)


# ── E2E integration tests ────────────────────────────────────────────


def test_e2e_free_tier_to_paid_upgrade(
    free_tier_manager: FreeTierQuotaManager,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store, "org_upgrade")
    _seed_meter_events(usage_meter, agent_id, "openai", FREE_TIER_LIMIT)

    allowed, remaining = _run(free_tier_manager.check_quota(agent_id))
    assert allowed is False
    assert remaining == 0

    _set_custom_attrs(identity_store, agent_id, {"stripe_customer_id": "cus_upgraded"})
    allowed_after, remaining_after = _run(free_tier_manager.check_quota(agent_id))
    assert allowed_after is True
    assert remaining_after == -1


def test_e2e_spend_cap_blocks_at_limit(
    spend_cap_manager: SpendCapManager,
    usage_meter: UsageMeterEngine,
    identity_store: AgentIdentityStore,
) -> None:
    agent_id = _register_agent(identity_store, "org_cap")
    _set_custom_attrs(identity_store, agent_id, {"monthly_spend_cap_usd": 0.003})
    _seed_meter_events(usage_meter, agent_id, "openai", 4)

    allowed, alert = _run(spend_cap_manager.check_spend_cap(agent_id))
    assert allowed is False
    assert alert is not None
    assert alert.alert_type == "critical"
