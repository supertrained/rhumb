"""Tests for proxy latency tracking and aggregation."""

import time

import pytest

from services.proxy_latency import LatencyTracker


@pytest.fixture
def tracker() -> LatencyTracker:
    """Create a fresh latency tracker."""
    return LatencyTracker()


@pytest.fixture
def short_window_tracker() -> LatencyTracker:
    """Create a tracker with very short window for testing pruning."""
    return LatencyTracker(window_seconds=0.5)


def _record_n(
    tracker: LatencyTracker,
    n: int,
    service: str = "stripe",
    agent_id: str = "default",
    latency_ms: float = 5.0,
) -> None:
    """Helper to record n latency measurements."""
    for _ in range(n):
        now = time.perf_counter()
        tracker.record(
            service=service,
            agent_id=agent_id,
            latency_ms=latency_ms,
            perf_start=now,
            perf_end=now + latency_ms / 1000,
        )


class TestLatencyRecording:
    """Test basic latency recording."""

    def test_record_creates_entry(self, tracker: LatencyTracker) -> None:
        """Recording creates a latency record."""
        now = time.perf_counter()
        record = tracker.record(
            service="stripe",
            agent_id="default",
            latency_ms=5.0,
            perf_start=now,
            perf_end=now + 0.005,
        )
        assert record.service == "stripe"
        assert record.latency_ms == 5.0
        assert tracker.record_count("stripe") == 1

    def test_record_multiple(self, tracker: LatencyTracker) -> None:
        """Multiple records are stored correctly."""
        _record_n(tracker, 10)
        assert tracker.record_count("stripe") == 10

    def test_record_separate_services(self, tracker: LatencyTracker) -> None:
        """Records are separated by service."""
        _record_n(tracker, 5, service="stripe")
        _record_n(tracker, 3, service="slack")
        assert tracker.record_count("stripe") == 5
        assert tracker.record_count("slack") == 3

    def test_record_separate_agents(self, tracker: LatencyTracker) -> None:
        """Records are separated by agent_id."""
        _record_n(tracker, 5, agent_id="agent-1")
        _record_n(tracker, 3, agent_id="agent-2")
        assert tracker.record_count("stripe", "agent-1") == 5
        assert tracker.record_count("stripe", "agent-2") == 3

    def test_record_with_error(self, tracker: LatencyTracker) -> None:
        """Error records are tracked."""
        now = time.perf_counter()
        tracker.record(
            service="stripe",
            agent_id="default",
            latency_ms=50.0,
            perf_start=now,
            perf_end=now + 0.05,
            status_code=500,
            success=False,
        )
        snapshot = tracker.get_snapshot("stripe")
        assert snapshot.error_count == 1


class TestLatencyPercentiles:
    """Test percentile computation."""

    def test_snapshot_empty(self, tracker: LatencyTracker) -> None:
        """Empty snapshot returns zeros."""
        snapshot = tracker.get_snapshot("stripe")
        assert snapshot.count == 0
        assert snapshot.p50_ms == 0.0

    def test_snapshot_single_record(self, tracker: LatencyTracker) -> None:
        """Single record snapshot has same value for all percentiles."""
        _record_n(tracker, 1, latency_ms=10.0)
        snapshot = tracker.get_snapshot("stripe")
        assert snapshot.count == 1
        assert snapshot.p50_ms == 10.0
        assert snapshot.p95_ms == 10.0
        assert snapshot.p99_ms == 10.0

    def test_snapshot_percentiles_correct(
        self, tracker: LatencyTracker
    ) -> None:
        """Percentiles are computed correctly for a known distribution."""
        # Record latencies 1..100
        for i in range(1, 101):
            now = time.perf_counter()
            tracker.record(
                service="stripe",
                agent_id="default",
                latency_ms=float(i),
                perf_start=now,
                perf_end=now + i / 1000,
            )

        snapshot = tracker.get_snapshot("stripe")
        assert snapshot.count == 100
        assert snapshot.p50_ms == pytest.approx(50.5, abs=1.0)
        assert snapshot.p95_ms == pytest.approx(95.05, abs=1.0)
        assert snapshot.p99_ms == pytest.approx(99.01, abs=1.0)
        assert snapshot.mean_ms == pytest.approx(50.5, abs=0.5)
        assert snapshot.min_ms == 1.0
        assert snapshot.max_ms == 100.0

    def test_snapshot_to_dict(self, tracker: LatencyTracker) -> None:
        """Snapshot to_dict has all expected fields."""
        _record_n(tracker, 5, latency_ms=10.0)
        snapshot = tracker.get_snapshot("stripe")
        d = snapshot.to_dict()
        assert "p50_ms" in d
        assert "p95_ms" in d
        assert "p99_ms" in d
        assert "mean_ms" in d
        assert "count" in d
        assert d["service"] == "stripe"


class TestLatencyGlobalSnapshot:
    """Test global aggregation across services."""

    def test_global_snapshot_empty(self, tracker: LatencyTracker) -> None:
        """Empty global snapshot returns zeros."""
        snapshot = tracker.get_global_snapshot()
        assert snapshot.count == 0

    def test_global_snapshot_aggregates(
        self, tracker: LatencyTracker
    ) -> None:
        """Global snapshot aggregates across services."""
        _record_n(tracker, 5, service="stripe", latency_ms=10.0)
        _record_n(tracker, 5, service="slack", latency_ms=20.0)

        snapshot = tracker.get_global_snapshot()
        assert snapshot.count == 10
        assert snapshot.service == "global"
        assert snapshot.mean_ms == pytest.approx(15.0, abs=0.5)


class TestLatencyAllSnapshots:
    """Test get_all_snapshots."""

    def test_all_snapshots(self, tracker: LatencyTracker) -> None:
        """get_all_snapshots returns per-service snapshots."""
        _record_n(tracker, 3, service="stripe")
        _record_n(tracker, 3, service="slack")

        snapshots = tracker.get_all_snapshots()
        assert len(snapshots) == 2
        assert "stripe:default" in snapshots
        assert "slack:default" in snapshots


class TestLatencyWindowPruning:
    """Test rolling window pruning."""

    def test_records_pruned_outside_window(
        self, short_window_tracker: LatencyTracker
    ) -> None:
        """Records outside the window are pruned."""
        _record_n(short_window_tracker, 5)

        # Records should be present now
        assert short_window_tracker.record_count("stripe") == 5

        # After window expires, records should be pruned
        import time as _time

        _time.sleep(0.6)  # Window is 0.5s
        assert short_window_tracker.record_count("stripe") == 0
