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
    assert "recommendation_reason" in first


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
    assert resolve_data["providers"][0]["recommendation_reason"] == (
        "Direct read-only PostgreSQL execution. Hosted Rhumb uses agent_vault; "
        "env-backed connection_ref is self-hosted/internal only."
    )
    assert resolve_data["execute_hint"]["preferred_provider"] == "postgresql"

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["service_slug"] == "postgresql"
    assert mode_data["providers"][0]["modes"][0]["mode"] == "byok"
    assert "Self-hosted/internal only" in mode_data["providers"][0]["modes"][0]["setup_hint"]
    assert mode_data["providers"][0]["modes"][1]["mode"] == "agent_vault"
    assert "Hosted/default path" in mode_data["providers"][0]["modes"][1]["setup_hint"]


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

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["service_slug"] == "aws-s3"
    assert mode_data["providers"][0]["modes"][0]["mode"] == "byok"
    assert "storage_ref" in mode_data["providers"][0]["modes"][0]["setup_hint"]


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

    mode_data = modes_resp.json()["data"]
    assert mode_data["providers"][0]["service_slug"] == "zendesk"
    assert mode_data["providers"][0]["modes"][0]["mode"] == "byok"
    assert "RHUMB_SUPPORT_<REF>" in mode_data["providers"][0]["modes"][0]["setup_hint"]


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
