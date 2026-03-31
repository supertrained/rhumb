"""Tests for the Resolve v2 dogfood operator harness."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "resolve_v2_dogfood.py"

spec = importlib.util.spec_from_file_location("resolve_v2_dogfood", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
resolve_v2_dogfood = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolve_v2_dogfood)


def test_build_l2_execute_payload_defaults_to_provider_preference():
    payload = resolve_v2_dogfood.build_l2_execute_payload(
        parameters={"query": "rhumb"},
        provider="brave-search-api",
        credential_mode="rhumb_managed",
        interface="dogfood",
        max_cost_usd=0.05,
        provider_preference=None,
    )

    assert payload == {
        "parameters": {"query": "rhumb"},
        "credential_mode": "rhumb_managed",
        "interface": "dogfood",
        "policy": {
            "max_cost_usd": 0.05,
            "provider_preference": ["brave-search-api"],
        },
    }


def test_build_l1_execute_payload_sets_idempotency_and_optional_policy():
    payload = resolve_v2_dogfood.build_l1_execute_payload(
        capability="search.query",
        parameters={"query": "rhumb"},
        credential_mode="rhumb_managed",
        interface="dogfood",
        max_cost_usd=0.05,
    )

    assert payload["capability"] == "search.query"
    assert payload["parameters"] == {"query": "rhumb"}
    assert payload["credential_mode"] == "rhumb_managed"
    assert payload["interface"] == "dogfood"
    assert payload["policy"] == {"max_cost_usd": 0.05}
    assert payload["idempotency_key"].startswith("dogfood-")


def test_extract_receipt_and_explanation_ids_from_v2_payload():
    data = {
        "execution_id": "exec_123",
        "_rhumb_v2": {
            "receipt_id": "rcpt_nested",
            "explanation_id": "expl_123",
        },
    }

    assert resolve_v2_dogfood.extract_execution_id(data) == "exec_123"
    assert resolve_v2_dogfood.extract_receipt_id(data) == "rcpt_nested"
    assert resolve_v2_dogfood.extract_explanation_id(data) == "expl_123"


def test_extract_receipt_id_prefers_top_level_receipt_id():
    data = {
        "receipt_id": "rcpt_top",
        "_rhumb": {"receipt_id": "rcpt_old"},
        "_rhumb_v2": {"receipt_id": "rcpt_nested"},
    }

    assert resolve_v2_dogfood.extract_receipt_id(data) == "rcpt_top"


def test_get_api_key_uses_env_first():
    with patch.dict(resolve_v2_dogfood.os.environ, {"RHUMB_DOGFOOD_API_KEY": "rhumb_env_key"}, clear=True):
        assert resolve_v2_dogfood._get_api_key("RHUMB_DOGFOOD_API_KEY") == "rhumb_env_key"


def test_get_api_key_falls_back_to_sop_when_env_missing():
    with (
        patch.dict(resolve_v2_dogfood.os.environ, {}, clear=True),
        patch.object(resolve_v2_dogfood, "_load_api_key_from_sop", return_value="rhumb_sop_key"),
    ):
        assert resolve_v2_dogfood._get_api_key("RHUMB_DOGFOOD_API_KEY") == "rhumb_sop_key"


def test_build_summary_mentions_l1_and_l2_receipts():
    summary = resolve_v2_dogfood._build_summary({
        "config": {
            "capability": "search.query",
            "provider": "brave-search-api",
        },
        "layer2": {
            "execute": {
                "data": {
                    "execution_id": "exec_l2",
                    "provider_used": "brave-search-api",
                    "receipt_id": "rcpt_l2",
                }
            },
            "receipt": {"receipt_id": "rcpt_l2"},
        },
        "layer1": {
            "execute": {
                "data": {
                    "execution_id": "exec_l1",
                    "receipt_id": "rcpt_l1",
                }
            },
            "receipt": {"receipt_id": "rcpt_l1"},
        },
        "billing": {
            "summary": {"data": {"events_count": 4}},
        },
        "audit": {
            "status": {"data": {"total_events": 7}},
        },
    })

    assert "Resolve v2 dogfood complete" in summary
    assert "L2 search.query via brave-search-api exec=exec_l2 receipt=rcpt_l2" in summary
    assert "L1 provider=brave-search-api exec=exec_l1 receipt=rcpt_l1" in summary
    assert "billing_events=4" in summary
    assert "audit_events=7" in summary
