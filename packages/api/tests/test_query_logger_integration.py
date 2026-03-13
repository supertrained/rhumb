"""Integration tests for query logging middleware.

Verifies that API route calls produce query_logs entries via the
QueryLoggingMiddleware + QueryLogger pipeline.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from app import app
from services.query_logger import query_logger


# ── Helper: capture logger output ────────────────────────────────


class CaptureSupabase:
    """Mock Supabase client that captures inserts."""

    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []

    def table(self, name: str) -> "CaptureSupabase":
        return self

    def insert(self, rows: List[Dict[str, Any]]) -> "CaptureSupabase":
        self.rows.extend(rows)
        return self

    async def execute(self) -> None:
        pass


@pytest.fixture
def capture_client():
    """Patch the global query_logger with a capturing Supabase mock."""
    capture = CaptureSupabase()
    query_logger.reset()
    query_logger._supabase = capture

    client = TestClient(app)
    yield client, capture

    # Cleanup
    query_logger.reset()


def _flush_sync() -> None:
    """Synchronously flush the query logger."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(lambda: asyncio.run(query_logger.flush())).result()
        else:
            loop.run_until_complete(query_logger.flush())
    except RuntimeError:
        asyncio.run(query_logger.flush())


# ── Test: Search route logs queries ──────────────────────────────


def test_search_route_logs_query(capture_client: tuple) -> None:
    """GET /v1/search?q=stripe should produce a query_logs entry."""
    client, capture = capture_client

    response = client.get("/v1/search?q=stripe")
    assert response.status_code == 200

    _flush_sync()

    assert len(capture.rows) >= 1, f"Expected at least 1 log entry, got {len(capture.rows)}"

    entry = capture.rows[0]
    assert entry["source"] == "web"
    assert entry["query_type"] == "search"
    assert entry["query_text"] == "stripe"
    assert entry["query_params"]["query"] == "stripe"
    assert entry["result_status"] == "success"
    assert isinstance(entry["latency_ms"], int)
    assert entry["latency_ms"] >= 0


# ── Test: Leaderboard route logs queries ─────────────────────────


def test_leaderboard_route_logs_query(capture_client: tuple) -> None:
    """GET /v1/leaderboard/payments should log a list_by_category query."""
    client, capture = capture_client

    response = client.get("/v1/leaderboard/payments")
    assert response.status_code == 200

    _flush_sync()

    assert len(capture.rows) >= 1

    entry = capture.rows[0]
    assert entry["source"] == "web"
    assert entry["query_type"] == "list_by_category"
    assert entry["query_text"] == "payments"
    assert entry["query_params"]["category"] == "payments"


# ── Test: Service detail route logs queries ──────────────────────


def test_service_route_logs_query(capture_client: tuple) -> None:
    """GET /v1/services/stripe should log a score_lookup query."""
    client, capture = capture_client

    response = client.get("/v1/services/stripe")
    assert response.status_code == 200

    _flush_sync()

    assert len(capture.rows) >= 1

    entry = capture.rows[0]
    assert entry["source"] == "web"
    assert entry["query_type"] == "score_lookup"
    assert entry["query_text"] == "stripe"
    assert entry["query_params"]["slug"] == "stripe"


# ── Test: Non-instrumented routes are NOT logged ─────────────────


def test_healthz_not_logged(capture_client: tuple) -> None:
    """GET /healthz should NOT produce a query_logs entry."""
    client, capture = capture_client

    response = client.get("/healthz")
    assert response.status_code == 200

    _flush_sync()

    assert len(capture.rows) == 0


# ── Test: Agent ID extraction from User-Agent header ─────────────


def test_agent_id_extracted_from_user_agent(capture_client: tuple) -> None:
    """Requests with Claude in User-Agent should populate agent_id."""
    client, capture = capture_client

    response = client.get(
        "/v1/search?q=test",
        headers={"User-Agent": "Claude-Web/1.0 (rhumb-discovery)"},
    )
    assert response.status_code == 200

    _flush_sync()

    assert len(capture.rows) >= 1
    assert capture.rows[0]["agent_id"] == "claude"


def test_no_agent_id_for_plain_browser(capture_client: tuple) -> None:
    """Regular browser User-Agent should have agent_id=None."""
    client, capture = capture_client

    response = client.get(
        "/v1/search?q=test",
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
    )
    assert response.status_code == 200

    _flush_sync()

    assert len(capture.rows) >= 1
    assert capture.rows[0]["agent_id"] is None


# ── Test: Latency is recorded correctly ──────────────────────────


def test_latency_recorded_correctly(capture_client: tuple) -> None:
    """Latency should be a non-negative integer in milliseconds."""
    client, capture = capture_client

    response = client.get("/v1/search?q=email")
    assert response.status_code == 200

    _flush_sync()

    assert len(capture.rows) >= 1
    latency = capture.rows[0]["latency_ms"]
    assert isinstance(latency, int)
    assert latency >= 0
    assert latency < 5000


# ── Test: Result count is extracted ──────────────────────────────


def test_search_result_count_extracted(capture_client: tuple) -> None:
    """Search results count should be extracted from response body."""
    client, capture = capture_client

    response = client.get("/v1/search?q=stripe")
    assert response.status_code == 200

    resp_data = response.json()
    expected_count = len(resp_data.get("data", {}).get("results", []))

    _flush_sync()

    assert len(capture.rows) >= 1
    assert capture.rows[0]["result_count"] == expected_count


# ── Test: Category not found status ──────────────────────────────


def test_leaderboard_not_found_status(capture_client: tuple) -> None:
    """Non-existent category should log result_status='not_found'."""
    client, capture = capture_client

    response = client.get("/v1/leaderboard/nonexistent-category-xyz")
    assert response.status_code == 200  # API returns 200 with error field

    _flush_sync()

    assert len(capture.rows) >= 1
    # The response has an error field saying "Category not found"
    assert capture.rows[0]["result_status"] == "not_found"
