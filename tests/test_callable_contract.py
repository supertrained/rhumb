"""Regression coverage for the callable-contract drift lock."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _load_module() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "callable_contract.py"
    spec = importlib.util.spec_from_file_location("callable_contract", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


contract_module = _load_module()

STATS_SOURCE = "https://api.rhumb.dev/v1/proxy/stats"
FETCHED_AT = "2026-09-10T00:00:00Z"


def test_extract_returns_exact_stats_slugs_and_ignores_circuits() -> None:
    payload = {
        "data": {
            "services_registered": 2,
            "services_callable": 1,
            "services_registered_slugs": ["algolia", "sendgrid"],
            "services_callable_slugs": ["algolia"],
            "circuits": {
                "bright-data": "closed",
                "sendgrid": "closed",
            },
            "per_service": {"bright-data": {"count": 1}},
            "pools": {"bright-data": {"pool_size": 1}},
            "per_service_coverage": "observed",
            "pools_coverage": "observed",
            "per_service_honesty": "not inventory",
            "pools_honesty": "not inventory",
        }
    }

    contract = contract_module.extract_from_stats(
        payload,
        fetched_at=FETCHED_AT,
        source=STATS_SOURCE,
    )

    assert contract.services_registered_slugs == ("algolia", "sendgrid")
    assert contract.services_callable_slugs == ("algolia",)


def test_missing_slug_keys_without_services_fallback_fails() -> None:
    payload = {
        "data": {
            "services_registered": 2,
            "services_callable": 2,
            "circuits": {"bright-data": "closed", "algolia": "closed"},
        }
    }

    with pytest.raises(contract_module.CallableContractError, match="missing slug lists"):
        contract_module.extract_from_stats(
            payload,
            fetched_at=FETCHED_AT,
            source=STATS_SOURCE,
        )


def test_extract_derives_from_services_fallback_not_circuits() -> None:
    stats = {
        "data": {
            "services_registered": 2,
            "services_callable": 1,
            "circuits": {"bright-data": "closed"},
        }
    }
    services = {
        "data": {
            "services": [
                {"canonical_slug": "sendgrid", "callable": False},
                {"canonical_slug": "algolia", "callable": True},
            ]
        }
    }

    contract = contract_module.extract_from_stats(
        stats,
        fetched_at=FETCHED_AT,
        source=STATS_SOURCE,
        services_fallback=services,
    )

    assert contract.services_registered_slugs == ("algolia", "sendgrid")
    assert contract.services_callable_slugs == ("algolia",)


def test_padding_callable_to_match_registered_fails_check(tmp_path: Path, monkeypatch: Any) -> None:
    json_path = tmp_path / "callable-contract.json"
    md_path = tmp_path / "CALLABLE-CONTRACT.md"
    json_path.write_text(
        json.dumps(
            {
                "fetched_at": FETCHED_AT,
                "source": STATS_SOURCE,
                "services_registered": 2,
                "services_callable": 1,
                "services_registered_slugs": ["algolia", "sendgrid"],
                "services_callable_slugs": ["algolia", "sendgrid"],
            },
            indent=2,
        )
        + "\n"
    )
    md_path.write_text("# stale\n")
    monkeypatch.setattr(contract_module, "CONTRACT_JSON", json_path)
    monkeypatch.setattr(contract_module, "CONTRACT_MD", md_path)

    with pytest.raises(contract_module.CallableContractError, match="services_callable"):
        contract_module.CallableContract(
            fetched_at=FETCHED_AT,
            source=STATS_SOURCE,
            services_registered=2,
            services_callable=1,
            services_registered_slugs=("algolia", "sendgrid"),
            services_callable_slugs=("algolia", "sendgrid"),
        )
    assert contract_module.main(["--check"]) == 1


def test_check_fails_when_markdown_is_stale(tmp_path: Path, monkeypatch: Any) -> None:
    contract = contract_module.CallableContract(
        fetched_at=FETCHED_AT,
        source=STATS_SOURCE,
        services_registered=2,
        services_callable=1,
        services_registered_slugs=("algolia", "sendgrid"),
        services_callable_slugs=("algolia",),
    )
    json_path = tmp_path / "callable-contract.json"
    md_path = tmp_path / "CALLABLE-CONTRACT.md"
    json_path.write_text(contract_module.render_json(contract))
    md_path.write_text("# stale\n")
    monkeypatch.setattr(contract_module, "CONTRACT_JSON", json_path)
    monkeypatch.setattr(contract_module, "CONTRACT_MD", md_path)

    with pytest.raises(contract_module.CallableContractError, match="out of date"):
        contract_module.check_contract(json_path, md_path)
    assert contract_module.main(["--check"]) == 1


def test_check_passes_when_markdown_matches_json(tmp_path: Path, monkeypatch: Any) -> None:
    contract = contract_module.CallableContract(
        fetched_at=FETCHED_AT,
        source=STATS_SOURCE,
        services_registered=2,
        services_callable=1,
        services_registered_slugs=("algolia", "sendgrid"),
        services_callable_slugs=("algolia",),
    )
    json_path = tmp_path / "callable-contract.json"
    md_path = tmp_path / "CALLABLE-CONTRACT.md"
    json_path.write_text(contract_module.render_json(contract))
    md_path.write_text(contract_module.render_markdown(contract))
    monkeypatch.setattr(contract_module, "CONTRACT_JSON", json_path)
    monkeypatch.setattr(contract_module, "CONTRACT_MD", md_path)

    assert contract_module.check_contract(json_path, md_path).services_callable_slugs == (
        "algolia",
    )
    assert contract_module.main(["--check"]) == 0
