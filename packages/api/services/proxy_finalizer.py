"""Queue-backed proxy finalization worker.

Moves durable bookkeeping (metering + identity last-used touch) off the
successful proxy request hot path while preserving graceful-shutdown drain and
inline fallback when the queue is unavailable or saturated.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import Optional

from services.operational_fact_emitter import get_operational_fact_emitter
from services.usage_metering import MeterWriteTimings, MeteredUsageEvent, UsageMeterEngine

logger = logging.getLogger(__name__)


@dataclass
class ProxyFinalizationJob:
    """One proxy bookkeeping job for the background finalizer."""

    event: MeteredUsageEvent
    service: str
    path: str
    upstream_latency_ms: float
    response_parse_ms: float
    schema_detect_ms: float
    build_event_ms: float


@dataclass
class ProxyFinalizationResult:
    """Result of queueing or inline finalization."""

    mode: str
    queue_depth: int
    persist_ms: float = 0.0
    identity_touch_ms: float = 0.0
    total_worker_ms: float = 0.0


class ProxyFinalizer:
    """Background worker for proxy finalization jobs."""

    def __init__(
        self,
        meter_engine: UsageMeterEngine,
        *,
        max_queue_size: int = 1000,
    ) -> None:
        self._meter = meter_engine
        self._queue: asyncio.Queue[ProxyFinalizationJob | None] = asyncio.Queue(
            maxsize=max_queue_size
        )
        self._worker_task: Optional[asyncio.Task[None]] = None
        self._accepting = False

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def is_running(self) -> bool:
        return self._worker_task is not None and not self._worker_task.done()

    async def start(self) -> None:
        """Start the background worker if needed."""
        if self.is_running:
            return
        self._accepting = True
        loop = asyncio.get_running_loop()
        self._worker_task = loop.create_task(self._worker_loop())

    async def stop(self, *, drain: bool = True) -> None:
        """Stop the worker, optionally draining queued jobs first."""
        self._accepting = False

        if self._worker_task is None:
            return

        if drain:
            await self._queue.join()
            self._queue.put_nowait(None)
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
        else:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task

        self._worker_task = None

    async def enqueue_or_finalize(
        self,
        job: ProxyFinalizationJob,
    ) -> ProxyFinalizationResult:
        """Queue a job or fall back to inline finalization.

        Returns quickly when the worker is running and the queue has capacity.
        Falls back to inline durable finalization when the worker is unavailable
        or the queue is saturated.
        """
        if not self.is_running or not self._accepting:
            timings = await self._finalize_inline(job, reason="worker_unavailable")
            return ProxyFinalizationResult(
                mode="inline_fallback",
                queue_depth=self.queue_depth,
                persist_ms=timings.persist_ms,
                identity_touch_ms=timings.identity_touch_ms,
                total_worker_ms=timings.total_ms,
            )

        try:
            self._queue.put_nowait(job)
            return ProxyFinalizationResult(mode="queued", queue_depth=self.queue_depth)
        except asyncio.QueueFull:
            timings = await self._finalize_inline(job, reason="queue_saturated")
            return ProxyFinalizationResult(
                mode="inline_fallback",
                queue_depth=self.queue_depth,
                persist_ms=timings.persist_ms,
                identity_touch_ms=timings.identity_touch_ms,
                total_worker_ms=timings.total_ms,
            )

    async def _worker_loop(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                if job is None:
                    return

                timings = await self._meter.finalize_prepared_event(job.event)
                get_operational_fact_emitter().schedule_latency_snapshot(
                    event=job.event,
                    path=job.path,
                    upstream_latency_ms=job.upstream_latency_ms,
                    response_parse_ms=job.response_parse_ms,
                    schema_detect_ms=job.schema_detect_ms,
                    build_event_ms=job.build_event_ms,
                    persist_ms=timings.persist_ms,
                    identity_touch_ms=timings.identity_touch_ms,
                    total_worker_ms=timings.total_ms,
                    queue_depth=self.queue_depth,
                    finalizer_mode="queued",
                )
                logger.info(
                    "proxy_finalizer worker service=%s path=%s persist_ms=%.1f identity_touch_ms=%.1f total_worker_ms=%.1f queue_depth=%d",
                    job.service,
                    job.path,
                    timings.persist_ms,
                    timings.identity_touch_ms,
                    timings.total_ms,
                    self.queue_depth,
                )
            except Exception:
                logger.warning("proxy_finalizer worker job failed", exc_info=True)
            finally:
                self._queue.task_done()

    async def _finalize_inline(
        self,
        job: ProxyFinalizationJob,
        *,
        reason: str,
    ) -> MeterWriteTimings:
        timings = await self._meter.finalize_prepared_event(job.event)
        get_operational_fact_emitter().schedule_latency_snapshot(
            event=job.event,
            path=job.path,
            upstream_latency_ms=job.upstream_latency_ms,
            response_parse_ms=job.response_parse_ms,
            schema_detect_ms=job.schema_detect_ms,
            build_event_ms=job.build_event_ms,
            persist_ms=timings.persist_ms,
            identity_touch_ms=timings.identity_touch_ms,
            total_worker_ms=timings.total_ms,
            queue_depth=self.queue_depth,
            finalizer_mode="inline_fallback",
        )
        logger.warning(
            "proxy_finalizer inline_fallback reason=%s service=%s path=%s persist_ms=%.1f identity_touch_ms=%.1f total_worker_ms=%.1f queue_depth=%d",
            reason,
            job.service,
            job.path,
            timings.persist_ms,
            timings.identity_touch_ms,
            timings.total_ms,
            self.queue_depth,
        )
        return timings


_proxy_finalizer: Optional[ProxyFinalizer] = None


def get_proxy_finalizer(
    meter_engine: Optional[UsageMeterEngine] = None,
) -> ProxyFinalizer:
    """Get or create the global proxy finalizer singleton."""
    global _proxy_finalizer
    if _proxy_finalizer is None:
        if meter_engine is None:
            from services.usage_metering import get_usage_meter_engine

            meter_engine = get_usage_meter_engine()
        _proxy_finalizer = ProxyFinalizer(meter_engine)
    return _proxy_finalizer


def reset_proxy_finalizer() -> None:
    """Reset singleton for tests."""
    global _proxy_finalizer
    _proxy_finalizer = None
