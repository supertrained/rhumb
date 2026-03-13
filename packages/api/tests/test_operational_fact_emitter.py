from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Generator

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import routes.proxy as proxy_module
from schemas.agent_identity import AgentIdentityStore
from services.operational_fact_emitter import (
    get_operational_fact_emitter,
    reset_operational_fact_emitter,
)
from services.proxy_auth import AuthInjectionRequest, AuthInjector, AuthMethod
from services.proxy_breaker import BreakerRegistry, BreakerState, CircuitBreaker
from services.proxy_credentials import CredentialStore
from services.proxy_finalizer import ProxyFinalizationJob, ProxyFinalizer
from services.proxy_latency import LatencyTracker
from services.usage_metering import UsageMeterEngine


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeSupabaseQuery:
    def __init__(self, client: "_FakeSupabaseClient", table_name: str) -> None:
        self._client = client
        self._table_name = table_name
        self._insert_payload: Any = None

    def insert(self, payload: Any) -> "_FakeSupabaseQuery":
        self._insert_payload = payload
        return self

    async def execute(self) -> _FakeResponse:
        return self._client.execute(self)


class _FakeSupabaseClient:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            "access_operational_facts": [],
        }

    def table(self, table_name: str) -> _FakeSupabaseQuery:
        return _FakeSupabaseQuery(self, table_name)

    def rows(self, table_name: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(table_name, [])

    def execute(self, query: _FakeSupabaseQuery) -> _FakeResponse:
        payload = query._insert_payload
        if payload is None:
            return _FakeResponse(None)

        row = dict(payload)
        self.rows(query._table_name).append(row)
        return _FakeResponse(row)


class _FailingSupabaseClient(_FakeSupabaseClient):
    def execute(self, query: _FakeSupabaseQuery) -> _FakeResponse:
        raise RuntimeError("supabase insert failed")


class _PoolWithNoMetrics:
    def get_all_metrics(self) -> dict[str, Any]:
        return {}


@pytest.fixture(autouse=True)
def _reset_state() -> Generator[None, None, None]:
    proxy_module._latency_tracker = None
    proxy_module._breaker_registry = None
    proxy_module._pool_manager = None
    reset_operational_fact_emitter()
    yield
    proxy_module._latency_tracker = None
    proxy_module._breaker_registry = None
    proxy_module._pool_manager = None
    reset_operational_fact_emitter()


@pytest.mark.asyncio
async def test_proxy_finalizer_emits_latency_snapshot_row() -> None:
    client = _FakeSupabaseClient()
    emitter = get_operational_fact_emitter(client)
    meter = UsageMeterEngine(identity_store=AgentIdentityStore(supabase_client=None))
    finalizer = ProxyFinalizer(meter, max_queue_size=4)
    await finalizer.start()

    job = ProxyFinalizationJob(
        event=meter.build_metered_event(
            agent_id="agent-latency",
            service="stripe",
            success=True,
            latency_ms=42.5,
            response_size_bytes=128,
        ),
        service="stripe",
        path="/v1/customers",
        upstream_latency_ms=42.5,
        response_parse_ms=1.2,
        schema_detect_ms=2.3,
        build_event_ms=0.4,
    )

    result = await finalizer.enqueue_or_finalize(job)
    assert result.mode == "queued"
    await finalizer.stop(drain=True)
    await asyncio.sleep(0)

    rows = client.rows("access_operational_facts")
    assert len(rows) == 1
    row = rows[0]
    assert row["schema_version"] == "access_operational_fact_v1"
    assert row["fact_type"] == "latency_snapshot"
    assert row["event_type"] == "proxy_call_completed"
    assert row["service_slug"] == "stripe"
    assert row["provider_slug"] == "stripe"
    assert row["agent_id"] == "agent-latency"
    assert row["ingress_channel"] == "access_proxy"
    assert row["countability_hint"] == "countable_as_evidence_now"
    assert row["payload"]["path"] == "/v1/customers"
    assert row["payload"]["result"] == "success"
    assert row["payload"]["upstream_latency_ms"] == 42.5
    assert row["payload"]["finalizer_mode"] == "queued"

    stats = emitter.get_stats()
    assert stats["emitted"] == 1
    assert stats["by_fact_type"] == {"latency_snapshot": 1}


@pytest.mark.asyncio
async def test_circuit_state_emits_only_on_real_transitions() -> None:
    client = _FakeSupabaseClient()
    emitter = get_operational_fact_emitter(client)

    def on_transition(
        breaker: CircuitBreaker,
        _previous_state: BreakerState,
        new_state: BreakerState,
    ) -> None:
        event_type = {
            "open": "circuit_opened",
            "half_open": "circuit_half_opened",
            "closed": "circuit_closed",
        }[new_state.value]
        emitter.schedule_circuit_state(
            service=breaker.service,
            agent_id=breaker.agent_id,
            event_type=event_type,
            new_state=new_state.value,
            failure_threshold=breaker.failure_threshold,
            timeout_threshold_ms=breaker.timeout_threshold_ms,
            cooldown_seconds=breaker.cooldown_seconds,
            metrics={
                "consecutive_failures": breaker.metrics.consecutive_failures,
                "total_failures": breaker.metrics.total_failures,
                "total_successes": breaker.metrics.total_successes,
                "times_opened": breaker.metrics.times_opened,
            },
        )

    registry = BreakerRegistry(failure_threshold=2, on_transition=on_transition)
    breaker = registry.get("stripe", "agent-breaker")

    breaker.record_failure(status_code=500)
    await asyncio.sleep(0)
    assert client.rows("access_operational_facts") == []

    breaker.record_failure(status_code=500)
    await asyncio.sleep(0)
    assert len(client.rows("access_operational_facts")) == 1

    breaker.record_failure(status_code=500)
    await asyncio.sleep(0)
    row = client.rows("access_operational_facts")[0]
    assert len(client.rows("access_operational_facts")) == 1
    assert row["fact_type"] == "circuit_state"
    assert row["event_type"] == "circuit_opened"
    assert row["payload"]["new_state"] == "open"
    assert row["payload"]["failure_threshold"] == 2
    assert row["payload"]["times_opened"] == 1


@pytest.mark.asyncio
async def test_auth_injector_emits_sanitized_credential_lifecycle_rows() -> None:
    client = _FakeSupabaseClient()
    emitter = get_operational_fact_emitter(client)
    store = CredentialStore(auto_load=False)
    store.set_credential("stripe", "api_key", "sk_live_secret_value")
    injector = AuthInjector(store, emitter=emitter)

    headers = injector.inject(
        AuthInjectionRequest(
            service="stripe",
            agent_id="agent-auth",
            auth_method=AuthMethod.API_KEY,
        )
    )
    assert headers["Authorization"] == "Bearer sk_live_secret_value"

    with pytest.raises(RuntimeError):
        injector.inject(
            AuthInjectionRequest(
                service="github",
                agent_id="agent-auth",
                auth_method=AuthMethod.API_TOKEN,
            )
        )

    await asyncio.sleep(0)

    rows = client.rows("access_operational_facts")
    assert len(rows) == 2
    assert rows[0]["event_type"] == "credential_injected"
    assert rows[0]["payload"]["auth_method"] == "api_key"
    assert rows[0]["payload"]["header_name"] == "Authorization"
    assert rows[1]["event_type"] == "credential_missing"
    assert rows[1]["payload"]["error_type"] == "RuntimeError"
    assert rows[1]["payload"]["error_message"] == "credential not found"

    serialized_rows = json.dumps(rows)
    assert "sk_live_secret_value" not in serialized_rows
    assert "Bearer sk_live_secret_value" not in serialized_rows


@pytest.mark.asyncio
async def test_emitter_failures_do_not_raise_into_auth_path() -> None:
    emitter = get_operational_fact_emitter(_FailingSupabaseClient())
    store = CredentialStore(auto_load=False)
    store.set_credential("stripe", "api_key", "sk_test_safe")
    injector = AuthInjector(store, emitter=emitter)

    headers = injector.inject(
        AuthInjectionRequest(
            service="stripe",
            agent_id="agent-auth",
            auth_method=AuthMethod.API_KEY,
        )
    )
    await asyncio.sleep(0)

    assert headers["Authorization"] == "Bearer sk_test_safe"
    assert emitter.get_stats()["failed"] == 1


@pytest.mark.asyncio
async def test_emitter_noops_without_supabase_and_tracks_unavailable() -> None:
    emitter = get_operational_fact_emitter()

    await emitter.emit_credential_lifecycle(
        service="stripe",
        agent_id="agent-auth",
        event_type="credential_lookup_failed",
        auth_method="api_key",
        outcome="error",
        error_type="RuntimeError",
        error_message="credential lookup failed",
    )

    assert emitter.get_stats()["emitted"] == 0
    assert emitter.get_stats()["dropped"] == 1
    assert emitter.get_stats()["unavailable"] == 1


@pytest.mark.asyncio
async def test_proxy_stats_includes_operational_fact_stats() -> None:
    client = _FakeSupabaseClient()
    emitter = get_operational_fact_emitter(client)
    await emitter.emit_credential_lifecycle(
        service="stripe",
        agent_id="agent-auth",
        event_type="credential_injected",
        auth_method="api_key",
        outcome="success",
        header_name="Authorization",
    )

    proxy_module._latency_tracker = LatencyTracker()
    proxy_module._breaker_registry = BreakerRegistry()
    proxy_module._pool_manager = _PoolWithNoMetrics()

    stats = await proxy_module.proxy_stats()

    assert stats["data"]["operational_facts"]["emitted"] == 1
    assert stats["data"]["operational_facts"]["by_fact_type"] == {
        "credential_lifecycle": 1
    }
