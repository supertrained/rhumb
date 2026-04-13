"""Regression coverage for the budget-aware routing example script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], *, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload


EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
SCRIPT_PATH = EXAMPLES_DIR / "budget-aware-routing.py"


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


def test_budget_example_surfaces_alternate_execute_endpoint(monkeypatch, capsys) -> None:
    module = _load_module("budget_aware_routing_example_alt")
    monkeypatch.setattr(module, "API_KEY", "test-key")

    def fake_get(url: str, *, headers: dict[str, str] | None = None):
        assert headers == {"X-Rhumb-Key": "test-key", "Content-Type": "application/json"}
        if url == f"{module.BASE}/agent/billing":
            return _FakeResponse({"data": {"balance_usd": 12.34}})
        if url == f"{module.BASE}/capabilities/data.enrich_company/resolve":
            return _FakeResponse(
                {
                    "data": {
                        "providers": [
                            {
                                "service_slug": "apollo",
                                "an_score": 8.4,
                                "cost_per_call": 0.02,
                                "available_for_execute": False,
                                "endpoint_pattern": None,
                            }
                        ],
                        "execute_hint": None,
                        "fallback_chain": [],
                        "recovery_hint": {
                            "reason": "no_providers_match_credential_mode",
                            "resolve_url": "/v1/capabilities/data.enrich_company/resolve?credential_mode=auto",
                            "alternate_execute_hint": {
                                "preferred_provider": "hubspot",
                                "preferred_credential_mode": "agent_vault",
                                "endpoint_pattern": "POST /v1/capabilities/crm.record.search/execute",
                                "setup_url": "/v1/services/hubspot/ceremony",
                            },
                        },
                    }
                }
            )
        if url == f"{module.BASE}/agent/billing/spend":
            return _FakeResponse({"data": {"total_spend_usd": 0.11, "calls_today": 2}})
        raise AssertionError(f"Unexpected GET {url}")

    def fake_post(
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ):
        assert url == f"{module.BASE}/agent/routing"
        assert headers == {"X-Rhumb-Key": "test-key", "Content-Type": "application/json"}
        assert json == {
            "strategy": "cheapest",
            "quality_floor": 6.0,
            "max_cost_per_call_usd": 0.05,
        }
        return _FakeResponse({"ok": True}, status_code=200)

    monkeypatch.setattr(module.httpx, "get", fake_get)
    monkeypatch.setattr(module.httpx, "post", fake_post)

    module.main()
    out = capsys.readouterr().out

    assert "🧭 Alternate execute rail: hubspot (agent_vault)" in out
    assert "  Endpoint: POST /v1/capabilities/crm.record.search/execute" in out
    assert "  Setup URL: /v1/services/hubspot/ceremony" in out
    assert "  Resolve URL: /v1/capabilities/data.enrich_company/resolve?credential_mode=auto" in out


def test_budget_example_surfaces_setup_handoff_hint(monkeypatch, capsys) -> None:
    module = _load_module("budget_aware_routing_example_setup")
    monkeypatch.setattr(module, "API_KEY", "test-key")

    def fake_get(url: str, *, headers: dict[str, str] | None = None):
        assert headers == {"X-Rhumb-Key": "test-key", "Content-Type": "application/json"}
        if url == f"{module.BASE}/agent/billing":
            return _FakeResponse({"data": {"balance_usd": 12.34}})
        if url == f"{module.BASE}/capabilities/data.enrich_company/resolve":
            return _FakeResponse(
                {
                    "data": {
                        "providers": [
                            {
                                "service_slug": "apollo",
                                "an_score": 8.4,
                                "cost_per_call": 0.02,
                                "available_for_execute": False,
                                "endpoint_pattern": None,
                            }
                        ],
                        "execute_hint": None,
                        "fallback_chain": [],
                        "recovery_hint": {
                            "reason": "no_execute_ready_providers",
                            "resolve_url": "/v1/capabilities/data.enrich_company/resolve?credential_mode=byok",
                            "setup_handoff": {
                                "preferred_provider": "apollo",
                                "preferred_credential_mode": "byok",
                                "setup_hint": "Set RHUMB_CREDENTIAL_APOLLO_API_KEY or configure via proxy credentials",
                            },
                        },
                    }
                }
            )
        if url == f"{module.BASE}/agent/billing/spend":
            return _FakeResponse({"data": {"total_spend_usd": 0.11, "calls_today": 2}})
        raise AssertionError(f"Unexpected GET {url}")

    def fake_post(
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ):
        assert url == f"{module.BASE}/agent/routing"
        assert headers == {"X-Rhumb-Key": "test-key", "Content-Type": "application/json"}
        assert json == {
            "strategy": "cheapest",
            "quality_floor": 6.0,
            "max_cost_per_call_usd": 0.05,
        }
        return _FakeResponse({"ok": True}, status_code=200)

    monkeypatch.setattr(module.httpx, "get", fake_get)
    monkeypatch.setattr(module.httpx, "post", fake_post)

    module.main()
    out = capsys.readouterr().out

    assert "🧭 Setup next: apollo (byok)" in out
    assert "  Setup hint: Set RHUMB_CREDENTIAL_APOLLO_API_KEY or configure via proxy credentials" in out
    assert "  Resolve URL: /v1/capabilities/data.enrich_company/resolve?credential_mode=byok" in out
