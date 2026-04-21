from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "onboarding_self_serve_smoke.py"

spec = importlib.util.spec_from_file_location("onboarding_self_serve_smoke", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
onboarding_self_serve_smoke = importlib.util.module_from_spec(spec)
# dataclasses needs the module to be registered in sys.modules during decoration.
sys.modules[spec.name] = onboarding_self_serve_smoke
spec.loader.exec_module(onboarding_self_serve_smoke)


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


def test_build_search_query_body_is_minimal() -> None:
    body = onboarding_self_serve_smoke._build_search_query_body("hello")
    assert body == {"q": "hello"}
