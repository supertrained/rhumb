from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import BackgroundTasks

import routes.proxy as proxy_module
from schemas.agent_identity import AgentIdentityStore, reset_identity_store
from services.agent_access_control import AgentAccessControl, reset_agent_access_control
from services.agent_rate_limit import AgentRateLimitChecker, reset_agent_rate_limit_checker
from services.proxy_auth import AuthInjector
from services.proxy_breaker import BreakerRegistry
from services.proxy_credentials import CredentialStore
from services.proxy_finalizer import (
    ProxyFinalizationJob,
    ProxyFinalizer,
    reset_proxy_finalizer,
)
from services.proxy_latency import LatencyTracker
from services.proxy_rate_limit import RateLimiter
from services.usage_metering import UsageMeterEngine, reset_usage_meter_engine


class _FakePool:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    async def acquire(
        self, service: str, agent_id: str, *, base_url: str = ""
    ):  # type: ignore[no-untyped-def]
        response = self._response

        class _Client:
            async def request(self, **kwargs):  # type: ignore[no-untyped-def]
                return response

        return _Client()

    async def release(self, service: str, agent_id: str) -> None:
        return None


class _NoChangeDetector:
    def detect_changes(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return SimpleNamespace(changes=(), warnings=())

    def alert_required(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return False


class _BlockingFirstPersistMeter(UsageMeterEngine):
    def __init__(self, identity_store: AgentIdentityStore) -> None:
        super().__init__(identity_store=identity_store)
        self.release_first_persist = asyncio.Event()
        self.first_persist_started = asyncio.Event()
        self.first_persist_finished = asyncio.Event()
        self.persist_calls = 0

    async def persist_metered_event(self, event):  # type: ignore[no-untyped-def]
        self.persist_calls += 1
        current = self.persist_calls
        if current == 1:
            self.first_persist_started.set()
            await self.release_first_persist.wait()
        await super().persist_metered_event(event)
        if current == 1:
            self.first_persist_finished.set()


@pytest.fixture(autouse=True)
def _reset_singletons() -> None:
    proxy_module._pool_manager = None
    proxy_module._breaker_registry = None
    proxy_module._latency_tracker = None
    proxy_module._http_client = None
    proxy_module._schema_detector = None
    proxy_module._schema_alert_dispatcher = None
    proxy_module._identity_store = None
    proxy_module._acl_instance = None
    proxy_module._rate_checker_instance = None
    proxy_module._auth_injector_instance = None
    proxy_module._meter_instance = None
    proxy_module._proxy_finalizer = None
    reset_identity_store()
    reset_agent_access_control()
    reset_agent_rate_limit_checker()
    reset_usage_meter_engine()
    reset_proxy_finalizer()
    yield
    proxy_module._pool_manager = None
    proxy_module._breaker_registry = None
    proxy_module._latency_tracker = None
    proxy_module._http_client = None
    proxy_module._schema_detector = None
    proxy_module._schema_alert_dispatcher = None
    proxy_module._identity_store = None
    proxy_module._acl_instance = None
    proxy_module._rate_checker_instance = None
    proxy_module._auth_injector_instance = None
    proxy_module._meter_instance = None
    proxy_module._proxy_finalizer = None
    reset_identity_store()
    reset_agent_access_control()
    reset_agent_rate_limit_checker()
    reset_usage_meter_engine()
    reset_proxy_finalizer()


async def _wired_identity() -> tuple[AgentIdentityStore, str, str]:
    identity_store = AgentIdentityStore(supabase_client=None)
    agent_id, api_key = await identity_store.register_agent(
        name="finalizer-agent",
        organization_id="org-finalizer",
    )
    await identity_store.grant_service_access(agent_id, "stripe")
    return identity_store, agent_id, api_key


def _wire_proxy_module(
    *,
    identity_store: AgentIdentityStore,
    meter: UsageMeterEngine,
    finalizer: ProxyFinalizer,
) -> None:
    credential_store = CredentialStore(auto_load=False)
    credential_store.set_credential("stripe", "api_key", "sk_test_finalizer")

    proxy_module._identity_store = identity_store
    proxy_module._acl_instance = AgentAccessControl(identity_store=identity_store)
    proxy_module._rate_checker_instance = AgentRateLimitChecker(
        identity_store=identity_store,
        rate_limiter=RateLimiter(redis_client=None),
    )
    proxy_module._auth_injector_instance = AuthInjector(credential_store)
    proxy_module._meter_instance = meter
    proxy_module._proxy_finalizer = finalizer
    proxy_module._pool_manager = _FakePool(
        httpx.Response(
            200,
            json={"ok": True, "data": []},
            headers={"content-type": "application/json"},
        )
    )
    proxy_module._breaker_registry = BreakerRegistry()
    proxy_module._latency_tracker = LatencyTracker()
    proxy_module._schema_detector = _NoChangeDetector()


@pytest.mark.asyncio
async def test_proxy_success_path_returns_before_finalizer_finishes() -> None:
    identity_store, agent_id, api_key = await _wired_identity()
    meter = _BlockingFirstPersistMeter(identity_store)
    finalizer = ProxyFinalizer(meter, max_queue_size=10)
    await finalizer.start()
    _wire_proxy_module(identity_store=identity_store, meter=meter, finalizer=finalizer)

    started = time.perf_counter()
    response = await proxy_module.proxy_request(
        proxy_module.ProxyRequest(service="stripe", method="GET", path="/v1/customers"),
        BackgroundTasks(),
        x_rhumb_key=api_key,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert response.status_code == 200
    assert elapsed_ms < 200, f"success path blocked too long: {elapsed_ms:.1f}ms"
    assert meter.first_persist_finished.is_set() is False

    meter.release_first_persist.set()
    await finalizer.stop(drain=True)

    snapshot = await meter.get_usage_snapshot(agent_id, "stripe", 1)
    assert snapshot is not None
    assert snapshot.call_count == 1
    assert snapshot.success_count == 1


@pytest.mark.asyncio
async def test_proxy_finalizer_stop_drains_pending_job() -> None:
    identity_store, agent_id, _api_key = await _wired_identity()
    meter = _BlockingFirstPersistMeter(identity_store)
    finalizer = ProxyFinalizer(meter, max_queue_size=10)
    await finalizer.start()

    job = ProxyFinalizationJob(
        event=meter.build_metered_event(
            agent_id=agent_id,
            service="stripe",
            success=True,
            latency_ms=42.0,
            response_size_bytes=64,
        ),
        service="stripe",
        path="/v1/customers",
        upstream_latency_ms=42.0,
        response_parse_ms=1.0,
        schema_detect_ms=1.0,
        build_event_ms=1.0,
    )

    result = await finalizer.enqueue_or_finalize(job)
    assert result.mode == "queued"

    await meter.first_persist_started.wait()
    assert meter.first_persist_finished.is_set() is False

    meter.release_first_persist.set()
    await finalizer.stop(drain=True)

    snapshot = await meter.get_usage_snapshot(agent_id, "stripe", 1)
    assert snapshot is not None
    assert snapshot.call_count == 1


@pytest.mark.asyncio
async def test_proxy_finalizer_queue_saturation_falls_back_inline() -> None:
    identity_store, agent_id, _api_key = await _wired_identity()
    meter = _BlockingFirstPersistMeter(identity_store)
    finalizer = ProxyFinalizer(meter, max_queue_size=1)
    await finalizer.start()

    job1 = ProxyFinalizationJob(
        event=meter.build_metered_event(agent_id, "stripe", True, 10.0, 10),
        service="stripe",
        path="/one",
        upstream_latency_ms=10.0,
        response_parse_ms=1.0,
        schema_detect_ms=1.0,
        build_event_ms=1.0,
    )
    job2 = ProxyFinalizationJob(
        event=meter.build_metered_event(agent_id, "stripe", True, 11.0, 11),
        service="stripe",
        path="/two",
        upstream_latency_ms=11.0,
        response_parse_ms=1.0,
        schema_detect_ms=1.0,
        build_event_ms=1.0,
    )
    job3 = ProxyFinalizationJob(
        event=meter.build_metered_event(agent_id, "stripe", True, 12.0, 12),
        service="stripe",
        path="/three",
        upstream_latency_ms=12.0,
        response_parse_ms=1.0,
        schema_detect_ms=1.0,
        build_event_ms=1.0,
    )

    first = await finalizer.enqueue_or_finalize(job1)
    assert first.mode == "queued"
    await meter.first_persist_started.wait()

    second = await finalizer.enqueue_or_finalize(job2)
    assert second.mode == "queued"

    third = await finalizer.enqueue_or_finalize(job3)
    assert third.mode == "inline_fallback"

    meter.release_first_persist.set()
    await finalizer.stop(drain=True)

    snapshot = await meter.get_usage_snapshot(agent_id, "stripe", 1)
    assert snapshot is not None
    assert snapshot.call_count == 3
