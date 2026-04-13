"""Regression coverage for the dogfood telemetry loop example script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self._responses = responses

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> _FakeResponse:
        assert headers == {
            "X-Rhumb-Key": "test-key",
            "Content-Type": "application/json",
            "User-Agent": "rhumb-dogfood-loop/0.1",
        }
        if url.endswith("/telemetry/usage"):
            assert params == {"days": 1, "capability_id": "search.query"}
        elif url.endswith("/capabilities/search.query/resolve"):
            assert params is None
        else:
            raise AssertionError(f"Unexpected GET {url}")
        return _FakeResponse(self._responses[url])


EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
SCRIPT_PATH = EXAMPLES_DIR / "dogfood-telemetry-loop.py"


def _load_module(name: str) -> ModuleType:
    sys.path.insert(0, str(EXAMPLES_DIR))
    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
        if spec is None or spec.loader is None:
            raise AssertionError(f"Could not load module from {SCRIPT_PATH}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def test_dogfood_loop_surfaces_alternate_execute_resolve_url(monkeypatch, capsys) -> None:
    module = _load_module("dogfood_telemetry_loop_example_alt")
    monkeypatch.setattr(module, "API_KEY", "test-key")
    monkeypatch.setattr(
        module.httpx,
        "Client",
        lambda timeout=30.0: _FakeClient(
            {
                f"{module.BASE}/telemetry/usage": {"data": {"summary": {"total_calls": 7}}},
                f"{module.BASE}/capabilities/search.query/resolve": {
                    "data": {
                        "providers": [
                            {
                                "service_slug": "resend",
                                "available_for_execute": False,
                                "endpoint_pattern": None,
                            }
                        ],
                        "execute_hint": None,
                        "fallback_chain": [],
                        "recovery_hint": {
                            "reason": "no_providers_match_credential_mode",
                            "resolve_url": "/v1/capabilities/search.query/resolve?credential_mode=auto",
                            "alternate_execute_hint": {
                                "preferred_provider": "gmail",
                                "preferred_credential_mode": "agent_vault",
                                "endpoint_pattern": "POST /v1/capabilities/search.query/execute",
                                "setup_url": "/v1/services/gmail/ceremony",
                            },
                        },
                    }
                },
            }
        ),
    )

    with pytest.raises(SystemExit) as excinfo:
        module.main()

    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "No execute-ready providers resolved for search.query." in out
    assert "Alternate execute rail: gmail (agent_vault)" in out
    assert "  Endpoint: POST /v1/capabilities/search.query/execute" in out
    assert "  Setup URL: /v1/services/gmail/ceremony" in out
    assert "  Resolve URL: /v1/capabilities/search.query/resolve?credential_mode=auto" in out
    assert out.index("  Resolve URL: /v1/capabilities/search.query/resolve?credential_mode=auto") < out.index(
        "Recovery hint:"
    )


def test_dogfood_loop_surfaces_setup_resolve_url(monkeypatch, capsys) -> None:
    module = _load_module("dogfood_telemetry_loop_example_setup")
    monkeypatch.setattr(module, "API_KEY", "test-key")
    monkeypatch.setattr(
        module.httpx,
        "Client",
        lambda timeout=30.0: _FakeClient(
            {
                f"{module.BASE}/telemetry/usage": {"data": {"summary": {"total_calls": 7}}},
                f"{module.BASE}/capabilities/search.query/resolve": {
                    "data": {
                        "providers": [
                            {
                                "service_slug": "resend",
                                "available_for_execute": False,
                                "endpoint_pattern": None,
                            }
                        ],
                        "execute_hint": None,
                        "fallback_chain": [],
                        "recovery_hint": {
                            "reason": "no_execute_ready_providers",
                            "resolve_url": "/v1/capabilities/search.query/resolve?credential_mode=byok",
                            "setup_handoff": {
                                "preferred_provider": "resend",
                                "preferred_credential_mode": "byok",
                                "setup_hint": "Set RHUMB_CREDENTIAL_RESEND_API_KEY environment variable or configure via proxy credentials",
                            },
                        },
                    }
                },
            }
        ),
    )

    with pytest.raises(SystemExit) as excinfo:
        module.main()

    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "No execute-ready providers resolved for search.query." in out
    assert "Setup next: resend (byok)" in out
    assert (
        "  Setup hint: Set RHUMB_CREDENTIAL_RESEND_API_KEY environment variable or configure via proxy credentials"
        in out
    )
    assert "  Resolve URL: /v1/capabilities/search.query/resolve?credential_mode=byok" in out
    assert out.index("  Resolve URL: /v1/capabilities/search.query/resolve?credential_mode=byok") < out.index(
        "Recovery hint:"
    )
