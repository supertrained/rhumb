"""Acceptance tests for public review and evidence read routes."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from routes import reviews as reviews_module


@pytest.fixture
def fake_supabase(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[dict[str, Any]]]:
    """Provide fixture-backed Supabase responses for review route tests."""
    tables: dict[str, list[dict[str, Any]]] = {
        "service_reviews": [],
        "review_evidence_links": [],
        "evidence_records": [],
    }

    async def _fake_fetch(path: str) -> list[dict[str, Any]]:
        _, _, query = path.partition("?")
        params = parse_qs(query)

        if path.startswith("service_reviews?"):
            rows = list(tables["service_reviews"])
            if "service_slug" in params:
                slug_filter = params["service_slug"][0]
                if slug_filter.startswith("eq."):
                    slug = unquote(slug_filter.removeprefix("eq."))
                    rows = [row for row in rows if row.get("service_slug") == slug]
                elif slug_filter.startswith("in.("):
                    raw = slug_filter.removeprefix("in.(").removesuffix(")")
                    slugs = {unquote(value) for value in raw.split(",") if value}
                    rows = [row for row in rows if row.get("service_slug") in slugs]
            if params.get("review_status") == ["eq.published"]:
                rows = [row for row in rows if row.get("review_status") == "published"]
            select_fields = params.get("select", [""])[0]
            if select_fields == "id,review_type":
                rows = [
                    {"id": row.get("id"), "review_type": row.get("review_type")}
                    for row in rows
                ]
            return sorted(rows, key=lambda row: row.get("reviewed_at", ""), reverse=True)

        if path.startswith("review_evidence_links?"):
            if "review_id" not in params:
                return list(tables["review_evidence_links"])
            review_ids_raw = params["review_id"][0].removeprefix("in.(").removesuffix(")")
            review_ids = set(filter(None, review_ids_raw.split(",")))
            return [
                row
                for row in tables["review_evidence_links"]
                if str(row.get("review_id")) in review_ids
            ]

        if path.startswith("evidence_records?"):
            rows = list(tables["evidence_records"])
            if "service_slug" in params:
                slug_filter = params["service_slug"][0]
                if slug_filter.startswith("eq."):
                    slug = unquote(slug_filter.removeprefix("eq."))
                    rows = [row for row in rows if row.get("service_slug") == slug]
                elif slug_filter.startswith("in.("):
                    raw = slug_filter.removeprefix("in.(").removesuffix(")")
                    slugs = {unquote(value) for value in raw.split(",") if value}
                    rows = [row for row in rows if row.get("service_slug") in slugs]
            if "evidence_kind" in params:
                kind = unquote(params["evidence_kind"][0].removeprefix("eq."))
                rows = [row for row in rows if row.get("evidence_kind") == kind]
            if "id" in params:
                evidence_ids_raw = params["id"][0].removeprefix("in.(").removesuffix(")")
                evidence_ids = set(filter(None, evidence_ids_raw.split(",")))
                rows = [row for row in rows if str(row.get("id")) in evidence_ids]
            select_fields = params.get("select", [""])[0]
            if select_fields == "id,source_type":
                rows = [
                    {"id": row.get("id"), "source_type": row.get("source_type")}
                    for row in rows
                ]
            return sorted(rows, key=lambda row: row.get("observed_at", ""), reverse=True)

        raise AssertionError(f"Unexpected Supabase path: {path}")

    monkeypatch.setattr(reviews_module, "supabase_fetch", _fake_fetch)
    return tables


def test_get_service_reviews_returns_published_rows_only(
    client: TestClient, fake_supabase: dict[str, list[dict[str, Any]]]
) -> None:
    """Published review reads exclude drafts and internal reviewer agent IDs."""
    fake_supabase["service_reviews"].extend(
        [
            {
                "id": "review-published",
                "service_slug": "stripe",
                "review_type": "docs",
                "review_status": "published",
                "headline": "Stripe Agent Accessibility Guide",
                "summary": "Public summary",
                "reviewer_label": "Rhumb editorial team",
                "reviewed_at": "2026-03-10T15:16:07-07:00",
                "confidence": 0.6,
                "evidence_count": 3,
                "reviewer_agent_id": "secret-agent-id",
            },
            {
                "id": "review-draft",
                "service_slug": "stripe",
                "review_type": "manual",
                "review_status": "draft",
                "headline": "Draft that must stay hidden",
                "summary": "Internal only",
                "reviewer_label": "Internal",
                "reviewed_at": "2026-03-11T10:00:00Z",
                "confidence": 0.1,
                "evidence_count": 1,
                "reviewer_agent_id": "draft-agent-id",
            },
        ]
    )
    fake_supabase["review_evidence_links"].append(
        {"review_id": "review-published", "evidence_record_id": "evidence-docs"}
    )
    fake_supabase["evidence_records"].append(
        {
            "id": "evidence-docs",
            "service_slug": "stripe",
            "source_type": "docs_derived",
            "evidence_kind": "failure_mode",
            "title": "Docs-backed evidence",
            "summary": "Derived from docs",
            "observed_at": "2026-03-10T22:16:07Z",
            "fresh_until": "2026-04-09T22:16:07Z",
            "confidence": 0.6,
            "source_ref": "failure_modes/uuid",
        }
    )

    response = client.get("/v1/services/stripe/reviews")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service_slug"] == "stripe"
    assert payload["total_reviews"] == 1
    assert len(payload["reviews"]) == 1
    review = payload["reviews"][0]
    assert review == {
        "id": "review-published",
        "review_type": "docs",
        "review_status": "published",
        "headline": "Stripe Agent Accessibility Guide",
        "summary": "Public summary",
        "reviewer_label": "Rhumb editorial team",
        "reviewed_at": "2026-03-10T15:16:07-07:00",
        "confidence": 0.6,
        "evidence_count": 3,
        "trust_label": "\U0001F4C4 Docs-derived",
    }
    assert "reviewer_agent_id" not in review
    assert payload["trust_summary"] == {
        "highest_source_type": "docs_derived",
        "runtime_backed_pct": 0.0,
        "freshest_evidence_at": "2026-03-10T22:16:07Z",
    }


def test_get_service_reviews_runtime_backed_pct_uses_review_level_ratio(
    client: TestClient, fake_supabase: dict[str, list[dict[str, Any]]]
) -> None:
    """Service trust summary should use runtime-backed reviews / total reviews."""
    fake_supabase["service_reviews"].extend(
        [
            {
                "id": "review-runtime",
                "service_slug": "stripe",
                "review_type": "manual",
                "review_status": "published",
                "headline": "Runtime review",
                "summary": "Observed live",
                "reviewer_label": "Rhumb editorial team",
                "reviewed_at": "2026-03-10T10:00:00Z",
                "confidence": 0.9,
                "evidence_count": 2,
                "highest_trust_source": "runtime_verified",
            },
            {
                "id": "review-docs",
                "service_slug": "stripe",
                "review_type": "docs",
                "review_status": "published",
                "headline": "Docs review",
                "summary": "Docs-backed",
                "reviewer_label": "Rhumb editorial team",
                "reviewed_at": "2026-03-09T10:00:00Z",
                "confidence": 0.6,
                "evidence_count": 1,
            },
        ]
    )
    fake_supabase["review_evidence_links"].extend(
        [
            {"review_id": "review-runtime", "evidence_record_id": "evidence-runtime-1"},
            {"review_id": "review-runtime", "evidence_record_id": "evidence-runtime-2"},
            {"review_id": "review-docs", "evidence_record_id": "evidence-docs"},
        ]
    )
    fake_supabase["evidence_records"].extend(
        [
            {
                "id": "evidence-runtime-1",
                "service_slug": "stripe",
                "source_type": "runtime_verified",
                "evidence_kind": "failure_mode",
                "title": "Runtime evidence 1",
                "summary": "Observed through runtime",
                "observed_at": "2026-03-10T10:00:00Z",
                "fresh_until": "2026-04-10T10:00:00Z",
                "confidence": 0.95,
                "source_ref": "facts/runtime-1",
            },
            {
                "id": "evidence-runtime-2",
                "service_slug": "stripe",
                "source_type": "runtime_verified",
                "evidence_kind": "latency_snapshot",
                "title": "Runtime evidence 2",
                "summary": "Observed through runtime again",
                "observed_at": "2026-03-10T10:05:00Z",
                "fresh_until": "2026-04-10T10:05:00Z",
                "confidence": 0.92,
                "source_ref": "facts/runtime-2",
            },
            {
                "id": "evidence-docs",
                "service_slug": "stripe",
                "source_type": "docs_derived",
                "evidence_kind": "failure_mode",
                "title": "Docs evidence",
                "summary": "Derived from docs",
                "observed_at": "2026-03-09T10:00:00Z",
                "fresh_until": "2026-04-09T10:00:00Z",
                "confidence": 0.6,
                "source_ref": "facts/docs",
            },
        ]
    )

    response = client.get("/v1/services/stripe/reviews")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_reviews"] == 2
    assert payload["trust_summary"]["runtime_backed_pct"] == 50.0
    assert payload["trust_summary"]["highest_source_type"] == "runtime_verified"
    assert payload["trust_summary"]["freshest_evidence_at"] == "2026-03-10T10:05:00Z"


def test_get_service_evidence_returns_filtered_rows_and_utc_freshness(
    client: TestClient,
    fake_supabase: dict[str, list[dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evidence reads expose freshness from fresh_until compared to UTC now."""
    fake_supabase["evidence_records"].extend(
        [
            {
                "id": "evidence-fresh",
                "service_slug": "stripe",
                "source_type": "runtime_verified",
                "evidence_kind": "failure_mode",
                "title": "Fresh runtime evidence",
                "summary": "Observed recently",
                "observed_at": "2026-03-10T22:16:07Z",
                "fresh_until": "2026-03-14T00:00:00+00:00",
                "confidence": 0.9,
                "source_ref": "facts/1",
            },
            {
                "id": "evidence-stale",
                "service_slug": "stripe",
                "source_type": "docs_derived",
                "evidence_kind": "failure_mode",
                "title": "Stale docs evidence",
                "summary": "Expired",
                "observed_at": "2026-03-01T00:00:00Z",
                "fresh_until": "2026-03-12T23:59:59Z",
                "confidence": 0.4,
                "source_ref": "facts/2",
            },
            {
                "id": "evidence-other-kind",
                "service_slug": "stripe",
                "source_type": "probe_generated",
                "evidence_kind": "latency_snapshot",
                "title": "Wrong kind",
                "summary": "Should be filtered out",
                "observed_at": "2026-03-09T00:00:00Z",
                "fresh_until": "2026-03-15T00:00:00Z",
                "confidence": 0.8,
                "source_ref": "facts/3",
            },
        ]
    )
    monkeypatch.setattr(
        reviews_module,
        "_utc_now",
        lambda: datetime(2026, 3, 13, 23, 30, tzinfo=UTC),
    )

    response = client.get("/v1/services/stripe/evidence?kind=failure_mode")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service_slug"] == "stripe"
    assert payload["total_evidence"] == 2
    assert [item["id"] for item in payload["evidence"]] == [
        "evidence-fresh",
        "evidence-stale",
    ]
    assert payload["evidence"][0]["is_fresh"] is True
    assert payload["evidence"][1]["is_fresh"] is False


def test_get_service_reviews_resolves_proxy_alias_to_canonical_slug(
    client: TestClient, fake_supabase: dict[str, list[dict[str, Any]]]
) -> None:
    """Proxy aliases like `pdl` should resolve to canonical public review slugs."""
    fake_supabase["service_reviews"].append(
        {
            "id": "review-pdl",
            "service_slug": "people-data-labs",
            "review_type": "manual",
            "review_status": "published",
            "headline": "PDL runtime review",
            "summary": "Canonical slug evidence",
            "reviewer_label": "Rhumb editorial team",
            "reviewed_at": "2026-03-12T00:00:00Z",
            "confidence": 0.8,
            "evidence_count": 1,
            "highest_trust_source": "runtime_verified",
        }
    )
    fake_supabase["review_evidence_links"].append(
        {"review_id": "review-pdl", "evidence_record_id": "evidence-pdl"}
    )
    fake_supabase["evidence_records"].append(
        {
            "id": "evidence-pdl",
            "service_slug": "people-data-labs",
            "source_type": "runtime_verified",
            "evidence_kind": "failure_mode",
            "title": "PDL runtime evidence",
            "summary": "Observed through runtime",
            "observed_at": "2026-03-12T00:00:00Z",
            "fresh_until": "2026-04-12T00:00:00Z",
            "confidence": 0.9,
            "source_ref": "facts/pdl-runtime",
        }
    )

    response = client.get("/v1/services/pdl/reviews")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service_slug"] == "people-data-labs"
    assert payload["total_reviews"] == 1
    assert payload["reviews"][0]["headline"] == "PDL runtime review"
    assert payload["reviews"][0]["trust_label"] == "\U0001F7E2 Runtime-verified"


def test_get_service_reviews_falls_back_to_proxy_slug_for_canonical_alias(
    client: TestClient, fake_supabase: dict[str, list[dict[str, Any]]]
) -> None:
    """Canonical Brave slug should surface reviews stored on the proxy slug."""
    fake_supabase["service_reviews"].append(
        {
            "id": "review-brave-runtime",
            "service_slug": "brave-search",
            "review_type": "manual",
            "review_status": "published",
            "headline": "Brave runtime review",
            "summary": "Proxy-backed runtime proof",
            "reviewer_label": "Rhumb editorial team",
            "reviewed_at": "2026-03-26T11:08:24Z",
            "confidence": 0.95,
            "evidence_count": 1,
            "highest_trust_source": "runtime_verified",
        }
    )
    fake_supabase["review_evidence_links"].append(
        {"review_id": "review-brave-runtime", "evidence_record_id": "evidence-brave-runtime"}
    )
    fake_supabase["evidence_records"].append(
        {
            "id": "evidence-brave-runtime",
            "service_slug": "brave-search",
            "source_type": "runtime_verified",
            "evidence_kind": "failure_mode",
            "title": "Brave runtime evidence",
            "summary": "Observed through runtime",
            "observed_at": "2026-03-26T11:08:24Z",
            "fresh_until": "2026-04-26T11:08:24Z",
            "confidence": 0.95,
            "source_ref": "facts/brave-runtime",
        }
    )

    response = client.get("/v1/services/brave-search-api/reviews")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service_slug"] == "brave-search-api"
    assert payload["total_reviews"] == 1
    assert payload["reviews"][0]["headline"] == "Brave runtime review"
    assert payload["reviews"][0]["trust_label"] == "\U0001F7E2 Runtime-verified"


def test_get_service_reviews_canonicalizes_legacy_alias_mentions_in_text(
    client: TestClient, fake_supabase: dict[str, list[dict[str, Any]]]
) -> None:
    """Historical review copy should not leak runtime alias slugs on public reads."""
    fake_supabase["service_reviews"].append(
        {
            "id": "review-brave-legacy-text",
            "service_slug": "brave-search",
            "review_type": "manual",
            "review_status": "published",
            "headline": "brave-search runtime review",
            "summary": "Observed through brave-search during live validation",
            "reviewer_label": "Rhumb editorial team",
            "reviewed_at": "2026-03-26T11:08:24Z",
            "confidence": 0.95,
            "evidence_count": 1,
            "highest_trust_source": "runtime_verified",
        }
    )
    fake_supabase["review_evidence_links"].append(
        {"review_id": "review-brave-legacy-text", "evidence_record_id": "evidence-brave-legacy-text"}
    )
    fake_supabase["evidence_records"].append(
        {
            "id": "evidence-brave-legacy-text",
            "service_slug": "brave-search",
            "source_type": "runtime_verified",
            "evidence_kind": "failure_mode",
            "title": "Brave runtime evidence",
            "summary": "Observed through runtime",
            "observed_at": "2026-03-26T11:08:24Z",
            "fresh_until": "2026-04-26T11:08:24Z",
            "confidence": 0.95,
            "source_ref": "facts/brave-legacy-text",
        }
    )

    response = client.get("/v1/services/brave-search-api/reviews")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service_slug"] == "brave-search-api"
    assert payload["total_reviews"] == 1
    assert payload["reviews"][0]["headline"] == "brave-search-api runtime review"
    assert payload["reviews"][0]["summary"] == "Observed through brave-search-api during live validation"


def test_get_service_reviews_canonicalizes_alternate_service_alias_mentions_in_text(
    client: TestClient, fake_supabase: dict[str, list[dict[str, Any]]]
) -> None:
    """Alias-backed review copy should also rewrite alternate service aliases on public reads."""
    fake_supabase["service_reviews"].append(
        {
            "id": "review-brave-alternate-alias-text",
            "service_slug": "brave-search",
            "review_type": "manual",
            "review_status": "published",
            "headline": "brave-search won after pdl comparison",
            "summary": "Observed brave-search after pdl comparison during live validation",
            "reviewer_label": "Rhumb editorial team",
            "reviewed_at": "2026-03-26T11:08:24Z",
            "confidence": 0.95,
            "evidence_count": 1,
            "highest_trust_source": "runtime_verified",
        }
    )
    fake_supabase["review_evidence_links"].append(
        {
            "review_id": "review-brave-alternate-alias-text",
            "evidence_record_id": "evidence-brave-alternate-alias-text",
        }
    )
    fake_supabase["evidence_records"].append(
        {
            "id": "evidence-brave-alternate-alias-text",
            "service_slug": "brave-search",
            "source_type": "runtime_verified",
            "evidence_kind": "failure_mode",
            "title": "Brave runtime evidence",
            "summary": "Observed through runtime",
            "observed_at": "2026-03-26T11:08:24Z",
            "fresh_until": "2026-04-26T11:08:24Z",
            "confidence": 0.95,
            "source_ref": "facts/brave-alternate-alias-text",
        }
    )

    response = client.get("/v1/services/brave-search-api/reviews")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service_slug"] == "brave-search-api"
    assert payload["total_reviews"] == 1
    assert payload["reviews"][0]["headline"] == "brave-search-api won after people-data-labs comparison"
    assert payload["reviews"][0]["summary"] == (
        "Observed brave-search-api after people-data-labs comparison during live validation"
    )


def test_get_service_reviews_normalizes_mixed_case_alias_input(
    client: TestClient, fake_supabase: dict[str, list[dict[str, Any]]]
) -> None:
    """Mixed-case proxy aliases should still resolve to canonical public review slugs."""
    fake_supabase["service_reviews"].append(
        {
            "id": "review-pdl-mixed-case",
            "service_slug": "people-data-labs",
            "review_type": "manual",
            "review_status": "published",
            "headline": "PDL mixed-case review",
            "summary": "Canonical slug evidence",
            "reviewer_label": "Rhumb editorial team",
            "reviewed_at": "2026-03-12T00:00:00Z",
            "confidence": 0.8,
            "evidence_count": 1,
            "highest_trust_source": "runtime_verified",
        }
    )
    fake_supabase["review_evidence_links"].append(
        {"review_id": "review-pdl-mixed-case", "evidence_record_id": "evidence-pdl-mixed-case"}
    )
    fake_supabase["evidence_records"].append(
        {
            "id": "evidence-pdl-mixed-case",
            "service_slug": "people-data-labs",
            "source_type": "runtime_verified",
            "evidence_kind": "failure_mode",
            "title": "PDL mixed-case evidence",
            "summary": "Observed through runtime",
            "observed_at": "2026-03-12T00:00:00Z",
            "fresh_until": "2026-04-12T00:00:00Z",
            "confidence": 0.9,
            "source_ref": "facts/pdl-mixed-case",
        }
    )

    response = client.get("/v1/services/PDL/reviews")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service_slug"] == "people-data-labs"
    assert payload["total_reviews"] == 1
    assert payload["reviews"][0]["headline"] == "PDL mixed-case review"


def test_get_service_evidence_normalizes_mixed_case_canonical_input(
    client: TestClient,
    fake_supabase: dict[str, list[dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mixed-case canonical aliases should still surface proxy-backed evidence rows."""
    fake_supabase["evidence_records"].append(
        {
            "id": "evidence-brave-mixed-case",
            "service_slug": "brave-search",
            "source_type": "runtime_verified",
            "evidence_kind": "failure_mode",
            "title": "Brave mixed-case evidence",
            "summary": "Observed through runtime",
            "observed_at": "2026-03-26T11:08:24Z",
            "fresh_until": "2026-04-26T11:08:24Z",
            "confidence": 0.95,
            "source_ref": "facts/brave-mixed-case",
        }
    )
    monkeypatch.setattr(
        reviews_module,
        "_utc_now",
        lambda: datetime(2026, 3, 27, 0, 0, tzinfo=UTC),
    )

    response = client.get("/v1/services/Brave-Search-Api/evidence?kind=failure_mode")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service_slug"] == "brave-search-api"
    assert payload["total_evidence"] == 1
    assert payload["evidence"][0]["id"] == "evidence-brave-mixed-case"
    assert payload["evidence"][0]["is_fresh"] is True


def test_get_service_evidence_canonicalizes_legacy_alias_mentions_in_text(
    client: TestClient,
    fake_supabase: dict[str, list[dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Historical evidence text should not leak runtime alias slugs on public reads."""
    fake_supabase["evidence_records"].append(
        {
            "id": "evidence-brave-usage-summary",
            "service_slug": "brave-search",
            "source_type": "runtime_verified",
            "evidence_kind": "usage_summary",
            "title": "Usage summary for brave-search (2026-03-26)",
            "summary": "Aggregated 2 usage events for brave-search",
            "observed_at": "2026-03-26T11:08:24Z",
            "fresh_until": "2026-04-26T11:08:24Z",
            "confidence": 0.95,
            "source_ref": "usage_events:brave-search:2026-03-26",
        }
    )
    monkeypatch.setattr(
        reviews_module,
        "_utc_now",
        lambda: datetime(2026, 3, 27, 0, 0, tzinfo=UTC),
    )

    response = client.get("/v1/services/brave-search-api/evidence?kind=usage_summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service_slug"] == "brave-search-api"
    assert payload["total_evidence"] == 1
    assert payload["evidence"][0]["title"] == "Usage summary for brave-search-api (2026-03-26)"
    assert payload["evidence"][0]["summary"] == "Aggregated 2 usage events for brave-search-api"
    assert payload["evidence"][0]["source_ref"] == "usage_events:brave-search:2026-03-26"


def test_get_service_evidence_canonicalizes_alternate_service_alias_mentions_in_text(
    client: TestClient,
    fake_supabase: dict[str, list[dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Alias-backed evidence text should also rewrite alternate service aliases on public reads."""
    fake_supabase["evidence_records"].append(
        {
            "id": "evidence-brave-usage-summary-alternate-alias",
            "service_slug": "brave-search",
            "source_type": "runtime_verified",
            "evidence_kind": "usage_summary",
            "title": "Usage summary for brave-search after pdl comparison",
            "summary": "Aggregated 2 usage events for brave-search after pdl comparison",
            "observed_at": "2026-03-26T11:08:24Z",
            "fresh_until": "2026-04-26T11:08:24Z",
            "confidence": 0.95,
            "source_ref": "usage_events:brave-search:2026-03-26",
        }
    )
    monkeypatch.setattr(
        reviews_module,
        "_utc_now",
        lambda: datetime(2026, 3, 27, 0, 0, tzinfo=UTC),
    )

    response = client.get("/v1/services/brave-search-api/evidence?kind=usage_summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service_slug"] == "brave-search-api"
    assert payload["total_evidence"] == 1
    assert payload["evidence"][0]["title"] == (
        "Usage summary for brave-search-api after people-data-labs comparison"
    )
    assert payload["evidence"][0]["summary"] == (
        "Aggregated 2 usage events for brave-search-api after people-data-labs comparison"
    )
    assert payload["evidence"][0]["source_ref"] == "usage_events:brave-search:2026-03-26"


def test_get_service_reviews_returns_empty_list_for_unknown_service(
    client: TestClient, fake_supabase: dict[str, list[dict[str, Any]]]
) -> None:
    """Unknown services return an empty reviews slice rather than 404."""
    fake_supabase["service_reviews"].append(
        {
            "id": "review-other",
            "service_slug": "github",
            "review_type": "docs",
            "review_status": "published",
            "headline": "GitHub review",
            "summary": "Not stripe",
            "reviewer_label": "Rhumb editorial team",
            "reviewed_at": "2026-03-01T00:00:00Z",
            "confidence": 0.7,
            "evidence_count": 1,
        }
    )

    response = client.get("/v1/services/nonexistent/reviews")

    assert response.status_code == 200
    assert response.json() == {
        "service_slug": "nonexistent",
        "reviews": [],
        "total_reviews": 0,
        "trust_summary": {
            "highest_source_type": None,
            "runtime_backed_pct": 0.0,
            "freshest_evidence_at": None,
        },
    }


def test_get_review_stats_returns_fixture_totals(
    client: TestClient, fake_supabase: dict[str, list[dict[str, Any]]]
) -> None:
    """Stats use published review truth and fixture-backed evidence counts."""
    fake_supabase["service_reviews"].extend(
        [
            {
                "id": "review-1",
                "service_slug": "stripe",
                "review_type": "docs",
                "review_status": "published",
                "reviewed_at": "2026-03-10T00:00:00Z",
            },
            {
                "id": "review-2",
                "service_slug": "stripe",
                "review_type": "manual",
                "review_status": "published",
                "reviewed_at": "2026-03-09T00:00:00Z",
            },
            {
                "id": "review-3",
                "service_slug": "stripe",
                "review_type": "crawler",
                "review_status": "published",
                "reviewed_at": "2026-03-08T00:00:00Z",
            },
            {
                "id": "review-draft",
                "service_slug": "stripe",
                "review_type": "tester",
                "review_status": "draft",
                "reviewed_at": "2026-03-11T00:00:00Z",
            },
        ]
    )
    fake_supabase["evidence_records"].extend(
        [
            {"id": "e1", "service_slug": "stripe", "source_type": "docs_derived"},
            {"id": "e2", "service_slug": "stripe", "source_type": "runtime_verified"},
            {"id": "e3", "service_slug": "stripe", "source_type": "tester_generated"},
            {"id": "e4", "service_slug": "stripe", "source_type": "probe_generated"},
            {"id": "e5", "service_slug": "stripe", "source_type": "manual_operator"},
        ]
    )

    response = client.get("/v1/reviews/stats")

    assert response.status_code == 200
    assert response.json() == {
        "total_published_reviews": 3,
        "total_evidence_records": 5,
        "review_type_breakdown": {
            "docs": 1,
            "manual": 1,
            "tester": 0,
            "automated": 1,
        },
        "source_type_breakdown": {
            "docs_derived": 1,
            "runtime_verified": 1,
            "tester_generated": 1,
            "probe_generated": 1,
            "manual_operator": 1,
        },
        "quality_floor": {
            "runtime_backed_reviews": 0,
            "runtime_backed_pct": 0.0,
            "docs_only_pct": 100.0,
            "public_claim_eligible": False,
            "reason": "Below 100 reviews and 0% runtime-backed (requires ≥20%)",
        },
        "gate_4_progress": "3 / 500",
    }


@pytest.mark.parametrize(
    ("source_type", "expected"),
    [
        ("runtime_verified", "\U0001F7E2 Runtime-verified"),
        ("tester_generated", "\U0001F9EA Tester-generated"),
        ("probe_generated", "\U0001F50D Probe-generated"),
        ("manual_operator", "\U0001F527 Operator-verified"),
        ("docs_derived", "\U0001F4C4 Docs-derived"),
    ],
)
def test_trust_label_matches_source_type(source_type: str, expected: str) -> None:
    """Trust labels must stay honest to source_type."""
    assert reviews_module.trust_label(source_type) == expected


def test_is_fresh_uses_timezone_aware_utc_now(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freshness checks compare UTC instants rather than naive local timestamps."""
    monkeypatch.setattr(
        reviews_module,
        "_utc_now",
        lambda: datetime(2026, 3, 13, 19, 0, tzinfo=UTC),
    )

    assert reviews_module.is_fresh("2026-03-13T12:30:00-07:00") is True
    assert reviews_module.is_fresh("2026-03-13T11:59:59-07:00") is False
