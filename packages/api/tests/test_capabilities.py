"""Tests for capability registry routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app


@pytest.fixture
def app():
    """Create test app with lifespan disabled."""
    application = create_app()
    return application


# ── Sample data ──────────────────────────────────────────────

SAMPLE_CAPABILITIES = [
    {"id": "email.send", "domain": "email", "action": "send",
     "description": "Send transactional or marketing email",
     "input_hint": "recipient, subject, body", "outcome": "Email delivered"},
    {"id": "email.verify", "domain": "email", "action": "verify",
     "description": "Verify an email address is valid",
     "input_hint": "email_address", "outcome": "Verification result"},
    {"id": "payment.charge", "domain": "payment", "action": "charge",
     "description": "Process a one-time payment",
     "input_hint": "amount, currency, payment_method", "outcome": "Payment captured"},
]

SAMPLE_MAPPINGS = [
    {"capability_id": "email.send", "service_slug": "sendgrid",
     "credential_modes": ["byo"], "auth_method": "api_key",
     "endpoint_pattern": "POST /v3/mail/send", "cost_per_call": "0.001",
     "cost_currency": "USD", "free_tier_calls": 100, "notes": None, "is_primary": True},
    {"capability_id": "email.send", "service_slug": "resend",
     "credential_modes": ["byo"], "auth_method": "api_key",
     "endpoint_pattern": "POST /emails", "cost_per_call": None,
     "cost_currency": "USD", "free_tier_calls": 100, "notes": None, "is_primary": True},
]

SAMPLE_SCORES = [
    {"service_slug": "resend", "aggregate_recommendation_score": 7.79,
     "execution_score": 8.5, "access_readiness_score": 7.0,
     "tier": "L3", "tier_label": "Ready", "confidence": 0.8},
    {"service_slug": "sendgrid", "aggregate_recommendation_score": 6.35,
     "execution_score": 7.0, "access_readiness_score": 5.5,
     "tier": "L3", "tier_label": "Ready", "confidence": 0.7},
]

SAMPLE_SERVICES = [
    {"slug": "sendgrid", "name": "SendGrid", "category": "email"},
    {"slug": "resend", "name": "Resend", "category": "email"},
]

SAMPLE_BUNDLES = [
    {"id": "prospect.enrich_and_verify", "name": "Prospect Enrichment + Verification",
     "description": "Find prospect data and verify contact information",
     "example": "Given a LinkedIn URL, get verified email + phone",
     "value_proposition": "One call instead of three"},
]

SAMPLE_BUNDLE_CAPS = [
    {"bundle_id": "prospect.enrich_and_verify", "capability_id": "data.enrich_person", "sequence_order": 1},
    {"bundle_id": "prospect.enrich_and_verify", "capability_id": "email.verify", "sequence_order": 2},
]

INTENT_CAPABILITIES = [
    {
        "id": "scrape.extract",
        "domain": "scrape",
        "action": "extract",
        "description": "Extract structured data from a web page URL",
        "input_hint": "url, schema",
        "outcome": "Structured website data",
    },
    {
        "id": "ai.generate_image",
        "domain": "ai",
        "action": "generate_image",
        "description": "Generate an image from a text prompt",
        "input_hint": "prompt",
        "outcome": "Generated image",
    },
    {
        "id": "data.enrich_person",
        "domain": "data",
        "action": "enrich_person",
        "description": "Enrich a person profile with professional data",
        "input_hint": "linkedin_url or email",
        "outcome": "Professional profile enrichment",
    },
    {
        "id": "audit.query",
        "domain": "audit",
        "action": "query",
        "description": "Query audit log entries",
        "input_hint": "filters, limit",
        "outcome": "Audit events",
    },
    {
        "id": "crm.query",
        "domain": "crm",
        "action": "query",
        "description": "Query CRM records",
        "input_hint": "object, filters",
        "outcome": "CRM rows",
    },
    {
        "id": "data_warehouse.query",
        "domain": "data_warehouse",
        "action": "query",
        "description": "Query a warehouse table with SQL",
        "input_hint": "sql, warehouse, filters",
        "outcome": "Warehouse rows",
    },
    {
        "id": "db.query.read",
        "domain": "database",
        "action": "query_read",
        "description": "Execute a read-only SQL query against a PostgreSQL database",
        "input_hint": "connection_ref, query, params",
        "outcome": "Database rows",
    },
]

DB_DIRECT_CAPABILITY = {
    "id": "db.query.read",
    "domain": "database",
    "action": "query_read",
    "description": "Execute a read-only SQL query against a PostgreSQL database",
    "input_hint": "connection_ref, query, params (optional), max_rows, timeout_ms",
    "outcome": "Query results: column metadata + rows, bounded by row limit and timeout",
}

OBJECT_STORAGE_DIRECT_CAPABILITIES = [
    {
        "id": "object.list",
        "domain": "object",
        "action": "list",
        "description": "List objects in an allowlisted AWS S3 bucket or prefix",
        "input_hint": "storage_ref, bucket, prefix (optional)",
        "outcome": "Object metadata list",
    },
    {
        "id": "object.head",
        "domain": "object",
        "action": "head",
        "description": "Fetch metadata for an allowlisted object in AWS S3",
        "input_hint": "storage_ref, bucket, key",
        "outcome": "Object metadata",
    },
    {
        "id": "object.get",
        "domain": "object",
        "action": "get",
        "description": "Fetch a bounded object body from AWS S3",
        "input_hint": "storage_ref, bucket, key, max_bytes",
        "outcome": "Bounded object body as text/base64",
    },
]

CRM_DIRECT_CAPABILITY = {
    "id": "crm.record.search",
    "domain": "crm",
    "action": "record.search",
    "description": "Search HubSpot CRM records with explicit object and property scope",
    "input_hint": "crm_ref, object_type, property_names (optional), filters (optional), sorts (optional)",
    "outcome": "CRM record summaries",
}


def _mock_supabase(path: str):
    """Route supabase_fetch calls to sample data based on table name."""
    if path.startswith("capabilities?"):
        if "domain=eq.email" in path:
            return [c for c in SAMPLE_CAPABILITIES if c["domain"] == "email"]
        if "id=eq.email.send" in path:
            return [SAMPLE_CAPABILITIES[0]]
        if "id=eq.nonexistent" in path:
            return []
        return SAMPLE_CAPABILITIES
    if path.startswith("capability_services?"):
        if "capability_id=eq.email.send" in path:
            return SAMPLE_MAPPINGS
        if "capability_id=in." in path:
            return SAMPLE_MAPPINGS
        if "select=capability_id,service_slug" in path:
            return SAMPLE_MAPPINGS
        return []
    if path.startswith("scores?"):
        return SAMPLE_SCORES
    if path.startswith("services?"):
        return SAMPLE_SERVICES
    if path.startswith("capability_bundles?"):
        return SAMPLE_BUNDLES
    if path.startswith("bundle_capabilities?"):
        return SAMPLE_BUNDLE_CAPS
    return []


def _mock_intent_supabase(path: str):
    if path.startswith("capabilities?"):
        return INTENT_CAPABILITIES
    if path.startswith("capability_services?"):
        return []
    if path.startswith("scores?"):
        return []
    if path.startswith("services?"):
        return []
    return []


def _mock_db_direct_supabase(path: str):
    if path.startswith("capabilities?"):
        if "id=eq.db.query.read" in path:
            return [DB_DIRECT_CAPABILITY]
        return [DB_DIRECT_CAPABILITY]
    if path.startswith("capability_services?"):
        return []
    if path.startswith("scores?"):
        return []
    if path.startswith("services?"):
        return []
    if path.startswith("bundle_capabilities?"):
        return []
    return []


def _mock_object_storage_direct_supabase(path: str):
    if path.startswith("capabilities?"):
        if "id=eq.object.list" in path:
            return [OBJECT_STORAGE_DIRECT_CAPABILITIES[0]]
        if "id=eq.object.head" in path:
            return [OBJECT_STORAGE_DIRECT_CAPABILITIES[1]]
        if "id=eq.object.get" in path:
            return [OBJECT_STORAGE_DIRECT_CAPABILITIES[2]]
        return list(OBJECT_STORAGE_DIRECT_CAPABILITIES)
    if path.startswith("capability_services?"):
        return []
    if path.startswith("scores?"):
        return []
    if path.startswith("services?"):
        return []
    if path.startswith("bundle_capabilities?"):
        return []
    return []


def _mock_crm_direct_supabase(path: str):
    if path.startswith("capabilities?"):
        if "id=eq.crm.record.search" in path:
            return [CRM_DIRECT_CAPABILITY]
        return [CRM_DIRECT_CAPABILITY]
    if path.startswith("capability_services?"):
        return []
    if path.startswith("scores?"):
        return []
    if path.startswith("services?"):
        return []
    if path.startswith("bundle_capabilities?"):
        return []
    return []


def _mock_support_direct_supabase(path: str):
    support_capability = {
        "id": "ticket.search",
        "domain": "support",
        "action": "search",
        "description": "Search support tickets",
        "input_hint": "support_ref, query",
        "outcome": "Ticket summaries",
    }
    if path.startswith("capabilities?"):
        if "id=eq.ticket.search" in path:
            return [support_capability]
        return [support_capability]
    if path.startswith("capability_services?"):
        return [
            {
                "capability_id": "ticket.search",
                "service_slug": "intercom",
                "credential_modes": ["byo"],
                "auth_method": "oauth",
                "endpoint_pattern": "/proxy/intercom",
                "cost_per_call": None,
                "cost_currency": "USD",
                "free_tier_calls": None,
                "notes": "generic",
                "is_primary": False,
            },
            {
                "capability_id": "ticket.search",
                "service_slug": "zendesk",
                "credential_modes": ["byo"],
                "auth_method": "api_token",
                "endpoint_pattern": "/proxy/zendesk",
                "cost_per_call": None,
                "cost_currency": "USD",
                "free_tier_calls": None,
                "notes": "generic",
                "is_primary": True,
            },
        ]
    if path.startswith("scores?"):
        return []
    if path.startswith("services?"):
        return []
    if path.startswith("bundle_capabilities?"):
        return []
    return []


class _FakeBreaker:
    def __init__(self, state: str, *, allowed: bool):
        self.state = type("State", (), {"value": state})()
        self._allowed = allowed

    def allow_request(self) -> bool:
        return self._allowed


class _FakeBreakerRegistry:
    def __init__(self, breaker_states: dict[str, tuple[str, bool]]):
        self._breaker_states = breaker_states

    def get(self, service: str, agent_id: str = "default") -> _FakeBreaker:
        state, allowed = self._breaker_states.get(service, ("closed", True))
        return _FakeBreaker(state, allowed=allowed)


# ── Tests ──────────────────────────────────────────────────

@pytest.mark.anyio
async def test_list_capabilities(app):
    """GET /v1/capabilities returns paginated capability list with provider info."""
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 3
    assert len(data["items"]) >= 3

    item = next(i for i in data["items"] if i["id"] == "email.send")
    assert item["domain"] == "email"
    assert "provider_count" in item
    assert "top_provider" in item


@pytest.mark.anyio
async def test_list_capabilities_domain_filter(app):
    """GET /v1/capabilities?domain=email filters by domain."""
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities?domain=email")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 2
    for item in data["items"]:
        assert item["domain"] == "email"


@pytest.mark.anyio
async def test_list_capabilities_intent_search_matches_spaced_queries(app):
    """Intent-style searches should match dotted/underscored capability IDs."""
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_intent_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities?search=generate%20image")
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert items
    assert items[0]["id"] == "ai.generate_image"


@pytest.mark.anyio
async def test_list_capabilities_intent_search_matches_tool_name_aliases(app):
    """Tool-name queries should map back to capabilities instead of requiring provider/model literacy."""
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_intent_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities?search=Nano%20Banana%20Pro")

    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert items
    assert items[0]["id"] == "ai.generate_image"


@pytest.mark.anyio
async def test_list_capabilities_intent_search_matches_synonyms(app):
    """Intent-style searches should bridge common agent language like website/LinkedIn."""
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_intent_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            scrape_resp = await client.get("/v1/capabilities?search=scrape%20website")
            person_resp = await client.get("/v1/capabilities?search=search%20person%20linkedin")

    scrape_items = scrape_resp.json()["data"]["items"]
    person_items = person_resp.json()["data"]["items"]

    assert scrape_items
    assert scrape_items[0]["id"] == "scrape.extract"
    assert person_items
    assert person_items[0]["id"] == "data.enrich_person"


@pytest.mark.anyio
async def test_list_capabilities_intent_search_prefers_postgres_query_for_db_read(app):
    """Intent search should rank the DB direct wedge above generic query capabilities."""
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_intent_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities?search=postgres%20query")

    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert items
    assert items[0]["id"] == "db.query.read"


@pytest.mark.anyio
async def test_get_capability(app):
    """GET /v1/capabilities/email.send returns capability with providers."""
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/email.send")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == "email.send"
    assert data["provider_count"] == 2
    assert len(data["providers"]) == 2
    # Providers should be sorted by AN score descending
    scores = [p["an_score"] for p in data["providers"] if p["an_score"] is not None]
    assert scores == sorted(scores, reverse=True)
    assert all(provider["credential_modes"] == ["byok"] for provider in data["providers"])


@pytest.mark.anyio
async def test_get_capability_not_found(app):
    """GET /v1/capabilities/nonexistent returns 404 with standardized envelope."""
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/nonexistent")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "capability_not_found"
    assert "nonexistent" in body["message"]
    assert "resolution" in body
    assert body["search_url"] == "/v1/capabilities?search=nonexistent"


@pytest.mark.anyio
async def test_get_capability_not_found_suggests_capability_for_tool_alias(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?id=eq."):
            return []
        return _mock_intent_supabase(path)

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/Nano%20Banana%20Pro")

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "capability_not_found"
    assert body["search_url"] == "/v1/capabilities?search=Nano%20Banana%20Pro"
    assert body["suggested_capabilities"][0]["id"] == "ai.generate_image"


@pytest.mark.anyio
async def test_list_capabilities_search_matches_provider_alias(app):
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities", params={"search": "resend"})

    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert items[0]["id"] == "email.send"


@pytest.mark.anyio
async def test_get_capability_not_found_suggests_capability_for_provider_alias(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?id=eq.Resend"):
            return []
        return _mock_supabase(path)

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/Resend")

    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "capability_not_found"
    assert body["search_url"] == "/v1/capabilities?search=Resend"
    assert body["suggested_capabilities"][0]["id"] == "email.send"


@pytest.mark.anyio
async def test_resolve_capability(app):
    """GET /v1/capabilities/email.send/resolve returns ranked providers with recommendations."""
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/email.send/resolve")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["capability"] == "email.send"
    assert len(data["providers"]) == 2
    assert len(data["fallback_chain"]) >= 1
    # First provider should be preferred (highest score)
    first = data["providers"][0]
    assert first["service_slug"] == "resend"
    assert first["recommendation"] == "preferred"
    assert first["credential_modes"] == ["byok"]
    assert data["execute_hint"]["auth_method"] == "api_key"
    assert data["execute_hint"]["configured"] is False
    assert data["execute_hint"]["credential_modes"] == ["byok"]
    assert data["execute_hint"]["credential_modes_url"] == "/v1/capabilities/email.send/credential-modes"
    assert data["execute_hint"]["preferred_credential_mode"] == "byok"
    assert data["execute_hint"]["selection_reason"] == "highest_ranked_provider"
    assert data["execute_hint"]["fallback_providers"] == ["sendgrid"]
    assert "RHUMB_CREDENTIAL_RESEND_API_KEY" in data["execute_hint"]["setup_hint"]
    assert data["related_bundles"] == ["prospect.enrich_and_verify"]
    assert "recommendation_reason" in first


@pytest.mark.anyio
async def test_resolve_capability_accepts_byok_alias_for_byo_mappings(app):
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/resolve",
                params={"credential_mode": "byok"},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [provider["service_slug"] for provider in data["providers"]] == ["resend", "sendgrid"]
    assert all(provider["credential_modes"] == ["byok"] for provider in data["providers"])
    assert data["execute_hint"]["preferred_provider"] == "resend"
    assert data["execute_hint"]["preferred_credential_mode"] == "byok"
    assert "RHUMB_CREDENTIAL_RESEND_API_KEY" in data["execute_hint"]["setup_hint"]


@pytest.mark.anyio
async def test_resolve_capability_empty_filter_keeps_resolve_contract(app):
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/resolve",
                params={"credential_mode": "agent_vault"},
            )

    assert resp.status_code == 200
    assert resp.json()["data"] == {
        "capability": "email.send",
        "providers": [],
        "fallback_chain": [],
        "related_bundles": [],
        "execute_hint": None,
        "recovery_hint": {
            "reason": "no_providers_match_credential_mode",
            "requested_credential_mode": "agent_vault",
            "resolve_url": "/v1/capabilities/email.send/resolve",
            "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
            "supported_provider_slugs": ["resend", "sendgrid"],
            "supported_credential_modes": ["byok"],
            "alternate_execute_hint": {
                "preferred_provider": "resend",
                "endpoint_pattern": "POST /emails",
                "estimated_cost_usd": None,
                "auth_method": "api_key",
                "credential_modes": ["byok"],
                "configured": False,
                "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
                "preferred_credential_mode": "byok",
                "setup_hint": "Set RHUMB_CREDENTIAL_RESEND_API_KEY environment variable or configure via proxy credentials",
                "selection_reason": "highest_ranked_provider",
                "fallback_providers": ["sendgrid"],
            },
        },
    }


@pytest.mark.anyio
async def test_resolve_capability_empty_filter_recovery_includes_execute_blockers(app):
    fake_breakers = _FakeBreakerRegistry({
        "resend": ("open", False),
        "sendgrid": ("closed", True),
    })

    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [{
                "id": "email.send",
                "domain": "email",
                "action": "send",
                "description": "Send email",
            }]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "sendgrid",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": None,
                    "cost_per_call": "0.001",
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
                {
                    "service_slug": "resend",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": None,
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
            ]
        if path.startswith("scores?"):
            return [
                {
                    "service_slug": "resend",
                    "aggregate_recommendation_score": 7.79,
                    "execution_score": 8.5,
                    "access_readiness_score": 7.0,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.8,
                },
                {
                    "service_slug": "sendgrid",
                    "aggregate_recommendation_score": 6.35,
                    "execution_score": 7.0,
                    "access_readiness_score": 5.5,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.7,
                },
            ]
        if path.startswith("services?"):
            return [
                {"slug": "sendgrid", "name": "SendGrid"},
                {"slug": "resend", "name": "Resend"},
            ]
        if path.startswith("bundle_capabilities?"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch), patch(
        "routes.proxy.get_breaker_registry",
        return_value=fake_breakers,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/resolve",
                params={"credential_mode": "agent_vault"},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["providers"] == []
    assert data["fallback_chain"] == []
    assert data["execute_hint"] is None
    recovery_hint = data["recovery_hint"]
    assert recovery_hint["reason"] == "no_providers_match_credential_mode"
    assert recovery_hint["requested_credential_mode"] == "agent_vault"
    assert recovery_hint["resolve_url"] == "/v1/capabilities/email.send/resolve"
    assert recovery_hint["credential_modes_url"] == "/v1/capabilities/email.send/credential-modes"
    assert recovery_hint["supported_provider_slugs"] == ["resend", "sendgrid"]
    assert recovery_hint["supported_credential_modes"] == ["byok"]
    assert recovery_hint["unavailable_provider_slugs"] == ["resend"]
    assert recovery_hint["not_execute_ready_provider_slugs"] == ["resend", "sendgrid"]
    assert recovery_hint["setup_handoff"] == {
        "preferred_provider": "sendgrid",
        "estimated_cost_usd": 0.001,
        "auth_method": "api_key",
        "credential_modes": ["byok"],
        "configured": False,
        "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
        "preferred_credential_mode": "byok",
        "setup_hint": "Set RHUMB_CREDENTIAL_SENDGRID_API_KEY environment variable or configure via proxy credentials",
        "selection_reason": "higher_ranked_provider_filtered_by_credential_mode",
        "skipped_provider_slugs": ["resend"],
        "unavailable_provider_slugs": ["resend"],
        "not_execute_ready_provider_slugs": ["resend"],
    }
    assert "alternate_execute_hint" not in recovery_hint


@pytest.mark.anyio
async def test_resolve_capability_filtered_execute_hint_marks_higher_ranked_filtered_provider(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [{
                "id": "email.send",
                "domain": "email",
                "action": "send",
                "description": "Send email",
            }]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "resend",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "POST /emails",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
                {
                    "service_slug": "gmail",
                    "credential_modes": ["agent_vault"],
                    "auth_method": "oauth",
                    "endpoint_pattern": "POST /gmail/v1/users/me/messages/send",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": None,
                    "notes": None,
                },
            ]
        if path.startswith("scores?"):
            return [
                {
                    "service_slug": "resend",
                    "aggregate_recommendation_score": 8.8,
                    "execution_score": 8.6,
                    "access_readiness_score": 8.7,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.92,
                },
                {
                    "service_slug": "gmail",
                    "aggregate_recommendation_score": 7.2,
                    "execution_score": 7.2,
                    "access_readiness_score": 7.0,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.9,
                },
            ]
        if path.startswith("services?"):
            return [
                {"slug": "resend", "name": "Resend"},
                {"slug": "gmail", "name": "Gmail"},
            ]
        if path.startswith("bundle_capabilities?"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/resolve",
                params={"credential_mode": "agent_vault"},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [provider["service_slug"] for provider in data["providers"]] == ["gmail"]
    assert data["fallback_chain"] == ["gmail"]
    assert data["execute_hint"]["preferred_provider"] == "gmail"
    assert data["execute_hint"]["preferred_credential_mode"] == "agent_vault"
    assert data["execute_hint"]["selection_reason"] == "higher_ranked_provider_filtered_by_credential_mode"
    assert data["execute_hint"]["skipped_provider_slugs"] == ["resend"]
    assert "fallback_providers" not in data["execute_hint"]


@pytest.mark.anyio
async def test_resolve_capability_agent_vault_hint_links_to_setup_surface(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [{
                "id": "email.send",
                "domain": "email",
                "action": "send",
                "description": "Send email",
            }]
        if path.startswith("capability_services?"):
            return [{
                "service_slug": "gmail",
                "credential_modes": ["agent_vault"],
                "auth_method": "oauth",
                "endpoint_pattern": "POST /gmail/v1/users/me/messages/send",
                "cost_per_call": None,
                "cost_currency": "USD",
                "free_tier_calls": None,
                "notes": None,
            }]
        if path.startswith("scores?"):
            return [{
                "service_slug": "gmail",
                "aggregate_recommendation_score": 7.8,
                "execution_score": 7.8,
                "access_readiness_score": 7.4,
                "tier": "L3",
                "tier_label": "Ready",
                "confidence": 0.85,
            }]
        if path.startswith("services?"):
            return [{"slug": "gmail", "name": "Gmail"}]
        if path.startswith("bundle_capabilities?"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/email.send/resolve")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["execute_hint"]["preferred_provider"] == "gmail"
    assert data["execute_hint"]["preferred_credential_mode"] == "agent_vault"
    assert data["execute_hint"]["credential_modes_url"] == "/v1/capabilities/email.send/credential-modes"
    assert data["execute_hint"]["setup_url"] == "/v1/services/gmail/ceremony"
    assert "/v1/services/gmail/ceremony" in data["execute_hint"]["setup_hint"]


@pytest.mark.anyio
async def test_resolve_capability_marks_rhumb_managed_provider_configured(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [{
                "id": "ai.generate_text",
                "domain": "ai",
                "action": "generate_text",
                "description": "Generate text",
            }]
        if path.startswith("capability_services?"):
            return [{
                "service_slug": "anthropic",
                "credential_modes": ["rhumb_managed", "byo"],
                "auth_method": "api_key",
                "endpoint_pattern": "POST /v1/messages",
                "cost_per_call": None,
                "cost_currency": "USD",
                "free_tier_calls": None,
                "notes": None,
            }]
        if path.startswith("scores?"):
            return [{
                "service_slug": "anthropic",
                "aggregate_recommendation_score": 8.5,
                "execution_score": 8.5,
                "access_readiness_score": 8.5,
                "tier": "L4",
                "tier_label": "Native",
                "confidence": 0.9,
            }]
        if path.startswith("services?"):
            return [{"slug": "anthropic", "name": "Anthropic"}]
        if path.startswith("bundle_capabilities?"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/ai.generate_text/resolve")
            byok_resp = await client.get(
                "/v1/capabilities/ai.generate_text/resolve",
                params={"credential_mode": "byok"},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["providers"][0]["credential_modes"] == ["rhumb_managed", "byok"]
    assert data["providers"][0]["configured"] is True
    assert data["execute_hint"]["auth_method"] == "api_key"
    assert data["execute_hint"]["configured"] is True
    assert data["execute_hint"]["credential_modes"] == ["rhumb_managed", "byok"]
    assert data["execute_hint"]["preferred_credential_mode"] == "rhumb_managed"
    assert "setup_hint" not in data["execute_hint"]

    byok_data = byok_resp.json()["data"]
    assert byok_data["providers"][0]["credential_modes"] == ["rhumb_managed", "byok"]
    assert byok_data["providers"][0]["configured"] is False
    assert byok_data["execute_hint"]["configured"] is False
    assert byok_data["execute_hint"]["preferred_credential_mode"] == "byok"
    assert "RHUMB_CREDENTIAL_ANTHROPIC_API_KEY" in byok_data["execute_hint"]["setup_hint"]


@pytest.mark.anyio
async def test_resolve_capability_filtered_mode_does_not_prefer_provider_configured_only_in_other_mode(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [{
                "id": "email.send",
                "domain": "email",
                "action": "send",
                "description": "Send email",
            }]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "resend",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "POST /emails",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
                {
                    "service_slug": "rhumb-managed-email",
                    "credential_modes": ["rhumb_managed", "byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "POST /v1/rhumb-managed/email/send",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": None,
                    "notes": None,
                },
            ]
        if path.startswith("scores?"):
            return [
                {
                    "service_slug": "resend",
                    "aggregate_recommendation_score": 8.8,
                    "execution_score": 8.6,
                    "access_readiness_score": 8.7,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.92,
                },
                {
                    "service_slug": "rhumb-managed-email",
                    "aggregate_recommendation_score": 7.0,
                    "execution_score": 7.0,
                    "access_readiness_score": 7.0,
                    "tier": "L4",
                    "tier_label": "Native",
                    "confidence": 0.9,
                },
            ]
        if path.startswith("services?"):
            return [
                {"slug": "resend", "name": "Resend"},
                {"slug": "rhumb-managed-email", "name": "Rhumb Managed Email"},
            ]
        if path.startswith("bundle_capabilities?"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/resolve",
                params={"credential_mode": "byok"},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [provider["service_slug"] for provider in data["providers"]] == [
        "resend",
        "rhumb-managed-email",
    ]
    assert data["providers"][0]["configured"] is False
    assert data["providers"][1]["configured"] is False
    assert data["execute_hint"]["preferred_provider"] == "resend"
    assert data["execute_hint"]["configured"] is False
    assert data["execute_hint"]["preferred_credential_mode"] == "byok"
    assert data["execute_hint"]["selection_reason"] == "highest_ranked_provider"
    assert data["execute_hint"]["fallback_providers"] == ["rhumb-managed-email"]
    assert "RHUMB_CREDENTIAL_RESEND_API_KEY" in data["execute_hint"]["setup_hint"]


@pytest.mark.anyio
async def test_resolve_capability_empty_filter_prefers_broader_configured_alternate(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [{
                "id": "email.send",
                "domain": "email",
                "action": "send",
                "description": "Send email",
            }]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "resend",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "POST /emails",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
                {
                    "service_slug": "rhumb-managed-email",
                    "credential_modes": ["rhumb_managed"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "POST /v1/rhumb-managed/email/send",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": None,
                    "notes": None,
                },
            ]
        if path.startswith("scores?"):
            return [
                {
                    "service_slug": "resend",
                    "aggregate_recommendation_score": 8.8,
                    "execution_score": 8.6,
                    "access_readiness_score": 8.7,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.92,
                },
                {
                    "service_slug": "rhumb-managed-email",
                    "aggregate_recommendation_score": 7.0,
                    "execution_score": 7.0,
                    "access_readiness_score": 7.0,
                    "tier": "L4",
                    "tier_label": "Native",
                    "confidence": 0.9,
                },
            ]
        if path.startswith("services?"):
            return [
                {"slug": "resend", "name": "Resend"},
                {"slug": "rhumb-managed-email", "name": "Rhumb Managed Email"},
            ]
        if path.startswith("bundle_capabilities?"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/resolve",
                params={"credential_mode": "agent_vault"},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["providers"] == []
    assert data["fallback_chain"] == []
    assert data["execute_hint"] is None
    assert data["recovery_hint"] == {
        "reason": "no_providers_match_credential_mode",
        "requested_credential_mode": "agent_vault",
        "resolve_url": "/v1/capabilities/email.send/resolve",
        "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
        "supported_provider_slugs": ["resend", "rhumb-managed-email"],
        "supported_credential_modes": ["rhumb_managed", "byok"],
        "alternate_execute_hint": {
            "preferred_provider": "rhumb-managed-email",
            "endpoint_pattern": "POST /v1/rhumb-managed/email/send",
            "estimated_cost_usd": None,
            "auth_method": "api_key",
            "credential_modes": ["rhumb_managed"],
            "configured": True,
            "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
            "preferred_credential_mode": "rhumb_managed",
            "selection_reason": "configured_provider_preferred",
            "skipped_provider_slugs": ["resend"],
            "fallback_providers": ["resend"],
        },
    }


@pytest.mark.anyio
async def test_resolve_capability_prefers_configured_provider_in_execute_hint(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [{
                "id": "email.send",
                "domain": "email",
                "action": "send",
                "description": "Send email",
            }]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "resend",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "POST /emails",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
                {
                    "service_slug": "rhumb-managed-email",
                    "credential_modes": ["rhumb_managed"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "POST /v1/rhumb-managed/email/send",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": None,
                    "notes": None,
                },
            ]
        if path.startswith("scores?"):
            return [
                {
                    "service_slug": "resend",
                    "aggregate_recommendation_score": 8.8,
                    "execution_score": 8.6,
                    "access_readiness_score": 8.7,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.92,
                },
                {
                    "service_slug": "rhumb-managed-email",
                    "aggregate_recommendation_score": 7.0,
                    "execution_score": 7.0,
                    "access_readiness_score": 7.0,
                    "tier": "L4",
                    "tier_label": "Native",
                    "confidence": 0.9,
                },
            ]
        if path.startswith("services?"):
            return [
                {"slug": "resend", "name": "Resend"},
                {"slug": "rhumb-managed-email", "name": "Rhumb Managed Email"},
            ]
        if path.startswith("bundle_capabilities?"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/email.send/resolve")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [provider["service_slug"] for provider in data["providers"]] == [
        "resend",
        "rhumb-managed-email",
    ]
    assert data["providers"][0]["configured"] is False
    assert data["providers"][1]["configured"] is True
    assert data["execute_hint"]["preferred_provider"] == "rhumb-managed-email"
    assert data["execute_hint"]["auth_method"] == "api_key"
    assert data["execute_hint"]["configured"] is True
    assert data["execute_hint"]["credential_modes"] == ["rhumb_managed"]
    assert data["execute_hint"]["preferred_credential_mode"] == "rhumb_managed"
    assert data["execute_hint"]["selection_reason"] == "configured_provider_preferred"
    assert data["execute_hint"]["skipped_provider_slugs"] == ["resend"]
    assert data["execute_hint"]["fallback_providers"] == ["resend"]
    assert "setup_hint" not in data["execute_hint"]


@pytest.mark.anyio
async def test_resolve_capability_skips_open_provider_in_execute_hint_fallbacks(app):
    fake_breakers = _FakeBreakerRegistry({
        "resend": ("open", False),
        "sendgrid": ("closed", True),
    })

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase), patch(
        "routes.proxy.get_breaker_registry",
        return_value=fake_breakers,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/email.send/resolve")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["providers"][0]["service_slug"] == "resend"
    assert data["providers"][0]["circuit_state"] == "open"
    assert data["fallback_chain"] == ["sendgrid"]
    assert data["execute_hint"]["preferred_provider"] == "sendgrid"
    assert data["execute_hint"]["selection_reason"] == "higher_ranked_provider_unavailable"
    assert data["execute_hint"]["skipped_provider_slugs"] == ["resend"]
    assert "fallback_providers" not in data["execute_hint"]


@pytest.mark.anyio
async def test_resolve_capability_reports_doubly_blocked_skipped_provider_in_execute_hint(app):
    fake_breakers = _FakeBreakerRegistry({
        "resend": ("open", False),
        "sendgrid": ("closed", True),
    })

    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [{
                "id": "email.send",
                "domain": "email",
                "action": "send",
                "description": "Send email",
            }]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "resend",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": None,
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
                {
                    "service_slug": "sendgrid",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "POST /v3/mail/send",
                    "cost_per_call": "0.001",
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
            ]
        if path.startswith("scores?"):
            return [
                {
                    "service_slug": "resend",
                    "aggregate_recommendation_score": 8.1,
                    "execution_score": 8.5,
                    "access_readiness_score": 7.0,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.8,
                },
                {
                    "service_slug": "sendgrid",
                    "aggregate_recommendation_score": 6.35,
                    "execution_score": 7.0,
                    "access_readiness_score": 5.5,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.7,
                },
            ]
        if path.startswith("services?"):
            return [
                {"slug": "resend", "name": "Resend"},
                {"slug": "sendgrid", "name": "SendGrid"},
            ]
        if path.startswith("bundle_capabilities?"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch), patch(
        "routes.proxy.get_breaker_registry",
        return_value=fake_breakers,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/email.send/resolve")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [provider["service_slug"] for provider in data["providers"]] == ["resend", "sendgrid"]
    assert data["fallback_chain"] == ["sendgrid"]
    assert data["execute_hint"]["preferred_provider"] == "sendgrid"
    assert data["execute_hint"]["selection_reason"] == "higher_ranked_provider_mixed_execute_blockers"
    assert data["execute_hint"]["skipped_provider_slugs"] == ["resend"]
    assert data["execute_hint"]["unavailable_provider_slugs"] == ["resend"]
    assert data["execute_hint"]["not_execute_ready_provider_slugs"] == ["resend"]
    assert "recovery_hint" not in data


@pytest.mark.anyio
async def test_resolve_capability_reports_mixed_skipped_execute_blockers(app):
    fake_breakers = _FakeBreakerRegistry({
        "resend": ("open", False),
        "postmark": ("closed", True),
        "sendgrid": ("closed", True),
    })

    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [{
                "id": "email.send",
                "domain": "email",
                "action": "send",
                "description": "Send email",
            }]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "resend",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "POST /emails",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
                {
                    "service_slug": "postmark",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": None,
                    "cost_per_call": "0.001",
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
                {
                    "service_slug": "sendgrid",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "POST /v3/mail/send",
                    "cost_per_call": "0.001",
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
            ]
        if path.startswith("scores?"):
            return [
                {
                    "service_slug": "resend",
                    "aggregate_recommendation_score": 8.1,
                    "execution_score": 8.5,
                    "access_readiness_score": 7.0,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.8,
                },
                {
                    "service_slug": "postmark",
                    "aggregate_recommendation_score": 7.4,
                    "execution_score": 7.8,
                    "access_readiness_score": 6.8,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.78,
                },
                {
                    "service_slug": "sendgrid",
                    "aggregate_recommendation_score": 6.35,
                    "execution_score": 7.0,
                    "access_readiness_score": 5.5,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.7,
                },
            ]
        if path.startswith("services?"):
            return [
                {"slug": "resend", "name": "Resend"},
                {"slug": "postmark", "name": "Postmark"},
                {"slug": "sendgrid", "name": "SendGrid"},
            ]
        if path.startswith("bundle_capabilities?"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch), patch(
        "routes.proxy.get_breaker_registry",
        return_value=fake_breakers,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/email.send/resolve")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [provider["service_slug"] for provider in data["providers"]] == ["resend", "postmark", "sendgrid"]
    assert data["fallback_chain"] == ["sendgrid"]
    assert data["execute_hint"]["preferred_provider"] == "sendgrid"
    assert data["execute_hint"]["selection_reason"] == "higher_ranked_provider_mixed_execute_blockers"
    assert data["execute_hint"]["skipped_provider_slugs"] == ["resend", "postmark"]
    assert data["execute_hint"]["unavailable_provider_slugs"] == ["resend"]
    assert data["execute_hint"]["not_execute_ready_provider_slugs"] == ["postmark"]
    assert "recovery_hint" not in data


@pytest.mark.anyio
async def test_resolve_capability_reports_recovery_when_no_execute_ready_providers_remain(app):
    fake_breakers = _FakeBreakerRegistry({
        "resend": ("open", False),
        "sendgrid": ("open", False),
    })

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase), patch(
        "routes.proxy.get_breaker_registry",
        return_value=fake_breakers,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/email.send/resolve")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [provider["service_slug"] for provider in data["providers"]] == ["resend", "sendgrid"]
    assert data["fallback_chain"] == []
    assert data["execute_hint"] is None
    assert data["recovery_hint"] == {
        "reason": "no_execute_ready_providers",
        "resolve_url": "/v1/capabilities/email.send/resolve",
        "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
        "supported_provider_slugs": ["resend", "sendgrid"],
        "supported_credential_modes": ["byok"],
        "unavailable_provider_slugs": ["resend", "sendgrid"],
    }


@pytest.mark.anyio
async def test_resolve_capability_reports_non_circuit_execute_blockers_in_recovery(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [{
                "id": "email.send",
                "domain": "email",
                "action": "send",
                "description": "Send email",
            }]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "sendgrid",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": None,
                    "cost_per_call": "0.001",
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
                {
                    "service_slug": "resend",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": None,
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
            ]
        if path.startswith("scores?"):
            return [
                {
                    "service_slug": "resend",
                    "aggregate_recommendation_score": 7.79,
                    "execution_score": 8.5,
                    "access_readiness_score": 7.0,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.8,
                },
                {
                    "service_slug": "sendgrid",
                    "aggregate_recommendation_score": 6.35,
                    "execution_score": 7.0,
                    "access_readiness_score": 5.5,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.7,
                },
            ]
        if path.startswith("services?"):
            return [
                {"slug": "sendgrid", "name": "SendGrid"},
                {"slug": "resend", "name": "Resend"},
            ]
        if path.startswith("bundle_capabilities?"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/email.send/resolve")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [provider["service_slug"] for provider in data["providers"]] == ["resend", "sendgrid"]
    assert data["fallback_chain"] == []
    assert data["execute_hint"] is None
    assert data["recovery_hint"] == {
        "reason": "no_execute_ready_providers",
        "resolve_url": "/v1/capabilities/email.send/resolve",
        "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
        "supported_provider_slugs": ["resend", "sendgrid"],
        "supported_credential_modes": ["byok"],
        "setup_handoff": {
            "preferred_provider": "resend",
            "estimated_cost_usd": None,
            "auth_method": "api_key",
            "credential_modes": ["byok"],
            "configured": False,
            "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
            "preferred_credential_mode": "byok",
            "setup_hint": "Set RHUMB_CREDENTIAL_RESEND_API_KEY environment variable or configure via proxy credentials",
            "selection_reason": "highest_ranked_provider",
        },
        "not_execute_ready_provider_slugs": ["resend", "sendgrid"],
    }


@pytest.mark.anyio
async def test_resolve_capability_reports_mixed_execute_blockers_in_recovery(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [{
                "id": "email.send",
                "domain": "email",
                "action": "send",
                "description": "Send email",
            }]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "sendgrid",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": None,
                    "cost_per_call": "0.001",
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
                {
                    "service_slug": "resend",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": None,
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
            ]
        if path.startswith("scores?"):
            return [
                {
                    "service_slug": "resend",
                    "aggregate_recommendation_score": 7.79,
                    "execution_score": 8.5,
                    "access_readiness_score": 7.0,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.8,
                },
                {
                    "service_slug": "sendgrid",
                    "aggregate_recommendation_score": 6.35,
                    "execution_score": 7.0,
                    "access_readiness_score": 5.5,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.7,
                },
            ]
        if path.startswith("services?"):
            return [
                {"slug": "sendgrid", "name": "SendGrid"},
                {"slug": "resend", "name": "Resend"},
            ]
        if path.startswith("bundle_capabilities?"):
            return []
        return []

    fake_breakers = _FakeBreakerRegistry({
        "resend": ("open", False),
        "sendgrid": ("closed", True),
    })

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch), patch(
        "routes.proxy.get_breaker_registry",
        return_value=fake_breakers,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/email.send/resolve")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [provider["service_slug"] for provider in data["providers"]] == ["resend", "sendgrid"]
    assert data["fallback_chain"] == []
    assert data["execute_hint"] is None
    assert data["recovery_hint"] == {
        "reason": "no_execute_ready_providers",
        "resolve_url": "/v1/capabilities/email.send/resolve",
        "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
        "supported_provider_slugs": ["resend", "sendgrid"],
        "supported_credential_modes": ["byok"],
        "setup_handoff": {
            "preferred_provider": "sendgrid",
            "estimated_cost_usd": 0.001,
            "auth_method": "api_key",
            "credential_modes": ["byok"],
            "configured": False,
            "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
            "preferred_credential_mode": "byok",
            "setup_hint": "Set RHUMB_CREDENTIAL_SENDGRID_API_KEY environment variable or configure via proxy credentials",
            "selection_reason": "higher_ranked_provider_mixed_execute_blockers",
            "skipped_provider_slugs": ["resend"],
            "unavailable_provider_slugs": ["resend"],
            "not_execute_ready_provider_slugs": ["resend"],
        },
        "unavailable_provider_slugs": ["resend"],
        "not_execute_ready_provider_slugs": ["resend", "sendgrid"],
    }


@pytest.mark.anyio
async def test_resolve_capability_reports_recovery_when_no_providers_registered(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [{
                "id": "email.send",
                "domain": "email",
                "action": "send",
                "description": "Send email",
            }]
        if path.startswith("capability_services?"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/email.send/resolve")

    assert resp.status_code == 200
    assert resp.json()["data"] == {
        "capability": "email.send",
        "providers": [],
        "fallback_chain": [],
        "related_bundles": [],
        "execute_hint": None,
        "recovery_hint": {
            "reason": "no_providers_registered",
            "resolve_url": "/v1/capabilities/email.send/resolve",
            "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
        },
    }


@pytest.mark.anyio
async def test_resolve_capability_filtered_mode_recovery_keeps_unfiltered_pivot(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [{
                "id": "email.send",
                "domain": "email",
                "action": "send",
                "description": "Send email",
            }]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "resend",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": None,
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
                {
                    "service_slug": "rhumb-managed-email",
                    "credential_modes": ["rhumb_managed"],
                    "auth_method": "api_key",
                    "endpoint_pattern": "POST /v1/rhumb-managed/email/send",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": None,
                    "notes": None,
                },
            ]
        if path.startswith("scores?"):
            return [
                {
                    "service_slug": "resend",
                    "aggregate_recommendation_score": 8.8,
                    "execution_score": 8.6,
                    "access_readiness_score": 8.7,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.92,
                },
                {
                    "service_slug": "rhumb-managed-email",
                    "aggregate_recommendation_score": 7.0,
                    "execution_score": 7.0,
                    "access_readiness_score": 7.0,
                    "tier": "L4",
                    "tier_label": "Native",
                    "confidence": 0.9,
                },
            ]
        if path.startswith("services?"):
            return [
                {"slug": "resend", "name": "Resend"},
                {"slug": "rhumb-managed-email", "name": "Rhumb Managed Email"},
            ]
        if path.startswith("bundle_capabilities?"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/resolve",
                params={"credential_mode": "byok"},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [provider["service_slug"] for provider in data["providers"]] == ["resend"]
    assert data["fallback_chain"] == []
    assert data["execute_hint"] is None
    assert data["recovery_hint"] == {
        "reason": "no_execute_ready_providers",
        "requested_credential_mode": "byok",
        "resolve_url": "/v1/capabilities/email.send/resolve",
        "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
        "supported_provider_slugs": ["resend", "rhumb-managed-email"],
        "supported_credential_modes": ["rhumb_managed", "byok"],
        "alternate_execute_hint": {
            "preferred_provider": "rhumb-managed-email",
            "endpoint_pattern": "POST /v1/rhumb-managed/email/send",
            "estimated_cost_usd": None,
            "auth_method": "api_key",
            "credential_modes": ["rhumb_managed"],
            "configured": True,
            "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
            "preferred_credential_mode": "rhumb_managed",
            "selection_reason": "higher_ranked_provider_not_execute_ready",
            "skipped_provider_slugs": ["resend"],
            "not_execute_ready_provider_slugs": ["resend"],
        },
        "not_execute_ready_provider_slugs": ["resend"],
    }


@pytest.mark.anyio
async def test_resolve_capability_filtered_mode_recovery_includes_alternate_setup_handoff(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [{
                "id": "email.send",
                "domain": "email",
                "action": "send",
                "description": "Send email",
            }]
        if path.startswith("capability_services?"):
            return [
                {
                    "service_slug": "resend",
                    "credential_modes": ["byo"],
                    "auth_method": "api_key",
                    "endpoint_pattern": None,
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": 100,
                    "notes": None,
                },
                {
                    "service_slug": "gmail",
                    "credential_modes": ["agent_vault"],
                    "auth_method": "oauth",
                    "endpoint_pattern": "POST /gmail/v1/users/me/messages/send",
                    "cost_per_call": None,
                    "cost_currency": "USD",
                    "free_tier_calls": None,
                    "notes": None,
                },
            ]
        if path.startswith("scores?"):
            return [
                {
                    "service_slug": "resend",
                    "aggregate_recommendation_score": 8.8,
                    "execution_score": 8.6,
                    "access_readiness_score": 8.7,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.92,
                },
                {
                    "service_slug": "gmail",
                    "aggregate_recommendation_score": 7.2,
                    "execution_score": 7.2,
                    "access_readiness_score": 7.0,
                    "tier": "L3",
                    "tier_label": "Ready",
                    "confidence": 0.9,
                },
            ]
        if path.startswith("services?"):
            return [
                {"slug": "resend", "name": "Resend"},
                {"slug": "gmail", "name": "Gmail"},
            ]
        if path.startswith("bundle_capabilities?"):
            return []
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/capabilities/email.send/resolve",
                params={"credential_mode": "byok"},
            )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [provider["service_slug"] for provider in data["providers"]] == ["resend"]
    assert data["fallback_chain"] == []
    assert data["execute_hint"] is None
    assert data["recovery_hint"] == {
        "reason": "no_execute_ready_providers",
        "requested_credential_mode": "byok",
        "resolve_url": "/v1/capabilities/email.send/resolve",
        "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
        "supported_provider_slugs": ["resend", "gmail"],
        "supported_credential_modes": ["agent_vault", "byok"],
        "alternate_execute_hint": {
            "preferred_provider": "gmail",
            "endpoint_pattern": "POST /gmail/v1/users/me/messages/send",
            "estimated_cost_usd": None,
            "auth_method": "oauth",
            "credential_modes": ["agent_vault"],
            "configured": False,
            "credential_modes_url": "/v1/capabilities/email.send/credential-modes",
            "preferred_credential_mode": "agent_vault",
            "setup_hint": (
                "Complete the ceremony at GET /v1/services/gmail/ceremony, "
                "then pass token via X-Agent-Token header"
            ),
            "setup_url": "/v1/services/gmail/ceremony",
            "selection_reason": "higher_ranked_provider_not_execute_ready",
            "skipped_provider_slugs": ["resend"],
            "not_execute_ready_provider_slugs": ["resend"],
        },
        "not_execute_ready_provider_slugs": ["resend"],
    }


@pytest.mark.anyio
async def test_resolve_capability_not_found(app):
    """GET /v1/capabilities/nonexistent/resolve returns 404 with standardized envelope."""
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/nonexistent/resolve")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "capability_not_found"
    assert "nonexistent" in body["message"]
    assert "resolution" in body
    assert body["search_url"] == "/v1/capabilities?search=nonexistent"


@pytest.mark.anyio
async def test_list_bundles(app):
    """GET /v1/capabilities/bundles returns bundles with capability lists."""
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/bundles")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["bundles"]) == 1
    bundle = data["bundles"][0]
    assert bundle["id"] == "prospect.enrich_and_verify"
    assert len(bundle["capabilities"]) == 2
    assert "data.enrich_person" in bundle["capabilities"]


@pytest.mark.anyio
async def test_list_domains(app):
    """GET /v1/capabilities/domains returns domain list with counts."""
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/domains")
    assert resp.status_code == 200
    data = resp.json()["data"]
    domains = data["domains"]
    assert len(domains) >= 1
    # Should have domain and count
    for d in domains:
        assert "domain" in d
        assert "capability_count" in d


@pytest.mark.anyio
async def test_capabilities_list_preserves_direct_fallback_during_catalog_outage(app):
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities")

    assert resp.status_code == 200
    body = resp.json()
    assert "temporarily unavailable" in body["error"].lower()
    ids = {item["id"] for item in body["data"]["items"]}
    assert "db.query.read" in ids
    assert "crm.record.search" in ids


@pytest.mark.anyio
async def test_mapped_capability_resolve_uses_cached_catalog_during_outage(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
            warm_resp = await client.get("/v1/capabilities/email.send/resolve")

        with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, return_value=None):
            degraded_resp = await client.get("/v1/capabilities/email.send/resolve")

    assert warm_resp.status_code == 200
    assert degraded_resp.status_code == 200

    warm_data = warm_resp.json()["data"]
    degraded_data = degraded_resp.json()["data"]

    assert degraded_data["providers"] == warm_data["providers"]
    assert degraded_data["fallback_chain"] == warm_data["fallback_chain"]
    assert degraded_data["related_bundles"] == warm_data["related_bundles"]
    assert degraded_data["execute_hint"] == warm_data["execute_hint"]


@pytest.mark.anyio
async def test_db_direct_capability_surfaces_synthetic_provider(app):
    """DB direct capabilities should expose a truthful synthetic PostgreSQL provider."""
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_db_direct_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            list_resp = await client.get("/v1/capabilities")
            get_resp = await client.get("/v1/capabilities/db.query.read")
            resolve_resp = await client.get("/v1/capabilities/db.query.read/resolve")
            modes_resp = await client.get("/v1/capabilities/db.query.read/credential-modes")

    list_item = list_resp.json()["data"]["items"][0]
    assert list_item["provider_count"] == 1
    assert list_item["top_provider"]["slug"] == "postgresql"

    get_data = get_resp.json()["data"]
    assert get_data["provider_count"] == 1
    assert get_data["providers"][0]["service_slug"] == "postgresql"
    assert get_data["providers"][0]["auth_method"] == "connection_ref"
    assert "Hosted Rhumb should use agent_vault" in get_data["providers"][0]["notes"]

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["service_slug"] == "postgresql"
    assert resolve_data["providers"][0]["credential_modes"] == ["byok", "agent_vault"]
    assert resolve_data["related_bundles"] == []
    assert "bundle_ids" not in resolve_data
    assert resolve_data["providers"][0]["recommendation_reason"] == (
        "Direct read-only PostgreSQL execution. Hosted Rhumb uses agent_vault; "
        "env-backed connection_ref is self-hosted/internal only."
    )
    assert resolve_data["execute_hint"]["preferred_provider"] == "postgresql"
    assert resolve_data["execute_hint"]["auth_method"] == "connection_ref"
    assert resolve_data["execute_hint"]["configured"] is False
    assert resolve_data["execute_hint"]["credential_modes_url"] == "/v1/capabilities/db.query.read/credential-modes"
    assert resolve_data["execute_hint"]["preferred_credential_mode"] == "agent_vault"
    assert "X-Agent-Token" in resolve_data["execute_hint"]["setup_hint"]

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["service_slug"] == "postgresql"
    assert mode_data["providers"][0]["modes"][0]["mode"] == "byok"
    assert "Self-hosted/internal only" in mode_data["providers"][0]["modes"][0]["setup_hint"]
    assert mode_data["providers"][0]["modes"][1]["mode"] == "agent_vault"
    assert "Hosted/default path" in mode_data["providers"][0]["modes"][1]["setup_hint"]


@pytest.mark.anyio
async def test_db_direct_credential_modes_ignores_catalog_mapping_rows(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [DB_DIRECT_CAPABILITY]
        if path.startswith("capability_services?"):
            return [{
                "capability_id": "db.query.read",
                "service_slug": "stale-db-proxy",
                "credential_modes": ["byo"],
                "auth_method": "api_key",
            }]
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            modes_resp = await client.get("/v1/capabilities/db.query.read/credential-modes")

    mode_data = modes_resp.json()["data"]
    provider = mode_data["providers"][0]
    assert provider["service_slug"] == "postgresql"
    assert provider["auth_method"] == "connection_ref"
    assert provider["any_configured"] is False
    assert [mode["mode"] for mode in provider["modes"]] == ["byok", "agent_vault"]
    assert provider["modes"][0]["configured"] is False
    assert "RHUMB_DB_<REF>" in provider["modes"][0]["setup_hint"]
    assert provider["modes"][1]["configured"] is False
    assert "X-Agent-Token" in provider["modes"][1]["setup_hint"]


@pytest.mark.anyio
async def test_db_direct_capability_marks_env_bundle_as_configured(
    app,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(
        "RHUMB_DB_CONN_READER",
        "postgresql://reader:pass@localhost:5432/app",
    )

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_db_direct_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resolve_resp = await client.get("/v1/capabilities/db.query.read/resolve")
            byok_resp = await client.get(
                "/v1/capabilities/db.query.read/resolve",
                params={"credential_mode": "byok"},
            )
            agent_vault_resp = await client.get(
                "/v1/capabilities/db.query.read/resolve",
                params={"credential_mode": "agent_vault"},
            )
            modes_resp = await client.get("/v1/capabilities/db.query.read/credential-modes")

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["configured"] is True
    assert resolve_data["execute_hint"]["configured"] is True
    assert resolve_data["execute_hint"]["preferred_credential_mode"] == "byok"
    assert "setup_hint" not in resolve_data["execute_hint"]

    byok_data = byok_resp.json()["data"]
    assert byok_data["providers"][0]["configured"] is True
    assert byok_data["execute_hint"]["configured"] is True
    assert byok_data["execute_hint"]["preferred_credential_mode"] == "byok"
    assert "setup_hint" not in byok_data["execute_hint"]

    agent_vault_data = agent_vault_resp.json()["data"]
    assert agent_vault_data["providers"][0]["configured"] is False
    assert agent_vault_data["execute_hint"]["configured"] is False
    assert agent_vault_data["execute_hint"]["preferred_credential_mode"] == "agent_vault"
    assert "X-Agent-Token" in agent_vault_data["execute_hint"]["setup_hint"]

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["modes"][0]["configured"] is True
    assert mode_data["providers"][0]["modes"][1]["configured"] is False
    assert mode_data["providers"][0]["any_configured"] is True


@pytest.mark.anyio
async def test_db_direct_resolve_respects_credential_mode_filter(app):
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_db_direct_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            supported = await client.get(
                "/v1/capabilities/db.query.read/resolve",
                params={"credential_mode": "agent_vault"},
            )
            supported_alias = await client.get(
                "/v1/capabilities/db.query.read/resolve",
                params={"credential_mode": "byo"},
            )
            unsupported = await client.get(
                "/v1/capabilities/db.query.read/resolve",
                params={"credential_mode": "rhumb_managed"},
            )

    supported_data = supported.json()["data"]
    assert supported_data["providers"][0]["service_slug"] == "postgresql"
    assert supported_data["execute_hint"]["preferred_provider"] == "postgresql"
    assert supported_data["execute_hint"]["preferred_credential_mode"] == "agent_vault"

    supported_alias_data = supported_alias.json()["data"]
    assert supported_alias_data["providers"][0]["service_slug"] == "postgresql"
    assert supported_alias_data["execute_hint"]["preferred_provider"] == "postgresql"
    assert supported_alias_data["execute_hint"]["preferred_credential_mode"] == "byok"

    unsupported_data = unsupported.json()["data"]
    assert unsupported_data["providers"] == []
    assert unsupported_data["fallback_chain"] == []
    assert unsupported_data["execute_hint"] is None
    assert unsupported_data["recovery_hint"] == {
        "reason": "no_providers_match_credential_mode",
        "requested_credential_mode": "rhumb_managed",
        "resolve_url": "/v1/capabilities/db.query.read/resolve",
        "credential_modes_url": "/v1/capabilities/db.query.read/credential-modes",
        "supported_provider_slugs": ["postgresql"],
        "supported_credential_modes": ["agent_vault", "byok"],
        "alternate_execute_hint": {
            "preferred_provider": "postgresql",
            "endpoint_pattern": "POST /v1/capabilities/db.query.read/execute",
            "estimated_cost_usd": None,
            "auth_method": "connection_ref",
            "credential_modes": ["byok", "agent_vault"],
            "configured": False,
            "credential_modes_url": "/v1/capabilities/db.query.read/credential-modes",
            "preferred_credential_mode": "agent_vault",
            "setup_hint": "Hosted/default path: set credential_mode to 'agent_vault' and pass either a short-lived signed rhdbv1 DB vault token in X-Agent-Token or, as a compatibility bridge, a transient PostgreSQL DSN in X-Agent-Token. The raw DSN is never stored.",
            "setup_url": "/v1/services/postgresql/ceremony",
            "selection_reason": "highest_ranked_provider",
        },
    }


@pytest.mark.anyio
async def test_object_storage_direct_capability_surfaces_synthetic_provider(app):
    """S3 direct capabilities should expose a truthful synthetic aws-s3 provider."""
    with patch(
        "routes.capabilities.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_object_storage_direct_supabase,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            list_resp = await client.get("/v1/capabilities")
            get_resp = await client.get("/v1/capabilities/object.list")
            resolve_resp = await client.get("/v1/capabilities/object.list/resolve")
            modes_resp = await client.get("/v1/capabilities/object.list/credential-modes")

    list_item = list_resp.json()["data"]["items"][0]
    assert list_item["provider_count"] == 1
    assert list_item["top_provider"]["slug"] == "aws-s3"

    get_data = get_resp.json()["data"]
    assert get_data["provider_count"] == 1
    assert get_data["providers"][0]["service_slug"] == "aws-s3"
    assert get_data["providers"][0]["auth_method"] == "storage_ref"

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["service_slug"] == "aws-s3"
    assert resolve_data["providers"][0]["credential_modes"] == ["byok"]
    assert resolve_data["execute_hint"]["preferred_provider"] == "aws-s3"
    assert resolve_data["execute_hint"]["auth_method"] == "storage_ref"
    assert resolve_data["execute_hint"]["configured"] is False
    assert resolve_data["execute_hint"]["preferred_credential_mode"] == "byok"
    assert "RHUMB_STORAGE_<REF>" in resolve_data["execute_hint"]["setup_hint"]

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["service_slug"] == "aws-s3"
    assert mode_data["providers"][0]["modes"][0]["mode"] == "byok"
    assert "storage_ref" in mode_data["providers"][0]["modes"][0]["setup_hint"]


@pytest.mark.anyio
async def test_object_storage_direct_credential_modes_ignores_catalog_mapping_rows(app):
    async def mock_fetch(path: str):
        if path.startswith("capabilities?"):
            return [OBJECT_STORAGE_DIRECT_CAPABILITIES[0]]
        if path.startswith("capability_services?"):
            return [{
                "capability_id": "object.list",
                "service_slug": "stale-object-proxy",
                "credential_modes": ["byo"],
                "auth_method": "api_key",
            }]
        return []

    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=mock_fetch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            modes_resp = await client.get("/v1/capabilities/object.list/credential-modes")

    mode_data = modes_resp.json()["data"]
    provider = mode_data["providers"][0]
    assert provider["service_slug"] == "aws-s3"
    assert provider["auth_method"] == "storage_ref"
    assert provider["any_configured"] is False
    assert len(provider["modes"]) == 1
    assert provider["modes"][0]["mode"] == "byok"
    assert provider["modes"][0]["configured"] is False
    assert "RHUMB_STORAGE_<REF>" in provider["modes"][0]["setup_hint"]


@pytest.mark.anyio
async def test_support_direct_capability_surfaces_synthetic_provider(app):
    """Zendesk direct capabilities should expose a truthful synthetic provider."""
    with patch(
        "routes.capabilities.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_support_direct_supabase,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            list_resp = await client.get("/v1/capabilities")
            get_resp = await client.get("/v1/capabilities/ticket.search")
            resolve_resp = await client.get("/v1/capabilities/ticket.search/resolve")
            modes_resp = await client.get("/v1/capabilities/ticket.search/credential-modes")

    list_item = list_resp.json()["data"]["items"][0]
    assert list_item["provider_count"] == 1
    assert list_item["top_provider"]["slug"] == "zendesk"

    get_data = get_resp.json()["data"]
    assert get_data["provider_count"] == 1
    assert get_data["providers"][0]["service_slug"] == "zendesk"
    assert get_data["providers"][0]["auth_method"] == "support_ref"

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["service_slug"] == "zendesk"
    assert resolve_data["providers"][0]["credential_modes"] == ["byok"]
    assert resolve_data["execute_hint"]["preferred_provider"] == "zendesk"
    assert resolve_data["execute_hint"]["auth_method"] == "support_ref"
    assert resolve_data["execute_hint"]["configured"] is False
    assert resolve_data["execute_hint"]["preferred_credential_mode"] == "byok"
    assert "RHUMB_SUPPORT_<REF>" in resolve_data["execute_hint"]["setup_hint"]

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["service_slug"] == "zendesk"
    assert mode_data["providers"][0]["modes"][0]["mode"] == "byok"
    assert "RHUMB_SUPPORT_<REF>" in mode_data["providers"][0]["modes"][0]["setup_hint"]


@pytest.mark.anyio
async def test_crm_direct_capability_surfaces_synthetic_provider(app):
    """Configured CRM direct capabilities should surface Salesforce first when it is available."""
    with patch(
        "routes.capabilities.supabase_fetch",
        new_callable=AsyncMock,
        side_effect=_mock_crm_direct_supabase,
    ), patch("routes.capabilities.has_any_crm_bundle_configured", return_value=True):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            list_resp = await client.get("/v1/capabilities")
            get_resp = await client.get("/v1/capabilities/crm.record.search")
            resolve_resp = await client.get("/v1/capabilities/crm.record.search/resolve")
            modes_resp = await client.get("/v1/capabilities/crm.record.search/credential-modes")

    list_item = list_resp.json()["data"]["items"][0]
    assert list_item["provider_count"] == 2
    assert list_item["top_provider"]["slug"] == "salesforce"

    get_data = get_resp.json()["data"]
    assert get_data["provider_count"] == 2
    assert get_data["providers"][0]["service_slug"] == "salesforce"
    assert get_data["providers"][1]["service_slug"] == "hubspot"
    assert get_data["providers"][0]["auth_method"] == "crm_ref"

    resolve_data = resolve_resp.json()["data"]
    assert resolve_data["providers"][0]["service_slug"] == "salesforce"
    assert resolve_data["providers"][1]["service_slug"] == "hubspot"
    assert resolve_data["providers"][0]["credential_modes"] == ["byok"]
    assert resolve_data["providers"][0]["configured"] is True
    assert resolve_data["providers"][1]["configured"] is True
    assert resolve_data["execute_hint"]["preferred_provider"] == "salesforce"
    assert resolve_data["execute_hint"]["auth_method"] == "crm_ref"
    assert resolve_data["execute_hint"]["configured"] is True
    assert resolve_data["execute_hint"]["preferred_credential_mode"] == "byok"
    assert resolve_data["execute_hint"]["selection_reason"] == "highest_ranked_provider"
    assert resolve_data["execute_hint"]["fallback_providers"] == ["hubspot"]
    assert "setup_hint" not in resolve_data["execute_hint"]

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["service_slug"] == "salesforce"
    assert mode_data["providers"][1]["service_slug"] == "hubspot"
    assert mode_data["providers"][0]["modes"][0]["mode"] == "byok"
    assert "RHUMB_CRM_<REF>" in mode_data["providers"][0]["modes"][0]["setup_hint"]


@pytest.mark.anyio
async def test_resolve_returns_cost_info(app):
    """Resolve includes cost and free tier in recommendation reason."""
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/email.send/resolve")
    data = resp.json()["data"]
    # Resend should mention free tier
    resend = next(p for p in data["providers"] if p["service_slug"] == "resend")
    assert "free" in resend["recommendation_reason"].lower() or resend["free_tier_calls"] is not None
    # SendGrid should mention cost
    sg = next(p for p in data["providers"] if p["service_slug"] == "sendgrid")
    assert sg["cost_per_call"] is not None


@pytest.mark.anyio
async def test_resolve_fallback_chain_order(app):
    """Fallback chain is ordered by recommendation quality then score."""
    with patch("routes.capabilities.supabase_fetch", new_callable=AsyncMock, side_effect=_mock_supabase):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/capabilities/email.send/resolve")
    chain = resp.json()["data"]["fallback_chain"]
    assert len(chain) >= 1
    # First in chain should be the highest-scored preferred provider
    assert chain[0] == "resend"
