"""Focused coverage for the direct Postgres score publisher rail."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

from db.repository import DirectPostgresScorePublisherRepository
from services.scoring import ANScoreResult


@pytest.fixture
def repository() -> DirectPostgresScorePublisherRepository:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))
        conn.execute(text("CREATE TABLE services (slug TEXT PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE scores ("
                "id TEXT PRIMARY KEY, "
                "service_slug TEXT NOT NULL REFERENCES services(slug), "
                "aggregate_recommendation_score REAL, "
                "execution_score REAL, "
                "access_readiness_score REAL, "
                "confidence REAL, "
                "tier TEXT, "
                "tier_label TEXT, "
                "probe_metadata TEXT, "
                "calculated_at TEXT NOT NULL, "
                "payment_autonomy REAL, "
                "payment_autonomy_rationale TEXT, "
                "payment_autonomy_confidence REAL, "
                "governance_readiness REAL, "
                "governance_readiness_rationale TEXT, "
                "governance_readiness_confidence REAL, "
                "web_accessibility REAL, "
                "web_accessibility_rationale TEXT, "
                "web_accessibility_confidence REAL, "
                "autonomy_score REAL"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE score_audit_chain ("
                "entry_id TEXT PRIMARY KEY, "
                "service_slug TEXT NOT NULL REFERENCES services(slug), "
                "old_score REAL, "
                "new_score REAL NOT NULL, "
                "change_reason TEXT NOT NULL, "
                "created_at TEXT NOT NULL, "
                "chain_hash TEXT NOT NULL, "
                "prev_hash TEXT NOT NULL"
                ")"
            )
        )
        conn.execute(text("INSERT INTO services (slug) VALUES ('stripe')"))
    return DirectPostgresScorePublisherRepository(engine)


def _result(score: float = 8.9) -> ANScoreResult:
    return ANScoreResult(
        service_slug="stripe",
        score=score,
        score_raw=score,
        execution_score=9.1,
        access_readiness_score=8.4,
        autonomy_score=7.2,
        aggregate_recommendation_score=score,
        an_score_version="0.3",
        confidence=0.98,
        tier="L4",
        explanation="Stripe scores strongly on governed execution.",
        dimension_snapshot={
            "tier_labels": {"L4": "Native"},
            "autonomy": {
                "avg": 7.2,
                "dimensions": [
                    {
                        "code": "P1",
                        "score": 9.0,
                        "rationale": "Payment-native",
                        "confidence": 0.9,
                    },
                    {
                        "code": "G1",
                        "score": 6.5,
                        "rationale": "Strong controls",
                        "confidence": 0.8,
                    },
                    {
                        "code": "W1",
                        "score": 6.0,
                        "rationale": "Navigable UI",
                        "confidence": 0.7,
                    },
                ],
            },
            "score_breakdown": {
                "execution": 9.1,
                "access_readiness": 8.4,
                "autonomy": 7.2,
                "aggregate_recommendation": score,
                "version": "0.3",
            },
        },
        calculated_at=datetime(2026, 4, 3, 17, 0, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_save_score_inserts_score_and_appends_audit_chain(
    repository: DirectPostgresScorePublisherRepository,
) -> None:
    persisted_id = await repository.save_score("stripe", _result())

    assert persisted_id

    stored = await repository.fetch_latest_score("stripe")
    assert stored is not None
    assert stored.service_slug == "stripe"
    assert stored.score == 8.9
    assert stored.explanation == "Stripe scores strongly on governed execution."

    rows = await repository.query_by_score_range(8.0, 9.5)
    assert [row.service_slug for row in rows] == ["stripe"]

    with repository._engine.begin() as conn:  # noqa: SLF001 - focused repository verification
        audit_row = (
            conn.execute(
                text(
                    "SELECT service_slug, old_score, new_score, change_reason, prev_hash, chain_hash "
                    "FROM score_audit_chain LIMIT 1"
                )
            )
            .mappings()
            .first()
        )

    assert audit_row is not None
    assert audit_row["service_slug"] == "stripe"
    assert audit_row["old_score"] is None
    assert audit_row["new_score"] == 8.9
    assert audit_row["change_reason"] == "initial"
    assert audit_row["prev_hash"] == "0" * 64
    assert audit_row["chain_hash"]


@pytest.mark.asyncio
async def test_save_score_updates_existing_row_and_chains_from_previous_hash(
    repository: DirectPostgresScorePublisherRepository,
) -> None:
    first_id = await repository.save_score("stripe", _result(8.5))
    second_id = await repository.save_score("stripe", _result(9.0))

    assert second_id == first_id

    stored = await repository.fetch_latest_score("stripe")
    assert stored is not None
    assert stored.score == 9.0

    with repository._engine.begin() as conn:  # noqa: SLF001 - focused repository verification
        audit_rows = (
            conn.execute(
                text(
                    "SELECT old_score, new_score, change_reason, prev_hash, chain_hash "
                    "FROM score_audit_chain ORDER BY created_at ASC"
                )
            )
            .mappings()
            .all()
        )

    assert len(audit_rows) == 2
    assert audit_rows[1]["old_score"] == 8.5
    assert audit_rows[1]["new_score"] == 9.0
    assert audit_rows[1]["change_reason"] == "recalculation"
    assert audit_rows[1]["prev_hash"] == audit_rows[0]["chain_hash"]


@pytest.mark.asyncio
async def test_save_score_requires_known_service_slug(
    repository: DirectPostgresScorePublisherRepository,
) -> None:
    with pytest.raises(ValueError):
        await repository.save_score("unknown-service", _result())
