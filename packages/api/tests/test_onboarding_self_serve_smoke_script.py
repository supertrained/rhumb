from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "onboarding_self_serve_smoke.py"

spec = importlib.util.spec_from_file_location("onboarding_self_serve_smoke", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
onboarding_self_serve_smoke = importlib.util.module_from_spec(spec)
# dataclasses needs the module to be registered in sys.modules during decoration.
sys.modules[spec.name] = onboarding_self_serve_smoke
spec.loader.exec_module(onboarding_self_serve_smoke)


class FakeResponse:
    def __init__(self, status_code: int, payload: Any = None, *, text: str | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or ("" if payload is None else str(payload))
        self.headers = {"content-type": "application/json"}

    def json(self) -> Any:
        return self._payload


class FakeClient:
    def __init__(self, factory: "FakeClientFactory", *, cookies: dict[str, str] | None = None) -> None:
        self.factory = factory
        self.cookies = cookies or {}

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def _record(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.factory.calls.append(
            {
                "method": method,
                "url": url,
                "json": kwargs.get("json"),
                "params": kwargs.get("params"),
                "headers": kwargs.get("headers"),
                "cookies": dict(self.cookies),
            }
        )
        assert self.factory.responses, f"No fake response queued for {method} {url}"
        return self.factory.responses.pop(0)

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._record("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._record("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._record("PUT", url, **kwargs)


class FakeClientFactory:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> FakeClient:
        return FakeClient(self, cookies=kwargs.get("cookies"))


def test_extract_session_token() -> None:
    assert onboarding_self_serve_smoke._extract_session_token({"data": {"session_token": "tok"}}) == "tok"
    assert onboarding_self_serve_smoke._extract_session_token({"data": {}}) is None
    assert onboarding_self_serve_smoke._extract_session_token({}) is None


def test_pick_preferred_provider_prefers_execute_hint() -> None:
    payload = {
        "data": {
            "providers": [{"service_slug": "brave-search-api"}],
            "execute_hint": {"preferred_provider": "people-data-labs"},
        }
    }
    assert onboarding_self_serve_smoke._pick_preferred_provider(payload) == "people-data-labs"


def test_pick_preferred_provider_falls_back_to_first_provider() -> None:
    payload = {"data": {"providers": [{"service_slug": "brave-search-api"}]}}
    assert onboarding_self_serve_smoke._pick_preferred_provider(payload) == "brave-search-api"


def test_build_search_query_body_defaults_to_q() -> None:
    body = onboarding_self_serve_smoke._build_search_query_body("hello", provider="unknown")
    assert body == {"q": "hello"}


def test_build_search_query_body_uses_query_for_tavily_and_exa() -> None:
    assert onboarding_self_serve_smoke._build_search_query_body("hello", provider="tavily") == {"query": "hello"}
    assert onboarding_self_serve_smoke._build_search_query_body("hello", provider="exa") == {"query": "hello"}


def test_build_search_query_body_uses_q_for_brave() -> None:
    assert onboarding_self_serve_smoke._build_search_query_body("hello", provider="brave-search") == {"q": "hello"}
    assert onboarding_self_serve_smoke._build_search_query_body("hello", provider="brave-search-api") == {"q": "hello"}


def test_main_runs_checkout_even_when_saved_card_exists_but_balance_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = FakeClientFactory(
        [
            FakeResponse(200, {"data": {"status": "ok"}}),
            FakeResponse(200, {"data": {"session_token": "sess_test"}}),
            FakeResponse(200, {"balance_usd": 0.0, "has_payment_method": True}),
            FakeResponse(200, {"checkout_url": "https://checkout.stripe.com/pay/cs_test"}),
            FakeResponse(200, {"balance_usd": 25.0, "has_payment_method": True}),
            FakeResponse(200, {"auto_reload_enabled": True}),
            FakeResponse(
                200,
                {
                    "agent_id": "agent_123",
                    "api_key": "rhumb_secret_key",
                    "api_key_prefix": "rhumb_abcd",
                },
            ),
            FakeResponse(200, {"data": {"execute_hint": {"preferred_provider": "exa"}}}),
            FakeResponse(200, {"ok": True}),
        ]
    )
    input_values = iter([""])

    monkeypatch.setattr(onboarding_self_serve_smoke.httpx, "Client", factory)
    monkeypatch.setattr(onboarding_self_serve_smoke.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(input_values))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "onboarding_self_serve_smoke.py",
            "--email",
            "journey@example.com",
            "--otp",
            "123456",
            "--json",
        ],
    )

    assert onboarding_self_serve_smoke.main() == 0

    checkout_calls = [
        call for call in factory.calls if call["url"].endswith("/v1/auth/me/billing/checkout")
    ]
    assert len(checkout_calls) == 1

    execute_call = next(
        call for call in factory.calls if call["url"].endswith("/v1/capabilities/search.query/execute")
    )
    assert execute_call["json"]["provider"] == "exa"
    assert execute_call["json"]["body"] == {"query": "Rhumb onboarding smoke test"}


def test_main_refuses_to_continue_when_checkout_does_not_fund_balance(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = FakeClientFactory(
        [
            FakeResponse(200, {"data": {"status": "ok"}}),
            FakeResponse(200, {"data": {"session_token": "sess_test"}}),
            FakeResponse(200, {"balance_usd": 0.0, "has_payment_method": True}),
            FakeResponse(200, {"checkout_url": "https://checkout.stripe.com/pay/cs_test"}),
            FakeResponse(200, {"balance_usd": 0.0, "has_payment_method": True}),
        ]
    )
    input_values = iter([""])
    times = iter([0.0, 0.0, 2.0])

    monkeypatch.setattr(onboarding_self_serve_smoke.httpx, "Client", factory)
    monkeypatch.setattr(onboarding_self_serve_smoke.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(onboarding_self_serve_smoke.time, "time", lambda: next(times))
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(input_values))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "onboarding_self_serve_smoke.py",
            "--email",
            "journey@example.com",
            "--otp",
            "123456",
            "--poll-seconds",
            "1",
            "--poll-interval",
            "0",
        ],
    )

    with pytest.raises(SystemExit, match="billing is still unfunded"):
        onboarding_self_serve_smoke.main()

    assert not any(call["url"].endswith("/v1/auth/me/billing/auto-reload") for call in factory.calls)
