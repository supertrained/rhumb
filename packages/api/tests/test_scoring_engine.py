"""Scoring engine coverage for WU 1.1."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from db.repository import InMemoryScoreRepository, SQLAlchemyScoreRepository
from services.fixtures import HAND_SCORED_FIXTURES
from services.scoring import EvidenceInput, ScoringService


@pytest.mark.parametrize("service_slug", ["stripe", "hubspot", "sendgrid", "resend", "github"])
def test_composite_reproduces_hand_scored_baselines(service_slug: str) -> None:
    """Weighted composite should stay within ±0.2 of hand-scored fixtures."""
    fixture = HAND_SCORED_FIXTURES[service_slug]
    scoring = ScoringService()
    score = scoring.calculate_composite(dict(fixture["dimensions"]))
    assert abs(score - float(fixture["expected_score"])) <= 0.2


def test_composite_handles_na_dimensions_with_weight_redistribution() -> None:
    """N/A dimensions should not penalize the score when weights are redistributed."""
    scoring = ScoringService()
    dimensions = {
        "I1": 8.0,
        "I2": 8.0,
        "I3": None,
        "F1": 8.0,
        "F2": None,
        "O1": 8.0,
    }
    assert scoring.calculate_composite(dimensions) == 8.0


def test_confidence_reflects_count_freshness_and_diversity() -> None:
    """Confidence should climb for richer evidence sets."""
    scoring = ScoringService()

    low = scoring.calculate_confidence(
        EvidenceInput(
            evidence_count=1,
            freshness="45 days ago",
            probe_types=["health"],
            production_telemetry=False,
        )
    )
    high = scoring.calculate_confidence(
        EvidenceInput(
            evidence_count=75,
            freshness="10 minutes ago",
            probe_types=["health", "auth", "schema", "load"],
            production_telemetry=True,
        )
    )

    assert low < 0.5
    assert high > 0.9


@pytest.mark.parametrize(
    ("score", "expected_tier"),
    [
        (0.0, "L1"),
        (3.95, "L1"),
        (3.99, "L1"),
        (4.0, "L2"),
        (5.95, "L2"),
        (5.99, "L2"),
        (6.0, "L3"),
        (7.99, "L3"),
        (8.0, "L4"),
        (10.0, "L4"),
    ],
)
def test_tier_assignment_boundaries(score: float, expected_tier: str) -> None:
    """Tier boundaries must follow the AN score spec exactly."""
    scoring = ScoringService()
    assert scoring.assign_tier(score) == expected_tier


def test_explanation_is_one_sentence_and_within_limit() -> None:
    """Explanation generation should always produce concise one-sentence output."""
    scoring = ScoringService()
    dimensions = dict(HAND_SCORED_FIXTURES["stripe"]["dimensions"])

    explanation = asyncio.run(scoring.generate_explanation("stripe", 8.9, dimensions))
    assert "\n" not in explanation
    assert len(explanation) <= 150
    assert explanation.endswith(".")


def test_database_round_trip_save_fetch_and_query() -> None:
    """Persisted scores should round-trip through repository integration."""
    repository = SQLAlchemyScoreRepository.from_url("sqlite+pysqlite:///:memory:")
    scoring = ScoringService(repository=repository)
    fixture = HAND_SCORED_FIXTURES["resend"]

    result = asyncio.run(
        scoring.score_service(
            service_slug="resend",
            dimensions=dict(fixture["dimensions"]),
            evidence=EvidenceInput(
                evidence_count=fixture["evidence_count"],
                freshness=fixture["freshness"],
                probe_types=list(fixture["probe_types"]),
                production_telemetry=bool(fixture["production_telemetry"]),
            ),
        )
    )

    score_id = scoring.save_score("resend", result)
    assert score_id is not None

    latest = scoring.fetch_latest_score("resend")
    assert latest is not None
    assert latest.service_slug == "resend"
    assert latest.score == result.score

    ranged = scoring.query_scores_by_range(min_score=8.0, max_score=10.0)
    assert any(item.service_slug == "resend" for item in ranged)


def test_score_endpoint_returns_full_schema(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /v1/score should return score + confidence + tier + explanation + snapshot."""
    from routes import scores as score_routes

    score_routes.get_scoring_service.cache_clear()
    monkeypatch.setattr(
        score_routes,
        "get_scoring_service",
        lambda: ScoringService(repository=InMemoryScoreRepository()),
    )

    fixture = HAND_SCORED_FIXTURES["stripe"]
    payload = {
        "service_slug": "stripe",
        "dimensions": fixture["dimensions"],
        "evidence_count": fixture["evidence_count"],
        "freshness": fixture["freshness"],
        "probe_types": fixture["probe_types"],
        "production_telemetry": fixture["production_telemetry"],
    }

    response = client.post("/v1/score", json=payload)
    assert response.status_code == 200

    body = dict(response.json())
    for field in ["score", "confidence", "tier", "explanation", "dimension_snapshot"]:
        assert field in body

    assert body["service_slug"] == "stripe"
    assert body["tier"] == "L4"


def test_score_endpoint_validation_errors(client) -> None:
    """Pydantic should reject unknown dimensions and invalid score bounds."""
    bad_payload: dict[str, Any] = {
        "service_slug": "example",
        "dimensions": {"X1": 9.0, "I1": 11.0},
        "evidence_count": 2,
        "freshness": "12 minutes ago",
    }

    response = client.post("/v1/score", json=bad_payload)
    assert response.status_code == 422
