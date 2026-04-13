"""Regression coverage for the resolve-and-execute example script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
SCRIPT_PATH = EXAMPLES_DIR / "resolve-and-execute.py"


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


def test_no_auth_walkthrough_shows_alternate_execute_handoff_before_auth_hint(
    monkeypatch, capsys
) -> None:
    module = _load_module("resolve_and_execute_example_alt")
    monkeypatch.setattr(module, "API_KEY", None)

    payload = {
        "data": {
            "providers": [
                {
                    "service_slug": "resend",
                    "an_score": 8.2,
                    "cost_per_call": 0.001,
                    "available_for_execute": False,
                    "endpoint_pattern": "/emails",
                }
            ],
            "execute_hint": None,
            "fallback_chain": [],
            "recovery_hint": {
                "reason": "no_providers_match_credential_mode",
                "alternate_execute_hint": {
                    "preferred_provider": "gmail",
                    "preferred_credential_mode": "agent_vault",
                    "endpoint_pattern": "POST /gmail/v1/users/me/messages/send",
                    "setup_url": "/v1/services/gmail/ceremony",
                },
            },
        }
    }

    def fake_get(url: str, *, headers: dict[str, str] | None = None):
        assert url == f"{module.BASE}/capabilities/search.query/resolve"
        assert headers == {}
        return _FakeResponse(payload)

    monkeypatch.setattr(module.httpx, "get", fake_get)

    module.main()
    out = capsys.readouterr().out

    assert "No execute-ready provider found in the current resolve context." in out
    assert "Next step: pivot to the alternate execute rail via gmail (agent_vault)." in out
    assert "  Endpoint: POST /gmail/v1/users/me/messages/send" in out
    assert "  Setup URL: /v1/services/gmail/ceremony" in out
    assert out.index("Next step: pivot to the alternate execute rail") < out.index(
        "💡 Set RHUMB_API_KEY to continue with estimation and execution."
    )


def test_no_auth_walkthrough_shows_setup_handoff_before_auth_hint(monkeypatch, capsys) -> None:
    module = _load_module("resolve_and_execute_example_setup")
    monkeypatch.setattr(module, "API_KEY", None)

    payload = {
        "data": {
            "providers": [
                {
                    "service_slug": "resend",
                    "an_score": 8.2,
                    "cost_per_call": 0.001,
                    "available_for_execute": False,
                    "endpoint_pattern": "/emails",
                }
            ],
            "execute_hint": None,
            "fallback_chain": [],
            "recovery_hint": {
                "reason": "no_execute_ready_providers",
                "setup_handoff": {
                    "preferred_provider": "resend",
                    "preferred_credential_mode": "byok",
                    "setup_hint": "Set RHUMB_CREDENTIAL_RESEND_API_KEY environment variable or configure via proxy credentials",
                },
            },
        }
    }

    def fake_get(url: str, *, headers: dict[str, str] | None = None):
        assert url == f"{module.BASE}/capabilities/search.query/resolve"
        assert headers == {}
        return _FakeResponse(payload)

    monkeypatch.setattr(module.httpx, "get", fake_get)

    module.main()
    out = capsys.readouterr().out

    assert "No execute-ready provider found in the current resolve context." in out
    assert "Next step: finish setup for resend (byok)." in out
    assert (
        "  Setup hint: Set RHUMB_CREDENTIAL_RESEND_API_KEY environment variable or configure via proxy credentials"
        in out
    )
    assert out.index("Next step: finish setup for resend (byok).") < out.index(
        "💡 Set RHUMB_API_KEY to continue with estimation and execution."
    )
