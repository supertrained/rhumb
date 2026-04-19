"""Tests for the execution receipt service."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import pytest

from services.receipt_service import (
    ReceiptInput,
    ReceiptService,
    _compute_receipt_hash,
    _generate_receipt_id,
    _hash_content,
    hash_caller_ip,
    hash_request_payload,
    hash_response_payload,
)


def test_receipt_id_format():
    rid = _generate_receipt_id()
    assert rid.startswith("rcpt_")
    assert len(rid) == 29  # "rcpt_" + 24 hex chars


def test_hash_content_deterministic():
    h1 = _hash_content("hello world")
    h2 = _hash_content("hello world")
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_hash_content_differs_for_different_input():
    h1 = _hash_content("hello")
    h2 = _hash_content("world")
    assert h1 != h2


def test_hash_request_payload_none():
    assert hash_request_payload(None) is None


def test_hash_request_payload_dict():
    h = hash_request_payload({"query": "test", "limit": 5})
    assert h is not None
    assert h.startswith("sha256:")


def test_hash_request_payload_deterministic():
    """Same payload with different key order should produce same hash."""
    h1 = hash_request_payload({"b": 2, "a": 1})
    h2 = hash_request_payload({"a": 1, "b": 2})
    assert h1 == h2


def test_hash_caller_ip():
    h = hash_caller_ip("192.168.1.1")
    assert h is not None
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 16


def test_hash_caller_ip_none():
    assert hash_caller_ip(None) is None


def test_compute_receipt_hash_deterministic():
    data = {
        "receipt_id": "rcpt_test123",
        "receipt_version": "1.0",
        "created_at": "2026-03-31T00:00:00Z",
        "execution_id": "exec_abc",
        "layer": 2,
        "capability_id": "search.query",
        "status": "success",
        "agent_id": "agent_123",
        "provider_id": "brave",
        "credential_mode": "rhumb_managed",
    }
    h1 = _compute_receipt_hash(data)
    h2 = _compute_receipt_hash(data)
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_compute_receipt_hash_changes_on_different_data():
    data1 = {
        "receipt_id": "rcpt_test123",
        "status": "success",
        "execution_id": "exec_abc",
        "layer": 2,
        "capability_id": "search.query",
        "agent_id": "agent_123",
        "provider_id": "brave",
        "credential_mode": "rhumb_managed",
    }
    data2 = {**data1, "status": "failure"}
    assert _compute_receipt_hash(data1) != _compute_receipt_hash(data2)


@pytest.mark.anyio
async def test_create_receipt_writes_to_supabase():
    """Receipt creation should write to Supabase and return a valid Receipt."""
    service = ReceiptService()

    mock_chain_state = [{"last_sequence": 0, "last_receipt_hash": None}]

    with (
        patch("services.receipt_service.supabase_fetch", new=AsyncMock(return_value=mock_chain_state)),
        patch("services.receipt_service.supabase_insert", new=AsyncMock(return_value=True)) as mock_insert,
        patch("services.receipt_service.supabase_patch", new=AsyncMock(return_value=True)),
    ):
        receipt = await service.create_receipt(ReceiptInput(
            execution_id="exec_test_001",
            capability_id="search.query",
            status="success",
            agent_id="agent_test_123",
            provider_id="brave-search",
            credential_mode="rhumb_managed",
            layer=2,
            total_latency_ms=342.5,
            provider_latency_ms=290.0,
            rhumb_overhead_ms=52.5,
        ))

    assert receipt.receipt_id.startswith("rcpt_")
    assert receipt.execution_id == "exec_test_001"
    assert receipt.capability_id == "search.query"
    assert receipt.status == "success"
    assert receipt.layer == 2
    assert receipt.chain_sequence == 1
    assert receipt.previous_receipt_hash is None
    assert receipt.receipt_hash.startswith("sha256:")

    # Verify Supabase insert was called
    mock_insert.assert_called_once()
    inserted_data = mock_insert.call_args[0][1]
    assert inserted_data["receipt_id"] == receipt.receipt_id
    assert inserted_data["execution_id"] == "exec_test_001"
    assert inserted_data["chain_sequence"] == 1


@pytest.mark.anyio
async def test_create_receipt_chains_correctly():
    """Second receipt should link to first receipt's hash."""
    service = ReceiptService()

    first_hash = "sha256:abc123"
    mock_chain_state = [{"last_sequence": 5, "last_receipt_hash": first_hash}]

    with (
        patch("services.receipt_service.supabase_fetch", new=AsyncMock(return_value=mock_chain_state)),
        patch("services.receipt_service.supabase_insert", new=AsyncMock(return_value=True)),
        patch("services.receipt_service.supabase_patch", new=AsyncMock(return_value=True)),
    ):
        receipt = await service.create_receipt(ReceiptInput(
            execution_id="exec_test_002",
            capability_id="person.enrich",
            status="success",
            agent_id="agent_test_456",
            provider_id="apollo",
            credential_mode="rhumb_managed",
        ))

    assert receipt.chain_sequence == 6
    assert receipt.previous_receipt_hash == first_hash


@pytest.mark.anyio
async def test_get_receipt_returns_none_for_missing():
    service = ReceiptService()

    with patch("services.receipt_service.supabase_fetch", new=AsyncMock(return_value=[])):
        result = await service.get_receipt("rcpt_nonexistent")

    assert result is None


@pytest.mark.anyio
async def test_create_receipt_canonicalizes_alias_backed_provider_id_before_hashing_and_persisting():
    service = ReceiptService()
    mock_chain_state = [{"last_sequence": 0, "last_receipt_hash": None}]

    with (
        patch("services.receipt_service.supabase_fetch", new=AsyncMock(return_value=mock_chain_state)),
        patch("services.receipt_service.supabase_insert", new=AsyncMock(return_value=True)) as mock_insert,
        patch("services.receipt_service.supabase_patch", new=AsyncMock(return_value=True)),
    ):
        receipt = await service.create_receipt(ReceiptInput(
            execution_id="exec_test_alias_001",
            capability_id="search.query",
            status="success",
            agent_id="agent_test_alias",
            provider_id="brave-search",
            credential_mode="rhumb_managed",
            layer=2,
        ))

    inserted_data = mock_insert.call_args[0][1]
    hashed_payload = {k: v for k, v in inserted_data.items() if k != "receipt_hash"}

    assert inserted_data["provider_id"] == "brave-search-api"
    assert receipt.provider_id == "brave-search-api"
    assert inserted_data["receipt_hash"] == _compute_receipt_hash(hashed_payload)
    assert inserted_data["receipt_hash"] != _compute_receipt_hash({
        **hashed_payload,
        "provider_id": "brave-search",
    })


@pytest.mark.anyio
async def test_create_receipt_canonicalizes_alias_backed_provider_text_before_hashing_and_persisting():
    service = ReceiptService()
    mock_chain_state = [{"last_sequence": 0, "last_receipt_hash": None}]

    with (
        patch("services.receipt_service.supabase_fetch", new=AsyncMock(return_value=mock_chain_state)),
        patch("services.receipt_service.supabase_insert", new=AsyncMock(return_value=True)) as mock_insert,
        patch("services.receipt_service.supabase_patch", new=AsyncMock(return_value=True)),
    ):
        receipt = await service.create_receipt(ReceiptInput(
            execution_id="exec_test_alias_text_001",
            capability_id="search.query",
            status="failure",
            agent_id="agent_test_alias_text",
            provider_id="brave-search",
            credential_mode="rhumb_managed",
            layer=2,
            provider_name="Brave Search (brave-search)",
            winner_reason="brave-search won on freshness",
            error_message="brave-search upstream exploded",
            error_code="upstream_error",
        ))

    inserted_data = mock_insert.call_args[0][1]
    hashed_payload = {k: v for k, v in inserted_data.items() if k != "receipt_hash"}

    assert receipt.provider_id == "brave-search-api"
    assert inserted_data["provider_id"] == "brave-search-api"
    assert inserted_data["provider_name"] == "Brave Search (brave-search-api)"
    assert inserted_data["winner_reason"] == "brave-search-api won on freshness"
    assert inserted_data["error_message"] == "brave-search-api upstream exploded"
    assert inserted_data["receipt_hash"] == _compute_receipt_hash(hashed_payload)
    assert inserted_data["receipt_hash"] != _compute_receipt_hash({
        **hashed_payload,
        "provider_name": "Brave Search (brave-search)",
        "winner_reason": "brave-search won on freshness",
        "error_message": "brave-search upstream exploded",
    })


@pytest.mark.anyio
async def test_create_receipt_canonicalizes_alternate_provider_alias_text_before_hashing_and_persisting():
    service = ReceiptService()
    mock_chain_state = [{"last_sequence": 0, "last_receipt_hash": None}]

    with (
        patch("services.receipt_service.supabase_fetch", new=AsyncMock(return_value=mock_chain_state)),
        patch("services.receipt_service.supabase_insert", new=AsyncMock(return_value=True)) as mock_insert,
        patch("services.receipt_service.supabase_patch", new=AsyncMock(return_value=True)),
    ):
        await service.create_receipt(ReceiptInput(
            execution_id="exec_test_alias_text_002",
            capability_id="search.query",
            status="failure",
            agent_id="agent_test_alias_text",
            provider_id="brave-search",
            credential_mode="rhumb_managed",
            layer=2,
            winner_reason="brave-search fell back to pdl on contact coverage",
            error_message="brave-search failed after pdl credential lookup",
            error_code="upstream_error",
            error_provider_raw="pdl",
        ))

    inserted_data = mock_insert.call_args[0][1]
    hashed_payload = {k: v for k, v in inserted_data.items() if k != "receipt_hash"}

    assert inserted_data["provider_id"] == "brave-search-api"
    assert inserted_data["winner_reason"] == "brave-search-api fell back to people-data-labs on contact coverage"
    assert inserted_data["error_message"] == "brave-search-api failed after people-data-labs credential lookup"
    assert inserted_data["receipt_hash"] == _compute_receipt_hash(hashed_payload)
    assert inserted_data["receipt_hash"] != _compute_receipt_hash({
        **hashed_payload,
        "winner_reason": "brave-search fell back to pdl on contact coverage",
        "error_message": "brave-search failed after pdl credential lookup",
    })


@pytest.mark.anyio
async def test_create_receipt_canonicalizes_known_alternate_provider_alias_text_without_raw_provider_hint():
    service = ReceiptService()
    mock_chain_state = [{"last_sequence": 0, "last_receipt_hash": None}]

    with (
        patch("services.receipt_service.supabase_fetch", new=AsyncMock(return_value=mock_chain_state)),
        patch("services.receipt_service.supabase_insert", new=AsyncMock(return_value=True)) as mock_insert,
        patch("services.receipt_service.supabase_patch", new=AsyncMock(return_value=True)),
    ):
        await service.create_receipt(ReceiptInput(
            execution_id="exec_test_alias_text_003",
            capability_id="search.query",
            status="failure",
            agent_id="agent_test_alias_text",
            provider_id="brave-search-api",
            credential_mode="rhumb_managed",
            layer=2,
            winner_reason="brave-search-api fell back to pdl on contact coverage",
            error_message="brave-search-api failed after pdl credential lookup",
            error_code="upstream_error",
        ))

    inserted_data = mock_insert.call_args[0][1]
    hashed_payload = {k: v for k, v in inserted_data.items() if k != "receipt_hash"}

    assert inserted_data["provider_id"] == "brave-search-api"
    assert inserted_data["winner_reason"] == "brave-search-api fell back to people-data-labs on contact coverage"
    assert inserted_data["error_message"] == "brave-search-api failed after people-data-labs credential lookup"
    assert inserted_data["receipt_hash"] == _compute_receipt_hash(hashed_payload)
    assert inserted_data["receipt_hash"] != _compute_receipt_hash({
        **hashed_payload,
        "winner_reason": "brave-search-api fell back to pdl on contact coverage",
        "error_message": "brave-search-api failed after pdl credential lookup",
    })


@pytest.mark.anyio
async def test_create_receipt_canonicalizes_same_provider_alias_text_when_structured_fields_are_already_canonical():
    service = ReceiptService()
    mock_chain_state = [{"last_sequence": 0, "last_receipt_hash": None}]

    with (
        patch("services.receipt_service.supabase_fetch", new=AsyncMock(return_value=mock_chain_state)),
        patch("services.receipt_service.supabase_insert", new=AsyncMock(return_value=True)) as mock_insert,
        patch("services.receipt_service.supabase_patch", new=AsyncMock(return_value=True)),
    ):
        await service.create_receipt(ReceiptInput(
            execution_id="exec_test_alias_text_004",
            capability_id="search.query",
            status="failure",
            agent_id="agent_test_alias_text",
            provider_id="brave-search-api",
            credential_mode="rhumb_managed",
            layer=2,
            provider_name="Brave Search (brave-search)",
            winner_reason="brave-search won on freshness",
            error_message="brave-search upstream exploded",
            error_code="upstream_error",
        ))

    inserted_data = mock_insert.call_args[0][1]
    hashed_payload = {k: v for k, v in inserted_data.items() if k != "receipt_hash"}

    assert inserted_data["provider_id"] == "brave-search-api"
    assert inserted_data["provider_name"] == "Brave Search (brave-search-api)"
    assert inserted_data["winner_reason"] == "brave-search-api won on freshness"
    assert inserted_data["error_message"] == "brave-search-api upstream exploded"
    assert "brave-search-api-api" not in inserted_data["provider_name"]
    assert "brave-search-api-api" not in inserted_data["winner_reason"]
    assert "brave-search-api-api" not in inserted_data["error_message"]
    assert inserted_data["receipt_hash"] == _compute_receipt_hash(hashed_payload)
    assert inserted_data["receipt_hash"] != _compute_receipt_hash({
        **hashed_payload,
        "provider_name": "Brave Search (brave-search)",
        "winner_reason": "brave-search won on freshness",
        "error_message": "brave-search upstream exploded",
    })


@pytest.mark.anyio
async def test_get_receipt_canonicalizes_alias_backed_provider_id():
    service = ReceiptService()

    with patch(
        "services.receipt_service.supabase_fetch",
        new=AsyncMock(return_value=[{"receipt_id": "rcpt_123", "provider_id": "brave-search"}]),
    ):
        result = await service.get_receipt("rcpt_123")

    assert result is not None
    assert result["provider_id"] == "brave-search-api"


@pytest.mark.anyio
async def test_get_receipt_canonicalizes_alias_backed_provider_name_error_message_and_winner_reason_and_hides_raw_provider_hint():
    service = ReceiptService()

    with patch(
        "services.receipt_service.supabase_fetch",
        new=AsyncMock(
            return_value=[
                {
                    "receipt_id": "rcpt_legacy_error",
                    "provider_id": "brave-search-api",
                    "provider_name": "Brave-Search",
                    "error_message": "Brave-Search upstream exploded",
                    "winner_reason": "Brave-Search won on freshness",
                    "error_provider_raw": "brave-search",
                }
            ]
        ),
    ):
        result = await service.get_receipt("rcpt_legacy_error")

    assert result is not None
    assert result["provider_id"] == "brave-search-api"
    assert result["provider_name"] == "brave-search-api"
    assert result["error_message"] == "brave-search-api upstream exploded"
    assert result["winner_reason"] == "brave-search-api won on freshness"
    assert "error_provider_raw" not in result


@pytest.mark.anyio
async def test_get_receipt_canonicalizes_alternate_provider_alias_text_on_public_reads():
    service = ReceiptService()

    with patch(
        "services.receipt_service.supabase_fetch",
        new=AsyncMock(
            return_value=[
                {
                    "receipt_id": "rcpt_legacy_fallback",
                    "provider_id": "brave-search-api",
                    "error_message": "brave-search failed after pdl credential lookup",
                    "winner_reason": "brave-search fell back to pdl on contact coverage",
                    "error_provider_raw": "pdl",
                }
            ]
        ),
    ):
        result = await service.get_receipt("rcpt_legacy_fallback")

    assert result is not None
    assert result["provider_id"] == "brave-search-api"
    assert result["error_message"] == "brave-search-api failed after people-data-labs credential lookup"
    assert result["winner_reason"] == "brave-search-api fell back to people-data-labs on contact coverage"
    assert "error_provider_raw" not in result


@pytest.mark.anyio
async def test_get_receipt_canonicalizes_known_alternate_provider_alias_text_without_raw_provider_hint_on_public_reads():
    service = ReceiptService()

    with patch(
        "services.receipt_service.supabase_fetch",
        new=AsyncMock(
            return_value=[
                {
                    "receipt_id": "rcpt_legacy_fallback_no_hint",
                    "provider_id": "brave-search-api",
                    "error_message": "brave-search-api failed after pdl credential lookup",
                    "winner_reason": "brave-search-api fell back to pdl on contact coverage",
                }
            ]
        ),
    ):
        result = await service.get_receipt("rcpt_legacy_fallback_no_hint")

    assert result is not None
    assert result["provider_id"] == "brave-search-api"
    assert result["error_message"] == "brave-search-api failed after people-data-labs credential lookup"
    assert result["winner_reason"] == "brave-search-api fell back to people-data-labs on contact coverage"


@pytest.mark.anyio
async def test_query_receipts_matches_alias_backed_provider_ids_and_returns_canonical_ids():
    service = ReceiptService()
    mock_fetch = AsyncMock(return_value=[{"receipt_id": "rcpt_123", "provider_id": "brave-search"}])

    with patch("services.receipt_service.supabase_fetch", new=mock_fetch):
        result = await service.query_receipts(provider_id="brave-search-api", limit=10)

    assert result == [{"receipt_id": "rcpt_123", "provider_id": "brave-search-api"}]
    query = mock_fetch.await_args.args[0]
    assert "provider_id=in.(brave-search-api,brave-search)" in query


@pytest.mark.anyio
async def test_query_receipts_canonicalizes_legacy_provider_text_on_public_reads():
    service = ReceiptService()
    mock_fetch = AsyncMock(
        return_value=[
            {
                "receipt_id": "rcpt_legacy_error",
                "provider_id": "people-data-labs",
                "provider_name": "PDL",
                "error_message": "pdl credential unavailable",
                "winner_reason": "PDL won on contact coverage",
            }
        ]
    )

    with patch("services.receipt_service.supabase_fetch", new=mock_fetch):
        result = await service.query_receipts(provider_id="people-data-labs", limit=10)

    assert result == [
        {
            "receipt_id": "rcpt_legacy_error",
            "provider_id": "people-data-labs",
            "provider_name": "people-data-labs",
            "error_message": "people-data-labs credential unavailable",
            "winner_reason": "people-data-labs won on contact coverage",
        }
    ]


@pytest.mark.anyio
async def test_public_receipt_row_preserves_human_provider_names_when_row_is_already_canonical():
    service = ReceiptService()
    mock_fetch = AsyncMock(
        return_value=[
            {
                "receipt_id": "rcpt_human_name",
                "provider_id": "people-data-labs",
                "provider_name": "People Data Labs",
            }
        ]
    )

    with patch("services.receipt_service.supabase_fetch", new=mock_fetch):
        result = await service.get_receipt("rcpt_human_name")

    assert result == {
        "receipt_id": "rcpt_human_name",
        "provider_id": "people-data-labs",
        "provider_name": "People Data Labs",
    }


@pytest.mark.anyio
async def test_verify_chain_intact():
    service = ReceiptService()

    mock_rows = [
        {"receipt_id": "r1", "receipt_hash": "h1", "previous_receipt_hash": None, "chain_sequence": 1},
        {"receipt_id": "r2", "receipt_hash": "h2", "previous_receipt_hash": "h1", "chain_sequence": 2},
        {"receipt_id": "r3", "receipt_hash": "h3", "previous_receipt_hash": "h2", "chain_sequence": 3},
    ]

    with patch("services.receipt_service.supabase_fetch", new=AsyncMock(return_value=mock_rows)):
        result = await service.verify_chain(limit=10)

    assert result["chain_intact"] is True
    assert result["verified"] == 3
    assert result["broken_links"] == []


@pytest.mark.anyio
async def test_verify_chain_detects_broken_link():
    service = ReceiptService()

    mock_rows = [
        {"receipt_id": "r1", "receipt_hash": "h1", "previous_receipt_hash": None, "chain_sequence": 1},
        {"receipt_id": "r2", "receipt_hash": "h2", "previous_receipt_hash": "WRONG", "chain_sequence": 2},
    ]

    with patch("services.receipt_service.supabase_fetch", new=AsyncMock(return_value=mock_rows)):
        result = await service.verify_chain(limit=10)

    assert result["chain_intact"] is False
    assert len(result["broken_links"]) == 1
    assert result["broken_links"][0]["receipt_id"] == "r2"
