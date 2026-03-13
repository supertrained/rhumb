"""Unit tests for QueryLogger — batch queueing, timer flush, rate limiting, feature flag."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from services.query_logger import QueryLogger, extract_agent_id


# ── Helper: mock Supabase client ──────────────────────────────────


class MockSupabaseTable:
    """Captures insert calls for assertion."""

    def __init__(self) -> None:
        self.inserted: List[List[Dict[str, Any]]] = []

    def insert(self, rows: List[Dict[str, Any]]) -> "MockSupabaseTable":
        self.inserted.append(rows)
        return self

    async def execute(self) -> None:
        pass


class MockSupabaseClient:
    """Minimal mock Supabase client."""

    def __init__(self) -> None:
        self._tables: Dict[str, MockSupabaseTable] = {}

    def table(self, name: str) -> MockSupabaseTable:
        if name not in self._tables:
            self._tables[name] = MockSupabaseTable()
        return self._tables[name]

    @property
    def query_logs_table(self) -> MockSupabaseTable:
        return self.table("query_logs")


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def mock_supabase() -> MockSupabaseClient:
    return MockSupabaseClient()


@pytest.fixture
def logger_with_mock(mock_supabase: MockSupabaseClient) -> QueryLogger:
    ql = QueryLogger(supabase_client=mock_supabase)
    return ql


# ── Test: Batch Queueing ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_queueing_10_items_single_insert(mock_supabase: MockSupabaseClient) -> None:
    """Queuing 10 items should trigger exactly 1 batch insert."""
    ql = QueryLogger(supabase_client=mock_supabase)

    for i in range(10):
        await ql.log(
            source="web",
            query_type="search",
            query_text=f"query_{i}",
            result_count=i,
            result_status="success",
            latency_ms=10 + i,
        )

    table = mock_supabase.query_logs_table
    assert len(table.inserted) == 1, f"Expected 1 insert call, got {len(table.inserted)}"
    assert len(table.inserted[0]) == 10, f"Expected 10 rows in batch, got {len(table.inserted[0])}"
    ql.reset()


@pytest.mark.asyncio
async def test_queue_under_batch_size_no_auto_flush(mock_supabase: MockSupabaseClient) -> None:
    """Queuing fewer than 10 items should NOT auto-flush."""
    ql = QueryLogger(supabase_client=mock_supabase)

    for i in range(5):
        await ql.log(
            source="web",
            query_type="search",
            query_text=f"query_{i}",
            result_status="success",
        )

    table = mock_supabase.query_logs_table
    assert len(table.inserted) == 0, "Should not auto-flush under batch size"
    assert ql.queue_size == 5
    ql.reset()


@pytest.mark.asyncio
async def test_manual_flush(mock_supabase: MockSupabaseClient) -> None:
    """Manual flush should write all queued items."""
    ql = QueryLogger(supabase_client=mock_supabase)

    for i in range(3):
        await ql.log(
            source="web",
            query_type="search",
            query_text=f"query_{i}",
            result_status="success",
        )

    flushed = await ql.flush()
    assert flushed == 3

    table = mock_supabase.query_logs_table
    assert len(table.inserted) == 1
    assert len(table.inserted[0]) == 3
    assert ql.queue_size == 0
    ql.reset()


# ── Test: Timer Flush ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timer_flush_after_interval(mock_supabase: MockSupabaseClient) -> None:
    """Background timer should flush after FLUSH_INTERVAL_SECONDS."""
    ql = QueryLogger(supabase_client=mock_supabase)
    ql.FLUSH_INTERVAL_SECONDS = 0.1  # Speed up for testing

    await ql.log(
        source="web",
        query_type="search",
        query_text="timer_test",
        result_status="success",
    )

    # Wait for timer to fire
    await asyncio.sleep(0.3)

    table = mock_supabase.query_logs_table
    assert len(table.inserted) >= 1, "Timer should have flushed the queue"
    assert ql.queue_size == 0
    ql.reset()


# ── Test: Rate Limiting ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_enforcement(mock_supabase: MockSupabaseClient) -> None:
    """Exceeding 1000 logs/min per source should silently drop excess."""
    ql = QueryLogger(supabase_client=mock_supabase)
    ql.RATE_LIMIT_PER_MIN = 50  # Lower for test speed

    # Log 70 entries (50 should pass, 20 should be dropped)
    for i in range(70):
        await ql.log(
            source="rate_test",
            query_type="search",
            query_text=f"query_{i}",
            result_status="success",
        )

    # Flush remaining
    await ql.flush()

    table = mock_supabase.query_logs_table
    total_rows = sum(len(batch) for batch in table.inserted)
    assert total_rows == 50, f"Expected exactly 50 (rate-limited), got {total_rows}"
    ql.reset()


@pytest.mark.asyncio
async def test_rate_limit_resets_after_window(mock_supabase: MockSupabaseClient) -> None:
    """Rate limit window should reset after 60 seconds."""
    ql = QueryLogger(supabase_client=mock_supabase)
    ql.RATE_LIMIT_PER_MIN = 5

    # Fill up the limit
    for i in range(5):
        await ql.log(source="reset_test", query_type="search", query_text=f"q{i}", result_status="success")

    # This one should be dropped
    await ql.log(source="reset_test", query_type="search", query_text="dropped", result_status="success")
    assert ql.queue_size == 5  # Only 5 made it

    # Simulate window reset
    import time
    ql._rate_window_start = time.monotonic() - 61

    # Now it should accept again
    await ql.log(source="reset_test", query_type="search", query_text="accepted", result_status="success")
    assert ql.queue_size == 6
    ql.reset()


# ── Test: Feature Flag ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_feature_flag_disabled(mock_supabase: MockSupabaseClient) -> None:
    """When ENABLE_QUERY_LOGGING=false, no entries should be queued."""
    ql = QueryLogger(supabase_client=mock_supabase)

    with patch.dict(os.environ, {"ENABLE_QUERY_LOGGING": "false"}):
        for i in range(20):
            await ql.log(
                source="web",
                query_type="search",
                query_text=f"query_{i}",
                result_status="success",
            )

    assert ql.queue_size == 0
    table = mock_supabase.query_logs_table
    assert len(table.inserted) == 0
    ql.reset()


@pytest.mark.asyncio
async def test_feature_flag_enabled_by_default(mock_supabase: MockSupabaseClient) -> None:
    """Feature flag should be enabled by default."""
    ql = QueryLogger(supabase_client=mock_supabase)

    # Remove the env var to test default
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ENABLE_QUERY_LOGGING", None)
        assert ql.enabled is True
    ql.reset()


# ── Test: Agent ID Extraction ────────────────────────────────────


def test_extract_agent_id_claude() -> None:
    assert extract_agent_id("Mozilla/5.0 Claude-Web/1.0") == "claude"


def test_extract_agent_id_gpt() -> None:
    assert extract_agent_id("GPT-4-Turbo/2024") == "gpt"


def test_extract_agent_id_gemini() -> None:
    assert extract_agent_id("Google-Gemini/1.0") == "gemini"


def test_extract_agent_id_bot_with_name() -> None:
    result = extract_agent_id("Bot: MyCustomBot/1.0")
    assert result is not None


def test_extract_agent_id_agent_with_name() -> None:
    result = extract_agent_id("Agent: rhumb-tester/1.0")
    assert result is not None


def test_extract_agent_id_plain_browser() -> None:
    assert extract_agent_id("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)") is None


def test_extract_agent_id_none() -> None:
    assert extract_agent_id(None) is None


def test_extract_agent_id_empty() -> None:
    assert extract_agent_id("") is None


def test_extract_agent_id_from_header() -> None:
    assert extract_agent_id("Mozilla/5.0", headers={"x-agent-id": "my-agent"}) == "my-agent"


def test_extract_agent_id_header_takes_priority() -> None:
    """X-Agent-Id header should take priority over User-Agent parsing."""
    assert extract_agent_id("Claude/1.0", headers={"x-agent-id": "custom-bot"}) == "custom-bot"


# ── Test: Log Entry Structure ────────────────────────────────────


@pytest.mark.asyncio
async def test_log_entry_structure(mock_supabase: MockSupabaseClient) -> None:
    """Verify the structure of logged entries."""
    ql = QueryLogger(supabase_client=mock_supabase)

    await ql.log(
        source="web",
        query_type="search",
        query_text="stripe payments",
        query_params={"query": "stripe payments", "limit": 10, "category": "payments"},
        agent_id="claude",
        user_agent="Claude-Web/1.0",
        result_count=5,
        result_status="success",
        latency_ms=42,
    )

    flushed = await ql.flush()
    assert flushed == 1

    table = mock_supabase.query_logs_table
    entry = table.inserted[0][0]

    assert entry["source"] == "web"
    assert entry["query_type"] == "search"
    assert entry["query_text"] == "stripe payments"
    assert entry["query_params"] == {"query": "stripe payments", "limit": 10, "category": "payments"}
    assert entry["agent_id"] == "claude"
    assert entry["user_agent"] == "Claude-Web/1.0"
    assert entry["result_count"] == 5
    assert entry["result_status"] == "success"
    assert entry["latency_ms"] == 42
    ql.reset()


# ── Test: Multiple Batches ───────────────────────────────────────


@pytest.mark.asyncio
async def test_multiple_batches(mock_supabase: MockSupabaseClient) -> None:
    """Logging 25 items should result in 2 batch inserts + 5 remaining."""
    ql = QueryLogger(supabase_client=mock_supabase)

    for i in range(25):
        await ql.log(
            source="web",
            query_type="search",
            query_text=f"query_{i}",
            result_status="success",
        )

    # Should have auto-flushed twice (at 10 and 20)
    table = mock_supabase.query_logs_table
    assert len(table.inserted) == 2
    assert len(table.inserted[0]) == 10
    assert len(table.inserted[1]) == 10

    # 5 remaining in queue
    assert ql.queue_size == 5

    # Flush the rest
    flushed = await ql.flush()
    assert flushed == 5
    assert len(table.inserted) == 3
    ql.reset()


# ── Test: Flush Error Handling ───────────────────────────────────


@pytest.mark.asyncio
async def test_flush_error_does_not_raise() -> None:
    """Supabase errors during flush should be caught, not propagated."""
    mock = MockSupabaseClient()
    # Make insert raise
    original_insert = mock.query_logs_table.insert
    def bad_insert(rows: list) -> Any:
        raise RuntimeError("Supabase connection failed")
    mock.query_logs_table.insert = bad_insert  # type: ignore[assignment]

    ql = QueryLogger(supabase_client=mock)

    await ql.log(source="web", query_type="search", query_text="error_test", result_status="success")

    # Should not raise
    flushed = await ql.flush()
    assert flushed == 0  # Failed to flush
    assert ql.queue_size == 0  # Queue was cleared despite error
    ql.reset()
