"""Async batch query logger for usage analytics instrumentation.

Logs API queries to the ``query_logs`` Supabase table with:
- Async batch writes (queue up to 10 logs, flush every 5 seconds)
- Feature flag: ``ENABLE_QUERY_LOGGING`` (default: true)
- Rate limiting: max 1000 logs/min per source (drop excess silently)
- Non-blocking: logging errors never fail the request

WU 3.5: Usage Analytics Instrumentation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from services.payload_redactor import sanitize_external_payload

logger = logging.getLogger(__name__)

# Agent identification patterns in User-Agent strings
AGENT_PATTERNS = [
    (re.compile(r"Claude", re.IGNORECASE), "claude"),
    (re.compile(r"GPT", re.IGNORECASE), "gpt"),
    (re.compile(r"Gemini", re.IGNORECASE), "gemini"),
    (re.compile(r"Agent[:\s/]+(\S+)", re.IGNORECASE), None),  # dynamic
    (re.compile(r"Bot[:\s/]+(\S+)", re.IGNORECASE), None),  # dynamic
    (re.compile(r"\bBot\b", re.IGNORECASE), "bot"),
    (re.compile(r"\bAgent\b", re.IGNORECASE), "agent"),
]

EXPLICIT_SOURCE_MAP = {
    "api": "api_direct",
    "api_direct": "api_direct",
    "cli": "cli",
    "mcp": "mcp",
    "unknown_agent": "unknown_agent",
    "web": "web",
}


def extract_agent_id(user_agent: Optional[str], headers: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Extract agent identifier from User-Agent string or headers.

    Looks for known agent patterns (Claude, GPT, Gemini, Bot, Agent).
    Also checks for ``X-Agent-Id`` header if provided.

    Returns:
        Agent identifier string, or None if no agent detected.
    """
    # Check explicit agent header first
    if headers:
        for header_name in ("x-agent-id", "x-agent-name"):
            value = headers.get(header_name)
            if value:
                return value

    if not user_agent:
        return None

    for pattern, static_id in AGENT_PATTERNS:
        match = pattern.search(user_agent)
        if match:
            if static_id is not None:
                return static_id
            # Dynamic extraction from capture group
            if match.lastindex and match.lastindex >= 1:
                return match.group(1).strip()
            return match.group(0).strip()

    return None


def classify_query_source(
    user_agent: Optional[str],
    headers: Optional[Dict[str, str]] = None,
    agent_id: Optional[str] = None,
) -> str:
    """Classify query source using explicit client headers first, then safe heuristics."""
    normalized_headers = {k.lower(): v for k, v in (headers or {}).items()}

    explicit_source = (
        normalized_headers.get("x-rhumb-client")
        or normalized_headers.get("x-rhumb-source")
        or ""
    ).strip().lower()
    if explicit_source in EXPLICIT_SOURCE_MAP:
        return EXPLICIT_SOURCE_MAP[explicit_source]

    normalized_ua = (user_agent or "").lower()
    if "rhumb-mcp" in normalized_ua or " modelcontextprotocol" in normalized_ua:
        return "mcp"
    if "rhumb-cli" in normalized_ua:
        return "cli"

    if normalized_headers.get("x-rhumb-key") or normalized_headers.get("authorization"):
        return "api_direct"

    if agent_id:
        return "unknown_agent"

    return "web"


class QueryLogger:
    """Async batch query logger with rate limiting and feature flag.

    Usage::

        from services.query_logger import query_logger

        await query_logger.log(
            source="web",
            query_type="search",
            query_text="stripe",
            query_params={"query": "stripe", "limit": 10},
            agent_id=None,
            user_agent="Mozilla/5.0 ...",
            result_count=5,
            result_status="success",
            latency_ms=42,
        )
    """

    BATCH_SIZE = 10
    FLUSH_INTERVAL_SECONDS = 5.0
    RATE_LIMIT_PER_MIN = 1000

    def __init__(self, supabase_client: Any = None) -> None:
        self._supabase = supabase_client
        self._queue: List[Dict[str, Any]] = []
        self._flush_task: Optional[asyncio.Task[None]] = None
        self._lock = asyncio.Lock()
        self._started = False

        # Rate limiting: track counts per source per minute
        self._rate_counts: Dict[str, int] = defaultdict(int)
        self._rate_window_start: float = time.monotonic()

    @property
    def enabled(self) -> bool:
        """Check if query logging is enabled via feature flag."""
        flag = os.environ.get("ENABLE_QUERY_LOGGING", "true")
        return flag.lower() not in ("false", "0", "no", "off")

    @property
    def queue_size(self) -> int:
        """Current number of items in the queue."""
        return len(self._queue)

    async def log(
        self,
        source: str,
        query_type: str,
        query_text: str,
        query_params: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        user_agent: Optional[str] = None,
        result_count: Optional[int] = None,
        result_status: str = "success",
        latency_ms: Optional[int] = None,
    ) -> None:
        """Queue a query log entry for batch insertion.

        This method is non-blocking — it appends to an internal queue
        and flushes when the batch size or timer threshold is reached.

        If the feature flag is disabled or rate limit is exceeded,
        the entry is silently dropped.
        """
        if not self.enabled:
            return

        # Rate limiting per source
        if not self._check_rate_limit(source):
            return

        safe_query_text = sanitize_external_payload(
            query_text,
            max_depth=1,
            max_items=10,
            max_string_length=256,
            strict=True,
        )
        if not isinstance(safe_query_text, str):
            safe_query_text = str(safe_query_text)

        safe_query_params = sanitize_external_payload(
            query_params or {},
            max_depth=4,
            max_items=25,
            max_string_length=256,
            strict=True,
        )
        if not isinstance(safe_query_params, dict):
            safe_query_params = {"value": safe_query_params}

        safe_user_agent = sanitize_external_payload(
            user_agent,
            max_depth=1,
            max_items=5,
            max_string_length=256,
            strict=True,
        )
        if safe_user_agent is not None and not isinstance(safe_user_agent, str):
            safe_user_agent = str(safe_user_agent)

        entry = {
            "source": source,
            "query_type": query_type,
            "query_text": safe_query_text,
            "query_params": safe_query_params,
            "agent_id": agent_id,
            "user_agent": safe_user_agent,
            "result_count": result_count,
            "result_status": result_status,
            "latency_ms": latency_ms,
        }

        async with self._lock:
            self._queue.append(entry)

            # Start background flush timer if not running
            if not self._started:
                self._start_flush_timer()

            # Flush immediately if batch is full
            if len(self._queue) >= self.BATCH_SIZE:
                await self._flush_locked()

    async def flush(self) -> int:
        """Manually flush all queued entries.

        Returns:
            Number of entries flushed.
        """
        async with self._lock:
            return await self._flush_locked()

    async def _flush_locked(self) -> int:
        """Flush queue while lock is held.

        Returns:
            Number of entries flushed.
        """
        if not self._queue:
            return 0

        batch = self._queue[:]
        self._queue.clear()
        count = len(batch)

        try:
            if self._supabase is not None:
                await self._supabase.table("query_logs").insert(batch).execute()
            else:
                # No Supabase client — attempt lazy initialization
                client = await self._get_supabase_client()
                if client is not None:
                    await client.table("query_logs").insert(batch).execute()
                else:
                    logger.debug(
                        "query_logger: no Supabase client, dropping %d entries", count
                    )
                    return 0
        except Exception:
            logger.warning(
                "query_logger: failed to flush %d entries", count, exc_info=True
            )
            return 0

        logger.debug("query_logger: flushed %d entries", count)
        return count

    def _check_rate_limit(self, source: str) -> bool:
        """Check and update rate limit for a source.

        Resets the window every 60 seconds. Returns True if under limit.
        """
        now = time.monotonic()
        elapsed = now - self._rate_window_start

        if elapsed >= 60.0:
            # Reset window
            self._rate_counts.clear()
            self._rate_window_start = now

        current = self._rate_counts[source]
        if current >= self.RATE_LIMIT_PER_MIN:
            logger.warning(
                "query_logger: rate limit exceeded for source '%s' (%d/%d per min)",
                source,
                current,
                self.RATE_LIMIT_PER_MIN,
            )
            return False

        self._rate_counts[source] += 1
        return True

    def _start_flush_timer(self) -> None:
        """Start periodic background flush task."""
        self._started = True
        try:
            loop = asyncio.get_running_loop()
            self._flush_task = loop.create_task(self._periodic_flush())
        except RuntimeError:
            # No running event loop — timer will not run
            self._started = False

    async def _periodic_flush(self) -> None:
        """Periodically flush the queue every FLUSH_INTERVAL_SECONDS."""
        while True:
            await asyncio.sleep(self.FLUSH_INTERVAL_SECONDS)
            try:
                async with self._lock:
                    await self._flush_locked()
            except Exception:
                logger.warning("query_logger: periodic flush error", exc_info=True)

    async def _get_supabase_client(self) -> Any:
        """Lazy-load Supabase client from db module."""
        try:
            from db.client import get_supabase_client
            client = await get_supabase_client()
            self._supabase = client
            return client
        except Exception:
            return None

    def reset(self) -> None:
        """Reset logger state (for testing)."""
        self._queue.clear()
        self._rate_counts.clear()
        self._rate_window_start = time.monotonic()
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        self._started = False
        self._supabase = None


# ── Singleton ────────────────────────────────────────────────────────

query_logger = QueryLogger()
