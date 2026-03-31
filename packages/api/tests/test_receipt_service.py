"""Tests for the execution receipt service.

Tests the core receipt creation, chain hashing, integrity verification,
and query functionality. Uses mocked Supabase calls.
"""

from __future__ import annotations

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.receipt_service import (
    Receipt,
    ReceiptInput,
    ReceiptService,
    _compute_receipt_hash,
    _generate_receipt_id,
    _hash_content,
    hash_caller_ip,
    hash_request_payload,
    hash_response_payload,
)


# ── Unit tests for hash helpers ──


def test_hash_content_deterministic():
    """Same input always produces same hash."""
    h1 = _hash_content("hello world")
    h2 = _hash_content("hello world")
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_hash_content_different_inputs():
    """Different inputs produce different hashes."""
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
    """Same dict produces same hash regardless of key order."""
    h1 = hash_request_payload({"b": 2, "a": 1})
    h2 = hash_request_payload({"a": 1, "b": 2})
    assert h1 == h2


def test_hash_response_payload():
    h = hash_response_payload({"status": "ok", "data": [1, 2, 3]})
    assert h is not None
    assert h.startswith("sha256:")


def test_hash_caller_ip():
    h = hash_caller_ip("192.168.1.1")
    assert h is not None
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 16  # truncated


def test_hash_caller_ip_none():
    assert hash_caller_ip(None) is None


def test_generate_receipt_id():
    rid = _generate_receipt_id()
    assert rid.startswith("rcpt_")
    assert len(rid) > 10


# ── Unit tests for receipt hash computation ──


def test_compute_receipt_hash_deterministic():
    """Same receipt data produces same hash."""
    data = {
        "receipt_id": "rcpt_abc123",
        "receipt_version": "1.0",
        "execution_id": "exec_001",
        "chain_sequence": 1,
        "previous_receipt_hash": None,
        "capability_id": "search.query",
        "status": "success",
        "agent_id": "agent_001",
        "provider_id": "brave-search-api",
        "credential_mode": "rhumb_managed",
    }
    h1 = _compute_receipt_hash(data)
    h2 = _compute_receipt_hash(data)
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_compute_receipt_hash_changes_with_data():
    """Changing any field changes the hash."""
    data1 = {
        "receipt_id": "rcpt_abc",
        "chain_sequence": 1,
        "status": "success",
    }
    data2 = {**data1, "status": "failure"}
    assert _compute_receipt_hash(data1) != _compute_receipt_hash(data2)


# ── Integration tests with mocked Supabase ──


@pytest.fixture
def receipt_service():
    return ReceiptService()


@pytest.fixture
def mock_supabase():
    """Mock supabase_fetch, supabase_insert, supabase_patch."""
    with patch("services.receipt_service.supabase_fetch") as mock_fetch, \
         patch("services.receipt_service.supabase_insert") as mock_insert, \
         patch("services.receipt_service.supabase_patch") as mock_patch:
        mock_fetch.return_value = [{"last_sequence": 0, "last_receipt_hash": None}]
        mock_insert.return_value = True
        mock_patch.return_value = True
        yield {
            "fetch": mock_fetch,
            "insert": mock_insert,
            "patch": mock_patch,
        }


@pytest.mark.asyncio
async def test_create_receipt_basic(receipt_service, mock_supabase):
    """Create a receipt and verify it has correct structure."""
    receipt = await receipt_service.create_receipt(ReceiptInput(
        execution_id="exec_test_001",
        capability_id="search.query",
        status="success",
        agent_id="agent_test",
        provider_id="brave-search-api",
        credential_mode="rhumb_managed",
        org_id="org_test",
        total_latency_ms=250.0,
        provider_latency_ms=200.0,
        rhumb_overhead_ms=50.0,
    ))

    assert receipt.receipt_id.startswith("rcpt_")
    assert receipt.receipt_version == "1.0"
    assert receipt.execution_id == "exec_test_001"
    assert receipt.capability_id == "search.query"
    assert receipt.status == "success"
    assert receipt.agent_id == "agent_test"
    assert receipt.provider_id == "brave-search-api"
    assert receipt.credential_mode == "rhumb_managed"
    assert receipt.chain_sequence == 1
    assert receipt.previous_receipt_hash is None  # First receipt in chain
    assert receipt.receipt_hash.startswith("sha256:")


@pytest.mark.asyncio
async def test_create_receipt_chain_sequence_increments(receipt_service, mock_supabase):
    """Second receipt gets sequence 2 and links to first receipt's hash."""
    # First receipt
    receipt1 = await receipt_service.create_receipt(ReceiptInput(
        execution_id="exec_001",
        capability_id="search.query",
        status="success",
        agent_id="agent_test",
        provider_id="brave",
        credential_mode="byo",
    ))

    # Simulate chain state after first receipt
    mock_supabase["fetch"].return_value = [{
        "last_sequence": 1,
        "last_receipt_hash": receipt1.receipt_hash,
    }]

    receipt2 = await receipt_service.create_receipt(ReceiptInput(
        execution_id="exec_002",
        capability_id="data.enrich_person",
        status="success",
        agent_id="agent_test",
        provider_id="apollo",
        credential_mode="rhumb_managed",
    ))

    assert receipt2.chain_sequence == 2
    assert receipt2.previous_receipt_hash == receipt1.receipt_hash
    assert receipt2.receipt_hash != receipt1.receipt_hash


@pytest.mark.asyncio
async def test_create_receipt_failure_status(receipt_service, mock_supabase):
    """Failure receipts include error fields."""
    receipt = await receipt_service.create_receipt(ReceiptInput(
        execution_id="exec_fail",
        capability_id="ai.generate_text",
        status="failure",
        agent_id="agent_test",
        provider_id="openai",
        credential_mode="byo",
        error_code="429",
        error_message="Rate limit exceeded",
        error_provider_raw='{"error": {"message": "Rate limit exceeded"}}',
    ))

    assert receipt.status == "failure"
    assert receipt.extra.get("error_code") == "429"
    assert receipt.extra.get("error_message") == "Rate limit exceeded"


@pytest.mark.asyncio
async def test_create_receipt_with_x402(receipt_service, mock_supabase):
    """x402 payment context is captured in receipt."""
    receipt = await receipt_service.create_receipt(ReceiptInput(
        execution_id="exec_x402",
        capability_id="search.query",
        status="success",
        agent_id="x402_wallet_0xabc",
        provider_id="tavily",
        credential_mode="rhumb_managed",
        x402_tx_hash="0xdef456",
        x402_network="base",
        x402_payer="0xabc123",
    ))

    assert receipt.extra.get("x402_tx_hash") == "0xdef456"
    assert receipt.extra.get("x402_network") == "base"
    assert receipt.extra.get("x402_payer") == "0xabc123"


@pytest.mark.asyncio
async def test_create_receipt_inserts_to_supabase(receipt_service, mock_supabase):
    """Verify the receipt is written to supabase via INSERT."""
    await receipt_service.create_receipt(ReceiptInput(
        execution_id="exec_insert",
        capability_id="search.query",
        status="success",
        agent_id="agent_test",
        provider_id="exa",
        credential_mode="byo",
    ))

    mock_supabase["insert"].assert_called_once()
    call_args = mock_supabase["insert"].call_args
    assert call_args[0][0] == "execution_receipts"
    inserted_data = call_args[0][1]
    assert inserted_data["receipt_id"].startswith("rcpt_")
    assert inserted_data["execution_id"] == "exec_insert"
    assert inserted_data["receipt_hash"].startswith("sha256:")


@pytest.mark.asyncio
async def test_get_receipt(receipt_service, mock_supabase):
    """Fetch a receipt by ID."""
    mock_supabase["fetch"].return_value = [{
        "receipt_id": "rcpt_test123",
        "execution_id": "exec_001",
        "status": "success",
    }]

    result = await receipt_service.get_receipt("rcpt_test123")
    assert result is not None
    assert result["receipt_id"] == "rcpt_test123"


@pytest.mark.asyncio
async def test_get_receipt_not_found(receipt_service, mock_supabase):
    """Return None when receipt not found."""
    mock_supabase["fetch"].return_value = []

    result = await receipt_service.get_receipt("rcpt_nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_query_receipts(receipt_service, mock_supabase):
    """Query receipts with filters."""
    mock_supabase["fetch"].return_value = [
        {"receipt_id": "rcpt_1", "agent_id": "agent_test"},
        {"receipt_id": "rcpt_2", "agent_id": "agent_test"},
    ]

    results = await receipt_service.query_receipts(agent_id="agent_test", limit=10)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_verify_chain_intact(receipt_service, mock_supabase):
    """Chain verification passes when hashes link correctly."""
    mock_supabase["fetch"].return_value = [
        {
            "receipt_id": "rcpt_1",
            "receipt_hash": "sha256:aaa",
            "previous_receipt_hash": None,
            "chain_sequence": 1,
        },
        {
            "receipt_id": "rcpt_2",
            "receipt_hash": "sha256:bbb",
            "previous_receipt_hash": "sha256:aaa",
            "chain_sequence": 2,
        },
        {
            "receipt_id": "rcpt_3",
            "receipt_hash": "sha256:ccc",
            "previous_receipt_hash": "sha256:bbb",
            "chain_sequence": 3,
        },
    ]

    result = await receipt_service.verify_chain()
    assert result["chain_intact"] is True
    assert result["verified"] == 3
    assert result["broken_links"] == []


@pytest.mark.asyncio
async def test_verify_chain_broken(receipt_service, mock_supabase):
    """Chain verification detects broken links."""
    mock_supabase["fetch"].return_value = [
        {
            "receipt_id": "rcpt_1",
            "receipt_hash": "sha256:aaa",
            "previous_receipt_hash": None,
            "chain_sequence": 1,
        },
        {
            "receipt_id": "rcpt_2",
            "receipt_hash": "sha256:bbb",
            "previous_receipt_hash": "sha256:WRONG",  # Broken link!
            "chain_sequence": 2,
        },
    ]

    result = await receipt_service.verify_chain()
    assert result["chain_intact"] is False
    assert len(result["broken_links"]) == 1
    assert result["broken_links"][0]["receipt_id"] == "rcpt_2"
