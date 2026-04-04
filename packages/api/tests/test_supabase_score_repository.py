"""Focused coverage for the publisher-only Supabase score repository."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from db.repository import SupabaseScoreRepository
from routes._supabase import SupabaseWriteUnavailable
from services.scoring import ANScoreResult


def _result() -> ANScoreResult:
    return ANScoreResult(
        service_slug="stripe",
        score=8.9,
        score_raw=8.9,
        execution_score=9.1,
        access_readiness_score=8.4,
        autonomy_score=7.2,
        aggregate_recommendation_score=8.9,
        an_score_version="0.3",
        confidence=0.98,
        tier="L4",
        explanation="Stripe scores 8.9 because API parity is strong but browser-gated edges remain.",
        dimension_snapshot={
            "tier_labels": {"L4": "Native"},
            "autonomy": {
                "avg": 7.2,
                "confidence": 0.9,
                "dimensions": [
                    {
                        "code": "P1",
                        "name": "payment_autonomy",
                        "score": 9.0,
                        "rationale": "x402 / API-native payments",
                        "confidence": 0.9,
                    },
                    {
                        "code": "G1",
                        "name": "governance_readiness",
                        "score": 6.5,
                        "rationale": "strong access controls",
                        "confidence": 0.8,
                    },
                    {
                        "code": "W1",
                        "name": "web_accessibility",
                        "score": 6.0,
                        "rationale": "AAG AA navigable UI",
                        "confidence": 0.7,
                    },
                ],
            },
            "score_breakdown": {
                "execution": 9.1,
                "access_readiness": 8.4,
                "autonomy": 7.2,
                "aggregate_recommendation": 8.9,
                "version": "0.3",
            },
        },
        calculated_at=datetime(2026, 4, 3, 16, 30, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_save_score_updates_existing_row_and_appends_audit_chain() -> None:
    repository = SupabaseScoreRepository()

    with (
        patch(
            "db.repository.supabase_fetch",
            new=AsyncMock(
                side_effect=[
                    [{"slug": "stripe"}],
                    [{"id": "score-row-1", "aggregate_recommendation_score": 8.5}],
                    [{"chain_hash": "abc123"}],
                ]
            ),
        ) as mock_fetch,
        patch(
            "db.repository.supabase_score_patch_required", new=AsyncMock(return_value=[{}])
        ) as mock_patch,
        patch(
            "db.repository.supabase_score_insert_required", new=AsyncMock(return_value=None)
        ) as mock_audit_insert,
        patch(
            "db.repository.supabase_score_insert_returning_required", new=AsyncMock()
        ) as mock_score_insert,
        patch("db.repository.get_signing_key_version", return_value=1),
    ):
        persisted_id = await repository.save_score("stripe", _result())

    assert persisted_id == "score-row-1"
    mock_score_insert.assert_not_awaited()
    assert mock_patch.await_args.args[0] == "scores?service_slug=eq.stripe"
    patched_payload = mock_patch.await_args.args[1]
    assert patched_payload["aggregate_recommendation_score"] == 8.9
    assert patched_payload["execution_score"] == 9.1
    assert patched_payload["tier_label"] == "Native"
    assert patched_payload["probe_metadata"]["writer_surface"] == "publisher"

    audit_payload = mock_audit_insert.await_args.args[1]
    assert audit_payload["service_slug"] == "stripe"
    assert audit_payload["old_score"] == 8.5
    assert audit_payload["new_score"] == 8.9
    assert audit_payload["prev_hash"] == "abc123"
    assert audit_payload["chain_hash"]
    assert audit_payload["key_version"] == 1
    assert mock_fetch.await_count == 3


@pytest.mark.asyncio
async def test_save_score_requires_known_service_slug() -> None:
    repository = SupabaseScoreRepository()

    with patch("db.repository.supabase_fetch", new=AsyncMock(return_value=[])):
        with pytest.raises(ValueError):
            await repository.save_score("unknown-service", _result())


@pytest.mark.asyncio
async def test_save_score_bubbles_audit_chain_failures() -> None:
    repository = SupabaseScoreRepository()

    with (
        patch(
            "db.repository.supabase_fetch",
            new=AsyncMock(
                side_effect=[
                    [{"slug": "stripe"}],
                    [],
                    [],
                ]
            ),
        ),
        patch(
            "db.repository.supabase_score_insert_returning_required",
            new=AsyncMock(return_value={"id": "score-row-2"}),
        ),
        patch(
            "db.repository.supabase_score_insert_required",
            new=AsyncMock(side_effect=SupabaseWriteUnavailable("audit unavailable")),
        ),
    ):
        with pytest.raises(SupabaseWriteUnavailable):
            await repository.save_score("stripe", _result())


@pytest.mark.asyncio
async def test_fetch_latest_score_parses_probe_metadata_back_into_stored_score() -> None:
    repository = SupabaseScoreRepository()
    row = {
        "id": "9d24cc06-3645-44e6-8090-e05fbaaf9998",
        "service_slug": "stripe",
        "aggregate_recommendation_score": 8.9,
        "confidence": 0.98,
        "tier": "L4",
        "probe_metadata": {
            "explanation": "Stored explanation.",
            "dimension_snapshot": {"score_breakdown": {"execution": 9.1}},
        },
        "calculated_at": "2026-04-03T16:30:00Z",
    }

    with patch("db.repository.supabase_fetch", new=AsyncMock(return_value=[row])):
        stored = await repository.fetch_latest_score("stripe")

    assert stored is not None
    assert stored.service_slug == "stripe"
    assert stored.score == 8.9
    assert stored.explanation == "Stored explanation."
    assert stored.dimension_snapshot["score_breakdown"]["execution"] == 9.1
    assert stored.calculated_at is not None
