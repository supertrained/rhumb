"""PP-1/PP-2 Index manifest serving route tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from schemas.capability_manifest import fixture_manifests_by_route_id
from services.index_manifest_store import DurableIndexManifestStore, IndexManifestStore


@pytest.fixture(autouse=True)
def _disable_durable_index_reads():
    """Keep route tests on deterministic fixture fallback unless a test opts in."""
    with patch("services.index_manifest_store.supabase_fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []
        yield mock_fetch


def _durable_manifest_row() -> dict:
    return {
        "route_id": "route_search_query_brave_search_api_official_api_v1",
        "manifest_id": "manifest_search_query_brave_search_api_official_api_v1",
        "manifest_version": "2026-05-19.1",
        "manifest_digest": "sha256:durable-manifest",
        "service_id": "brave-search",
        "provider_id": "brave-search-api",
        "capability_id": "search.query",
        "substrate": "official_api",
        "provenance_origin": "rhumb_managed",
        "source_risk": "verified_low",
        "side_effect_class": "read",
        "promotion_state": "production_executable",
        "review_status": "current",
        "evidence_packet_id": "evidence_search_query_brave_search_api_official_api_2026_05_19",
        "evidence_packet_digest": "sha256:durable-evidence",
        "evidence_expires_at": "2026-08-17T00:00:00Z",
        "public_claim_boundary": "Rhumb can route read-only web search queries through a governed Brave Search API route.",
        "manifest_json": {
            "route_name": "Durable Brave Search API route",
            "network_allowlist": ["api.search.brave.com"],
        },
        "evidence_packet_json": {"sources": [{"kind": "vendor_docs", "url": "https://api.search.brave.com/"}]},
        "owner": "Pedro",
        "reviewer": "Pedro",
        "expires_at": "2026-08-17T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_index_manifest_list_serves_taxonomy_policy_and_manifest_facts() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/v2/index/manifests?capability_id=search.query")

    assert response.status_code == 200
    payload = response.json()
    assert payload["error"] is None
    data = payload["data"]
    assert data["contract_id"] == "index_command_manifest_v1"
    assert data["source"] == "PP-2"
    assert data["status"] == "hosted_index_with_fixture_fallback"
    assert data["total"] == 1
    assert "official_api" in data["taxonomy"]["substrates"]
    assert "verified_low" in data["taxonomy"]["source_risks"]

    manifest = data["manifests"][0]
    assert manifest["route_id"] == "route_search_query_brave_search_api_official_api_v1"
    assert manifest["capability_id"] == "search.query"
    assert manifest["substrate"] == "official_api"
    assert manifest["source_risk"] == "verified_low"
    assert manifest["recommendation_policy"]["default_recommendable"] is True
    assert manifest["recommendation_policy"]["reasons"] == []
    assert data["_rhumb_v2"]["compat_mode"] == "v1-translate"


@pytest.mark.asyncio
async def test_index_manifest_filters_expose_non_default_fixture_policy() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/v2/index/manifests?substrate=generated_adapter")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    manifest = data["manifests"][0]
    assert manifest["substrate"] == "generated_adapter"
    assert manifest["recommendation_policy"]["default_recommendable"] is False
    assert manifest["recommendation_policy"]["requires_explicit_request"] is True
    assert "generated_route_not_default" in manifest["recommendation_policy"]["reasons"]


@pytest.mark.asyncio
async def test_index_manifest_detail_returns_one_stable_route_manifest() -> None:
    route_id = "route_workflow_run_list_github_cli_v1"
    expected = fixture_manifests_by_route_id()[route_id]

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get(f"/v2/index/manifests/{route_id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["contract_id"] == "index_command_manifest_v1"
    manifest = data["manifest"]
    assert manifest["manifest_digest"] == expected["manifest_digest"]
    assert manifest["substrate"] == "official_cli"
    assert manifest["recommendation_policy"]["default_recommendable"] is False


@pytest.mark.asyncio
async def test_index_manifest_invalid_taxonomy_filter_rejects_before_manifest_serving() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/v2/index/manifests?source_risk=totally-made-up")

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_PARAMETERS"
    assert body["error"]["message"] == "Invalid 'source_risk' filter."
    assert "verified_low" in body["error"]["detail"]


@pytest.mark.asyncio
async def test_index_manifest_unknown_route_id_returns_typed_not_found() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/v2/index/manifests/route_missing")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "ROUTE_MANIFEST_NOT_FOUND"
    assert "GET /v2/index/manifests" in body["error"]["detail"]


def test_index_manifest_store_returns_deep_copies_and_route_facts() -> None:
    store = IndexManifestStore()

    manifests = store.list_manifests(capability_id="search.query")
    manifests[0]["substrate"] = "mutated_by_test"

    fresh = store.list_manifests(capability_id="search.query")[0]
    assert fresh["substrate"] == "official_api"

    route_facts = store.route_facts_for_provider("search.query", "brave-search-api")
    assert route_facts["route_id"] == "route_search_query_brave_search_api_official_api_v1"
    assert route_facts["manifest_digest"].startswith("sha256:")
    assert route_facts["evidence_packet_id"] == "evidence_search_query_brave_search_api_official_api_2026_05_19"
    assert route_facts["recommendation_policy"]["default_recommendable"] is True


@pytest.mark.asyncio
async def test_durable_index_manifest_store_prefers_hosted_rows(_disable_durable_index_reads) -> None:
    _disable_durable_index_reads.return_value = [_durable_manifest_row()]
    store = DurableIndexManifestStore()

    manifests = await store.list_manifests(capability_id="search.query")

    assert manifests[0]["route_name"] == "Durable Brave Search API route"
    assert manifests[0]["manifest_digest"] == "sha256:durable-manifest"
    assert _disable_durable_index_reads.await_args.args[0].startswith("index_command_manifests?capability_id=eq.search.query")


@pytest.mark.asyncio
async def test_durable_index_manifest_store_route_facts_include_evidence_and_policy(_disable_durable_index_reads) -> None:
    _disable_durable_index_reads.return_value = [_durable_manifest_row()]
    store = DurableIndexManifestStore()

    facts = await store.route_facts_for_provider("search.query", "brave-search-api")

    assert facts["route_id"] == "route_search_query_brave_search_api_official_api_v1"
    assert facts["manifest_digest"] == "sha256:durable-manifest"
    assert facts["evidence_packet_digest"] == "sha256:durable-evidence"
    assert facts["review_status"] == "current"
    assert facts["recommendation_policy"]["default_recommendable"] is True


@pytest.mark.asyncio
async def test_durable_index_manifest_store_falls_back_when_hosted_rows_empty(_disable_durable_index_reads) -> None:
    _disable_durable_index_reads.return_value = []
    store = DurableIndexManifestStore()

    manifest = await store.get_manifest("route_workflow_run_list_github_cli_v1")

    assert manifest is not None
    assert manifest["substrate"] == "official_cli"
