"""Regression coverage for the callable review coverage audit script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "audit_callable_review_coverage.py"
    )
    spec = importlib.util.spec_from_file_location("audit_callable_review_coverage", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit_module = _load_module()


def test_audit_flags_runtime_evidence_without_runtime_backed_reviews(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        audit_module,
        "_callable_services",
        lambda base_url, timeout: [
            {
                "canonical_slug": "slack",
                "proxy_name": "slack",
                "auth_type": "oauth",
                "callable": True,
            },
            {
                "canonical_slug": "stripe",
                "proxy_name": "stripe",
                "auth_type": "api_key",
                "callable": True,
            },
        ],
    )

    review_payloads = {
        "slack": {
            "reviews": [
                {"id": "slack-1", "trust_label": "📘 Docs-backed"},
                {"id": "slack-2", "trust_label": "📘 Docs-backed"},
            ],
            "total_reviews": 2,
            "trust_summary": {
                "highest_source_type": "docs_derived",
                "runtime_backed_pct": 0.0,
                "freshest_evidence_at": "2026-03-26T12:00:00Z",
            },
        },
        "stripe": {
            "reviews": [
                {"id": "stripe-1", "trust_label": audit_module.RUNTIME_TRUST_LABEL},
                {"id": "stripe-2", "trust_label": "📘 Docs-backed"},
            ],
            "total_reviews": 2,
            "trust_summary": {
                "highest_source_type": "runtime_verified",
                "runtime_backed_pct": 50.0,
                "freshest_evidence_at": "2026-03-27T12:00:00Z",
            },
        },
    }
    evidence_payloads = {
        "slack": {
            "evidence": [
                {"id": "s-1", "source_type": "runtime_verified"},
                {"id": "s-2", "source_type": "tester_generated"},
                {"id": "s-3", "source_type": "docs_derived"},
            ],
            "total_evidence": 3,
        },
        "stripe": {
            "evidence": [
                {"id": "st-1", "source_type": "runtime_verified"},
                {"id": "st-2", "source_type": "manual_operator"},
            ],
            "total_evidence": 2,
        },
    }
    monkeypatch.setattr(
        audit_module,
        "_service_reviews",
        lambda base_url, slug, timeout: review_payloads[slug],
    )
    monkeypatch.setattr(
        audit_module,
        "_service_evidence",
        lambda base_url, slug, timeout: evidence_payloads[slug],
    )

    payload = audit_module.audit("https://api.example.test/v1", 1.0)
    providers = {row["service_slug"]: row for row in payload["providers"]}

    slack = providers["slack"]
    assert slack["runtime_backed_reviews"] == 0
    assert slack["total_reviews"] == 2
    assert slack["runtime_backed_evidence_records"] == 2
    assert slack["total_evidence_records"] == 3
    assert slack["runtime_backed_evidence_pct"] == 66.7
    assert slack["evidence_review_gap_suspected"] is True
    assert slack["non_runtime_reviews"] == 2

    stripe = providers["stripe"]
    assert stripe["runtime_backed_reviews"] == 1
    assert stripe["runtime_backed_evidence_records"] == 1
    assert stripe["runtime_backed_evidence_pct"] == 50.0
    assert stripe["evidence_review_gap_suspected"] is False

    assert payload["weakest_runtime_depth"] == 0
    assert payload["weakest_bucket"] == ["slack"]


def test_audit_does_not_flag_gap_when_service_has_no_reviews(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        audit_module,
        "_callable_services",
        lambda base_url, timeout: [
            {
                "canonical_slug": "new-service",
                "proxy_name": "new-service",
                "auth_type": None,
                "callable": True,
            }
        ],
    )
    monkeypatch.setattr(
        audit_module,
        "_service_reviews",
        lambda base_url, slug, timeout: {
            "reviews": [],
            "total_reviews": 0,
            "trust_summary": {
                "highest_source_type": None,
                "runtime_backed_pct": 0.0,
                "freshest_evidence_at": None,
            },
        },
    )
    monkeypatch.setattr(
        audit_module,
        "_service_evidence",
        lambda base_url, slug, timeout: {
            "evidence": [{"id": "n-1", "source_type": "runtime_verified"}],
            "total_evidence": 1,
        },
    )

    payload = audit_module.audit("https://api.example.test/v1", 1.0)

    assert payload["providers"][0]["runtime_backed_evidence_records"] == 1
    assert payload["providers"][0]["evidence_review_gap_suspected"] is False


def test_print_human_surfaces_mismatch_flag(capsys: Any) -> None:
    audit_module._print_human(
        {
            "base_url": "https://api.example.test/v1",
            "callable_provider_count": 1,
            "weakest_runtime_depth": 0,
            "weakest_bucket": ["slack"],
            "providers": [
                {
                    "service_slug": "slack",
                    "proxy_name": "slack",
                    "auth_type": "oauth",
                    "callable": True,
                    "total_reviews": 2,
                    "runtime_backed_reviews": 0,
                    "non_runtime_reviews": 2,
                    "total_evidence_records": 3,
                    "runtime_backed_evidence_records": 2,
                    "runtime_backed_evidence_pct": 66.7,
                    "evidence_review_gap_suspected": True,
                    "highest_source_type": "docs_derived",
                    "runtime_backed_review_pct": 0.0,
                    "reported_runtime_backed_pct": 0.0,
                    "freshest_evidence_at": "2026-03-26T12:00:00Z",
                }
            ],
        }
    )

    output = capsys.readouterr().out
    assert "Evidence/review mismatches suspected: 1" in output
    assert "Flagged providers: slack" in output
    assert "MISMATCH" in output
