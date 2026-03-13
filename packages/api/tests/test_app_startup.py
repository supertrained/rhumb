"""Targeted tests for application startup warm-up behavior."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app
from services import operational_fact_emitter as operational_fact_emitter_module
from services import proxy_auth as proxy_auth_module
from services import proxy_credentials as proxy_credentials_module


class _DummyMeter:
    async def ensure_supabase(self) -> bool:
        return False


class _DummyFinalizer:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def start(self) -> None:
        self._events.append("finalizer_start")

    async def stop(self, drain: bool = True) -> None:
        self._events.append("finalizer_stop")


def _patch_startup_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    events: list[str],
) -> None:
    async def fake_get_supabase_client() -> object:
        events.append("supabase")
        return object()

    def fake_get_agent_identity_store(supabase: Any = None) -> object:
        events.append("identity_store")
        return object()

    def fake_get_usage_meter_engine() -> _DummyMeter:
        events.append("meter")
        return _DummyMeter()

    def fake_get_proxy_finalizer(meter: Any) -> _DummyFinalizer:
        events.append("finalizer")
        return _DummyFinalizer(events)

    import db.client as db_client_module
    import schemas.agent_identity as identity_module
    import services.proxy_finalizer as proxy_finalizer_module
    import services.usage_metering as usage_metering_module

    monkeypatch.setattr(db_client_module, "get_supabase_client", fake_get_supabase_client)
    monkeypatch.setattr(identity_module, "get_agent_identity_store", fake_get_agent_identity_store)
    monkeypatch.setattr(
        usage_metering_module,
        "get_usage_meter_engine",
        fake_get_usage_meter_engine,
    )
    monkeypatch.setattr(
        proxy_finalizer_module,
        "get_proxy_finalizer",
        fake_get_proxy_finalizer,
    )


def test_lifespan_warms_auth_injector(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    events: list[str] = []
    emitter_sentinel = object()

    def fake_get_operational_fact_emitter(supabase: object | None = None) -> object:
        events.append("emitter")
        assert supabase is not None
        return emitter_sentinel

    def fake_get_auth_injector(*, emitter: object | None = None) -> object:
        events.append("auth")
        assert emitter is emitter_sentinel
        return object()

    _patch_startup_dependencies(monkeypatch, events=events)
    monkeypatch.setattr(
        operational_fact_emitter_module,
        "get_operational_fact_emitter",
        fake_get_operational_fact_emitter,
    )
    monkeypatch.setattr(proxy_auth_module, "get_auth_injector", fake_get_auth_injector)

    with caplog.at_level(logging.INFO):
        with TestClient(create_app()):
            pass

    assert "emitter" in events
    assert "auth" in events
    assert events.index("emitter") < events.index("auth")
    assert events.index("auth") < events.index("finalizer_start")
    assert "Operational fact emitter: Supabase client initialized" in caplog.text
    assert "Auth injector: credential store warmed" in caplog.text


def test_lifespan_startup_succeeds_when_sop_missing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    events: list[str] = []
    _patch_startup_dependencies(monkeypatch, events=events)

    proxy_auth_module._injector = None
    proxy_credentials_module._credential_store = None
    operational_fact_emitter_module.reset_operational_fact_emitter()
    monkeypatch.setattr(
        proxy_credentials_module.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )

    with caplog.at_level(logging.INFO):
        with TestClient(create_app()):
            pass

    assert proxy_auth_module._injector is not None
    assert proxy_credentials_module._credential_store is not None
    assert "Auth injector: credential store warmed" in caplog.text

    proxy_auth_module._injector = None
    proxy_credentials_module._credential_store = None
    operational_fact_emitter_module.reset_operational_fact_emitter()


def test_credential_store_falls_back_to_env_when_sop_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RHUMB_CREDENTIAL_SLACK_OAUTH_TOKEN", "xoxb-test-token")
    monkeypatch.setattr(
        proxy_credentials_module.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )

    store = proxy_credentials_module.CredentialStore(auto_load=False)
    store._load_service("slack")

    assert store.get_credential("slack", "oauth_token") == "xoxb-test-token"


def test_credential_store_prefers_sop_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RHUMB_CREDENTIAL_SLACK_OAUTH_TOKEN", "xoxb-env-token")

    class _Result:
        returncode = 0
        stdout = "xoxb-sop-token\n"

    monkeypatch.setattr(
        proxy_credentials_module.subprocess,
        "run",
        lambda *args, **kwargs: _Result(),
    )

    store = proxy_credentials_module.CredentialStore(auto_load=False)
    store._load_service("slack")

    assert store.get_credential("slack", "oauth_token") == "xoxb-sop-token"
