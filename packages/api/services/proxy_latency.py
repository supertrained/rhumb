"""Latency measurement and aggregation for proxy service.

Tracks per-call latency with perf_counter precision.
Maintains a 5-minute rolling window of measurements per service+agent pair.
Computes P50, P95, P99 percentiles and mean.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


@dataclass
class LatencyRecord:
    """A single latency measurement."""

    service: str
    agent_id: str
    latency_ms: float
    timestamp: float  # time.time() for wall-clock
    perf_start: float  # time.perf_counter() start
    perf_end: float  # time.perf_counter() end
    status_code: int = 0
    success: bool = True


@dataclass
class LatencySnapshot:
    """Aggregated latency statistics for a time window."""

    service: str
    agent_id: str
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    mean_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    count: int = 0
    error_count: int = 0
    window_start: float = 0.0
    window_end: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API response."""
        return {
            "service": self.service,
            "agent_id": self.agent_id,
            "p50_ms": round(self.p50_ms, 3),
            "p95_ms": round(self.p95_ms, 3),
            "p99_ms": round(self.p99_ms, 3),
            "mean_ms": round(self.mean_ms, 3),
            "min_ms": round(self.min_ms, 3),
            "max_ms": round(self.max_ms, 3),
            "count": self.count,
            "error_count": self.error_count,
            "window_start": self.window_start,
            "window_end": self.window_end,
        }


class LatencyTracker:
    """Per-call latency tracking with rolling window aggregation.

    Maintains a 5-minute (default) sliding window of latency records
    per service+agent pair. Computes percentile statistics on demand.
    """

    DEFAULT_WINDOW_SECONDS: float = 300.0  # 5 minutes

    def __init__(self, window_seconds: float = DEFAULT_WINDOW_SECONDS) -> None:
        self._window_seconds = window_seconds
        self._records: dict[str, list[LatencyRecord]] = {}

    def _key(self, service: str, agent_id: str) -> str:
        """Generate lookup key."""
        return f"{service}:{agent_id}"

    def _prune(self, key: str) -> None:
        """Remove records outside the rolling window."""
        if key not in self._records:
            return
        cutoff = time.time() - self._window_seconds
        self._records[key] = [r for r in self._records[key] if r.timestamp > cutoff]

    def record(
        self,
        service: str,
        agent_id: str,
        latency_ms: float,
        perf_start: float,
        perf_end: float,
        status_code: int = 200,
        success: bool = True,
    ) -> LatencyRecord:
        """Record a latency measurement.

        Args:
            service: Provider service name.
            agent_id: Agent identifier.
            latency_ms: Measured latency in milliseconds.
            perf_start: perf_counter() value at call start.
            perf_end: perf_counter() value at call end.
            status_code: HTTP response status code.
            success: Whether the call was successful.

        Returns:
            The recorded LatencyRecord.
        """
        key = self._key(service, agent_id)
        record = LatencyRecord(
            service=service,
            agent_id=agent_id,
            latency_ms=latency_ms,
            timestamp=time.time(),
            perf_start=perf_start,
            perf_end=perf_end,
            status_code=status_code,
            success=success,
        )

        if key not in self._records:
            self._records[key] = []
        self._records[key].append(record)
        self._prune(key)

        return record

    def get_snapshot(
        self, service: str, agent_id: str = "default"
    ) -> LatencySnapshot:
        """Compute percentile statistics for a service+agent pair.

        Args:
            service: Provider service name.
            agent_id: Agent identifier.

        Returns:
            LatencySnapshot with P50/P95/P99/mean/min/max statistics.
        """
        key = self._key(service, agent_id)
        self._prune(key)

        records = self._records.get(key, [])
        if not records:
            return LatencySnapshot(service=service, agent_id=agent_id)

        latencies = np.array([r.latency_ms for r in records])
        error_count = sum(1 for r in records if not r.success)

        return LatencySnapshot(
            service=service,
            agent_id=agent_id,
            p50_ms=float(np.percentile(latencies, 50)),
            p95_ms=float(np.percentile(latencies, 95)),
            p99_ms=float(np.percentile(latencies, 99)),
            mean_ms=float(np.mean(latencies)),
            min_ms=float(np.min(latencies)),
            max_ms=float(np.max(latencies)),
            count=len(records),
            error_count=error_count,
            window_start=records[0].timestamp,
            window_end=records[-1].timestamp,
        )

    def get_all_snapshots(self) -> dict[str, LatencySnapshot]:
        """Compute snapshots for all tracked service+agent pairs.

        Returns:
            Dict mapping keys to their LatencySnapshots.
        """
        snapshots: dict[str, LatencySnapshot] = {}
        for key in list(self._records.keys()):
            self._prune(key)
            records = self._records.get(key, [])
            if not records:
                continue
            service = records[0].service
            agent_id = records[0].agent_id
            snapshots[key] = self.get_snapshot(service, agent_id)
        return snapshots

    def get_global_snapshot(self) -> LatencySnapshot:
        """Compute aggregate statistics across all services.

        Returns:
            LatencySnapshot aggregated across all service+agent pairs.
        """
        all_latencies: list[float] = []
        error_count = 0
        earliest = float("inf")
        latest = 0.0

        for key in list(self._records.keys()):
            self._prune(key)
            for record in self._records.get(key, []):
                all_latencies.append(record.latency_ms)
                if not record.success:
                    error_count += 1
                earliest = min(earliest, record.timestamp)
                latest = max(latest, record.timestamp)

        if not all_latencies:
            return LatencySnapshot(service="global", agent_id="all")

        latencies = np.array(all_latencies)
        return LatencySnapshot(
            service="global",
            agent_id="all",
            p50_ms=float(np.percentile(latencies, 50)),
            p95_ms=float(np.percentile(latencies, 95)),
            p99_ms=float(np.percentile(latencies, 99)),
            mean_ms=float(np.mean(latencies)),
            min_ms=float(np.min(latencies)),
            max_ms=float(np.max(latencies)),
            count=len(all_latencies),
            error_count=error_count,
            window_start=earliest if earliest != float("inf") else 0.0,
            window_end=latest,
        )

    def record_count(self, service: str, agent_id: str = "default") -> int:
        """Get number of records in window for a service+agent pair."""
        key = self._key(service, agent_id)
        self._prune(key)
        return len(self._records.get(key, []))

    async def persist_to_supabase(
        self, supabase_client: object, service: str, agent_id: str = "default"
    ) -> Optional[dict[str, Any]]:
        """Persist a snapshot to the Supabase proxy_metrics table.

        Args:
            supabase_client: Supabase client instance.
            service: Provider service name.
            agent_id: Agent identifier.

        Returns:
            Inserted row data or None if no records to persist.
        """
        snapshot = self.get_snapshot(service, agent_id)
        if snapshot.count == 0:
            return None

        row = {
            "service": snapshot.service,
            "agent_id": snapshot.agent_id,
            "p50_ms": snapshot.p50_ms,
            "p95_ms": snapshot.p95_ms,
            "p99_ms": snapshot.p99_ms,
            "mean_ms": snapshot.mean_ms,
            "min_ms": snapshot.min_ms,
            "max_ms": snapshot.max_ms,
            "call_count": snapshot.count,
            "error_count": snapshot.error_count,
            "window_start": snapshot.window_start,
            "window_end": snapshot.window_end,
        }

        try:
            result = supabase_client.table("proxy_metrics").insert(row).execute()  # type: ignore[attr-defined,union-attr]
            return result.data  # type: ignore[attr-defined,union-attr]
        except Exception:
            # Don't let metrics persistence failures break the proxy
            return None
