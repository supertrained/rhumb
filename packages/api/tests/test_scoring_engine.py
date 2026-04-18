"""Scoring engine coverage for WU 1.1."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from db.repository import (
    InMemoryProbeRepository,
    InMemoryScoreRepository,
    SQLAlchemyScoreRepository,
    StoredScore,
)
from services.fixtures import HAND_SCORED_FIXTURES
from services.scoring import (
    AN_SCORE_VERSION,
    AXIS_WEIGHTS,
    EvidenceInput,
    ScoringService,
    load_autonomy_score_artifact,
)


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


def test_confidence_rewards_fresh_low_latency_probe_telemetry() -> None:
    """Probe freshness + latency telemetry should increase confidence when all else is equal."""
    scoring = ScoringService()

    baseline = scoring.calculate_confidence(
        EvidenceInput(
            evidence_count=30,
            freshness="6 hours ago",
            probe_types=["health", "schema"],
            production_telemetry=False,
        )
    )

    with_probe_telemetry = scoring.calculate_confidence(
        EvidenceInput(
            evidence_count=30,
            freshness="6 hours ago",
            probe_types=["health", "schema"],
            production_telemetry=False,
            probe_freshness="5 minutes ago",
            probe_latency_distribution_ms={"p50": 110, "p95": 290, "p99": 510, "samples": 12},
        )
    )

    assert with_probe_telemetry > baseline


def test_confidence_uses_probe_freshness_and_latency_as_separate_inputs() -> None:
    """Probe freshness and probe latency should independently affect confidence."""
    scoring = ScoringService()

    stale_probe = scoring.calculate_confidence(
        EvidenceInput(
            evidence_count=30,
            freshness="6 hours ago",
            probe_types=["health", "schema"],
            production_telemetry=False,
            probe_freshness="4 days ago",
            probe_latency_distribution_ms={"p50": 120, "p95": 290, "p99": 500, "samples": 8},
        )
    )

    fresh_probe = scoring.calculate_confidence(
        EvidenceInput(
            evidence_count=30,
            freshness="6 hours ago",
            probe_types=["health", "schema"],
            production_telemetry=False,
            probe_freshness="6 minutes ago",
            probe_latency_distribution_ms={"p50": 120, "p95": 290, "p99": 500, "samples": 8},
        )
    )

    high_latency_probe = scoring.calculate_confidence(
        EvidenceInput(
            evidence_count=30,
            freshness="6 hours ago",
            probe_types=["health", "schema"],
            production_telemetry=False,
            probe_freshness="6 minutes ago",
            probe_latency_distribution_ms={"p50": 600, "p95": 2800, "p99": 4200, "samples": 8},
        )
    )

    assert fresh_probe > stale_probe
    assert fresh_probe > high_latency_probe


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


def test_v03_aggregate_formula_uses_execution_access_autonomy_45_40_15() -> None:
    """Aggregate should blend execution/access/autonomy with 45/40/15 axis weights."""
    scoring = ScoringService()

    aggregate = scoring.calculate_aggregate_recommendation(
        execution_score_raw=8.9,
        access_readiness_score_raw=6.5,
        autonomy_score_raw=9.0,
    )

    expected = round(
        (8.9 * AXIS_WEIGHTS["execution"])
        + (6.5 * AXIS_WEIGHTS["access"])
        + (9.0 * AXIS_WEIGHTS["autonomy"]),
        1,
    )
    assert aggregate == expected


def test_v03_aggregate_renormalizes_when_access_missing() -> None:
    """When an axis is missing, aggregate should renormalize remaining axis weights."""
    scoring = ScoringService()

    aggregate = scoring.calculate_aggregate_recommendation(
        execution_score_raw=8.0,
        access_readiness_score_raw=None,
        autonomy_score_raw=4.0,
    )

    expected = round((8.0 * 0.75) + (4.0 * 0.25), 1)
    assert aggregate == expected


def test_autonomy_dimension_calculators_use_artifact_scores_for_known_service() -> None:
    """P1/G1/W1 calculators should return artifact-backed values and bounded confidence."""
    scoring = ScoringService()

    payment = scoring.calculate_payment_autonomy("stripe")
    governance = scoring.calculate_governance_readiness("stripe")
    web = scoring.calculate_web_accessibility("stripe")

    assert payment[0] == 10.0
    assert governance[0] == 10.0
    assert web[0] == 8.0

    for score, rationale, confidence in (payment, governance, web):
        assert 0.0 <= score <= 10.0
        assert rationale
        assert 0.0 <= confidence <= 1.0


def test_autonomy_score_artifact_covers_50_services() -> None:
    """Autonomy artifact should include complete coverage for the seeded 50-service dataset."""
    artifact_scores = load_autonomy_score_artifact()

    assert len(artifact_scores) == 50
    assert {"P1", "G1", "W1"}.issubset(artifact_scores["stripe"].keys())


def test_v02_tier_guardrail_caps_high_aggregate_when_access_is_low() -> None:
    """Access readiness below 4.0 should cap tier to L2 even if aggregate suggests L3/L4."""
    scoring = ScoringService()

    fixture = HAND_SCORED_FIXTURES["stripe"]
    result = asyncio.run(
        scoring.score_service(
            service_slug="stripe",
            dimensions=dict(fixture["dimensions"]),
            access_dimensions={
                "A1": 3.0,
                "A2": 3.0,
                "A3": 3.0,
                "A4": 3.0,
                "A5": 3.0,
                "A6": 3.0,
            },
            evidence=EvidenceInput(
                evidence_count=fixture["evidence_count"],
                freshness=fixture["freshness"],
                probe_types=list(fixture["probe_types"]),
                production_telemetry=bool(fixture["production_telemetry"]),
            ),
        )
    )

    assert result.aggregate_recommendation_score >= 6.0
    assert result.access_readiness_score == 3.0
    assert result.tier == "L2"


def test_v02_tier_guardrail_caps_high_aggregate_when_execution_is_low() -> None:
    """Execution below 6.0 should cap tier to L2 even when access score is high."""
    scoring = ScoringService()

    dimensions = {dimension: 5.0 for dimension in HAND_SCORED_FIXTURES["stripe"]["dimensions"]}
    result = asyncio.run(
        scoring.score_service(
            service_slug="stripe",
            dimensions=dimensions,
            access_dimensions={
                "A1": 9.0,
                "A2": 9.0,
                "A3": 9.0,
                "A4": 9.0,
                "A5": 9.0,
                "A6": 9.0,
            },
            evidence=EvidenceInput(
                evidence_count=25,
                freshness="2 hours ago",
                probe_types=["health", "schema"],
                production_telemetry=False,
            ),
        )
    )

    assert result.execution_score == 5.0
    assert result.aggregate_recommendation_score >= 6.0
    assert result.tier == "L2"


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

    score_id = asyncio.run(scoring.save_score("resend", result))
    assert score_id is not None

    latest = asyncio.run(scoring.fetch_latest_score("resend"))
    assert latest is not None
    assert latest.service_slug == "resend"
    assert latest.score == result.score

    ranged = asyncio.run(scoring.query_scores_by_range(min_score=8.0, max_score=10.0))
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
        "probe_freshness": "8 minutes ago",
        "probe_latency_distribution_ms": {"p50": 115, "p95": 320, "p99": 615, "samples": 9},
    }

    response = client.post("/v1/score", json=payload)
    assert response.status_code == 200

    body = dict(response.json())
    for field in [
        "score",
        "execution_score",
        "access_readiness_score",
        "autonomy_score",
        "autonomy",
        "an_score",
        "an_score_version",
        "confidence",
        "tier",
        "explanation",
        "dimension_snapshot",
    ]:
        assert field in body

    assert body["service_slug"] == "stripe"
    assert body["tier"] == "L4"
    assert body["score"] == body["an_score"]
    assert body["access_readiness_score"] is None
    assert body["autonomy_score"] is not None
    assert body["autonomy"]["avg"] == body["autonomy_score"]


def test_score_endpoint_supports_access_dimensions_contract(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /v1/score should expose v0.3 execution/access/autonomy contract fields."""
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
        "access_dimensions": {
            "A1": 8.0,
            "A2": 7.0,
            "A3": 9.0,
            "A4": 8.0,
            "A5": 8.0,
            "A6": 7.0,
        },
        "evidence_count": fixture["evidence_count"],
        "freshness": fixture["freshness"],
        "probe_types": fixture["probe_types"],
        "production_telemetry": fixture["production_telemetry"],
    }

    response = client.post("/v1/score", json=payload)
    assert response.status_code == 200

    body = response.json()
    assert body["an_score_version"] == AN_SCORE_VERSION
    assert body["access_readiness_score"] is not None
    assert body["autonomy_score"] is not None
    assert body["autonomy"] is not None
    assert body["execution_score"] >= 0.0
    assert body["score"] == body["an_score"]


def test_get_service_score_fixture_fallback_exposes_dual_scores(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /v1/services/{slug}/score should return v0.3 autonomy fields from fixture fallback."""
    from routes import scores as score_routes

    score_routes.get_scoring_service.cache_clear()
    monkeypatch.setattr(
        score_routes,
        "get_scoring_service",
        lambda: ScoringService(repository=InMemoryScoreRepository()),
    )

    response = client.get("/v1/services/stripe/score")
    assert response.status_code == 200

    body = response.json()
    assert body["an_score_version"] == AN_SCORE_VERSION
    assert body["access_readiness_score"] is not None
    assert body["autonomy"] is not None
    assert body["autonomy"]["avg"] is not None
    assert len(body["autonomy"]["dimensions"]) == 3
    assert body["score"] == body["an_score"]


def test_compare_route_exposes_dual_score_fields(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /v1/compare should include v0.3 aggregate fields for each compared service."""
    from routes import scores as score_routes

    score_routes.get_scoring_service.cache_clear()
    monkeypatch.setattr(
        score_routes,
        "get_scoring_service",
        lambda: ScoringService(repository=InMemoryScoreRepository()),
    )

    response = client.get("/v1/compare?services=stripe,resend")
    assert response.status_code == 200

    payload = response.json()["data"]["comparison"]
    assert len(payload) == 2

    for item in payload:
        assert item["an_score_version"] == AN_SCORE_VERSION
        assert item["score"] == item["an_score"]
        assert item["execution_score"] >= 0.0
        assert item["access_readiness_score"] is not None
        assert item["autonomy_score"] is not None


def test_get_service_score_reads_alias_backed_stored_score_with_canonical_slug(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /v1/services/{slug}/score should read alias-backed stored rows and canonicalize explanation text."""
    from routes import scores as score_routes

    score_routes.get_scoring_service.cache_clear()
    repository = InMemoryScoreRepository(
        _rows=[
            StoredScore(
                id=uuid4(),
                service_slug="brave-search",
                score=8.7,
                confidence=0.91,
                tier="L4",
                explanation="brave-search outranked pdl on fresh probes.",
                dimension_snapshot={
                    "score_breakdown": {
                        "execution": 8.4,
                        "access_readiness": 8.8,
                        "autonomy": 8.9,
                        "aggregate_recommendation": 8.7,
                        "version": AN_SCORE_VERSION,
                    }
                },
                calculated_at=datetime(2026, 4, 16, 18, 0, tzinfo=timezone.utc),
            )
        ]
    )
    monkeypatch.setattr(
        score_routes,
        "get_scoring_service",
        lambda: ScoringService(repository=repository),
    )

    response = client.get("/v1/services/brave-search-api/score")
    assert response.status_code == 200

    body = response.json()
    assert body["service_slug"] == "brave-search-api"
    assert body["an_score"] == 8.7
    assert body["execution_score"] == 8.4
    assert body["access_readiness_score"] == 8.8
    assert body["autonomy_score"] == 8.9
    assert body["an_score_version"] == AN_SCORE_VERSION
    assert body["explanation"] == "brave-search-api outranked people-data-labs on fresh probes."


def test_get_service_score_canonicalizes_alternate_aliases_in_explanation_when_row_is_already_canonical(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stored canonical score rows should still rewrite alternate alias mentions in explanation text."""
    from routes import scores as score_routes

    score_routes.get_scoring_service.cache_clear()
    repository = InMemoryScoreRepository(
        _rows=[
            StoredScore(
                id=uuid4(),
                service_slug="brave-search-api",
                score=8.7,
                confidence=0.91,
                tier="L4",
                explanation="brave-search-api outranked pdl on fresh probes.",
                dimension_snapshot={
                    "score_breakdown": {
                        "execution": 8.4,
                        "access_readiness": 8.8,
                        "autonomy": 8.9,
                        "aggregate_recommendation": 8.7,
                        "version": AN_SCORE_VERSION,
                    }
                },
                calculated_at=datetime(2026, 4, 16, 18, 0, tzinfo=timezone.utc),
            )
        ]
    )
    monkeypatch.setattr(
        score_routes,
        "get_scoring_service",
        lambda: ScoringService(repository=repository),
    )

    response = client.get("/v1/services/brave-search-api/score")
    assert response.status_code == 200

    body = response.json()
    assert body["service_slug"] == "brave-search-api"
    assert body["explanation"] == "brave-search-api outranked people-data-labs on fresh probes."


def test_get_service_score_accepts_mixed_case_alias_input(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /v1/services/{slug}/score should accept mixed-case canonical or alias inputs."""
    from routes import scores as score_routes

    score_routes.get_scoring_service.cache_clear()
    repository = InMemoryScoreRepository(
        _rows=[
            StoredScore(
                id=uuid4(),
                service_slug="brave-search",
                score=8.7,
                confidence=0.91,
                tier="L4",
                explanation="Alias-backed stored score.",
                dimension_snapshot={
                    "score_breakdown": {
                        "execution": 8.4,
                        "access_readiness": 8.8,
                        "autonomy": 8.9,
                        "aggregate_recommendation": 8.7,
                        "version": AN_SCORE_VERSION,
                    }
                },
                calculated_at=datetime(2026, 4, 16, 18, 0, tzinfo=timezone.utc),
            )
        ]
    )
    monkeypatch.setattr(
        score_routes,
        "get_scoring_service",
        lambda: ScoringService(repository=repository),
    )

    response = client.get("/v1/services/Brave-Search-Api/score")
    assert response.status_code == 200

    body = response.json()
    assert body["service_slug"] == "brave-search-api"
    assert body["an_score"] == 8.7
    assert body["execution_score"] == 8.4


def test_score_endpoint_canonicalizes_alias_backed_service_slug_on_write(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /v1/score should persist and return canonical public service ids."""
    from routes import scores as score_routes

    score_routes.get_scoring_service.cache_clear()
    repository = InMemoryScoreRepository()
    monkeypatch.setattr(
        score_routes,
        "get_scoring_service",
        lambda: ScoringService(repository=repository),
    )

    fixture = HAND_SCORED_FIXTURES["stripe"]
    response = client.post(
        "/v1/score",
        json={
            "service_slug": "Brave-Search",
            "dimensions": fixture["dimensions"],
            "evidence_count": fixture["evidence_count"],
            "freshness": fixture["freshness"],
            "probe_types": fixture["probe_types"],
            "production_telemetry": fixture["production_telemetry"],
        },
    )
    assert response.status_code == 200
    assert response.json()["service_slug"] == "brave-search-api"

    latest = asyncio.run(repository.fetch_latest_score("brave-search-api"))
    legacy = asyncio.run(repository.fetch_latest_score("brave-search"))

    assert latest is not None
    assert latest.service_slug == "brave-search-api"
    assert legacy is None


def test_score_endpoint_probe_hydration_reads_alias_backed_latest_probe_for_canonical_service(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /v1/score should hydrate probe telemetry across canonical and legacy alias forms."""
    from routes import scores as score_routes

    score_routes.get_scoring_service.cache_clear()
    score_routes.get_probe_repository.cache_clear()

    scoring_service = ScoringService(repository=InMemoryScoreRepository())
    probe_repository = InMemoryProbeRepository()
    probe_repository.save_probe(
        service_slug="brave-search",
        probe_type="health",
        status="ok",
        latency_ms=180,
        probe_metadata={
            "latency_distribution_ms": {"p50": 120, "p95": 280, "p99": 460, "samples": 8}
        },
    )

    monkeypatch.setattr(score_routes, "get_scoring_service", lambda: scoring_service)
    monkeypatch.setattr(score_routes, "get_probe_repository", lambda: probe_repository)

    fixture = HAND_SCORED_FIXTURES["stripe"]
    payload = {
        "service_slug": "Brave-Search-Api",
        "dimensions": fixture["dimensions"],
        "evidence_count": 30,
        "freshness": "6 hours ago",
        "probe_types": ["health", "schema"],
        "production_telemetry": False,
    }

    baseline_response = client.post("/v1/score", json=payload)
    assert baseline_response.status_code == 200
    baseline_confidence = baseline_response.json()["confidence"]

    hydrated_response = client.post(
        "/v1/score",
        json={**payload, "hydrate_probe_telemetry": True},
    )
    assert hydrated_response.status_code == 200
    assert hydrated_response.json()["service_slug"] == "brave-search-api"
    hydrated_confidence = hydrated_response.json()["confidence"]

    assert hydrated_confidence > baseline_confidence


def test_compare_route_canonicalizes_alias_inputs_and_alias_backed_stored_rows(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /v1/compare should normalize alias requests and alias-backed stored rows to canonical ids."""
    from routes import scores as score_routes

    score_routes.get_scoring_service.cache_clear()
    repository = InMemoryScoreRepository(
        _rows=[
            StoredScore(
                id=uuid4(),
                service_slug="brave-search",
                score=8.7,
                confidence=0.91,
                tier="L4",
                explanation="Alias-backed stored score.",
                dimension_snapshot={
                    "score_breakdown": {
                        "execution": 8.4,
                        "access_readiness": 8.8,
                        "autonomy": 8.9,
                        "aggregate_recommendation": 8.7,
                        "version": AN_SCORE_VERSION,
                    }
                },
                calculated_at=datetime(2026, 4, 16, 18, 0, tzinfo=timezone.utc),
            )
        ]
    )
    monkeypatch.setattr(
        score_routes,
        "get_scoring_service",
        lambda: ScoringService(repository=repository),
    )

    response = client.get("/v1/compare?services=brave-search-api,brave-search")
    assert response.status_code == 200

    body = response.json()["data"]
    assert body["services"] == ["brave-search-api"]
    assert body["comparison"] == [
        {
            "service_slug": "brave-search-api",
            "an_score": 8.7,
            "score": 8.7,
            "execution_score": 8.4,
            "access_readiness_score": 8.8,
            "autonomy_score": 8.9,
            "an_score_version": AN_SCORE_VERSION,
            "confidence": 0.91,
            "tier": "L4",
            "tier_label": "Native",
        }
    ]


def test_compare_route_accepts_mixed_case_alias_inputs(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /v1/compare should canonicalize mixed-case alias inputs before deduping."""
    from routes import scores as score_routes

    score_routes.get_scoring_service.cache_clear()
    repository = InMemoryScoreRepository(
        _rows=[
            StoredScore(
                id=uuid4(),
                service_slug="brave-search",
                score=8.7,
                confidence=0.91,
                tier="L4",
                explanation="Alias-backed stored score.",
                dimension_snapshot={
                    "score_breakdown": {
                        "execution": 8.4,
                        "access_readiness": 8.8,
                        "autonomy": 8.9,
                        "aggregate_recommendation": 8.7,
                        "version": AN_SCORE_VERSION,
                    }
                },
                calculated_at=datetime(2026, 4, 16, 18, 0, tzinfo=timezone.utc),
            )
        ]
    )
    monkeypatch.setattr(
        score_routes,
        "get_scoring_service",
        lambda: ScoringService(repository=repository),
    )

    response = client.get("/v1/compare?services=Brave-Search-Api,Brave-Search")
    assert response.status_code == 200

    body = response.json()["data"]
    assert body["services"] == ["brave-search-api"]
    assert body["comparison"] == [
        {
            "service_slug": "brave-search-api",
            "an_score": 8.7,
            "score": 8.7,
            "execution_score": 8.4,
            "access_readiness_score": 8.8,
            "autonomy_score": 8.9,
            "an_score_version": AN_SCORE_VERSION,
            "confidence": 0.91,
            "tier": "L4",
            "tier_label": "Native",
        }
    ]


def test_autonomy_seed_migration_covers_all_artifact_services() -> None:
    """Seed migration should include one row for every autonomy-scored service."""
    repo_root = Path(__file__).resolve().parents[3]
    migration_sql = (repo_root / "packages/api/migrations/0010_seed_autonomy_scores.sql").read_text(
        encoding="utf-8"
    )

    migration_slugs = set(re.findall(r"\('([a-z0-9-]+)',\s*[0-9]+(?:\.[0-9]+)?", migration_sql))
    artifact_slugs = set(load_autonomy_score_artifact().keys())

    assert migration_slugs == artifact_slugs
    assert len(migration_slugs) == 50


def test_score_endpoint_can_hydrate_probe_telemetry_from_latest_probe(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hydration flag should pull probe freshness/latency from latest stored probe when omitted."""
    from routes import scores as score_routes

    score_routes.get_scoring_service.cache_clear()
    score_routes.get_probe_repository.cache_clear()

    scoring_service = ScoringService(repository=InMemoryScoreRepository())
    probe_repository = InMemoryProbeRepository()
    probe_repository.save_probe(
        service_slug="stripe",
        probe_type="health",
        status="ok",
        latency_ms=180,
        probe_metadata={
            "latency_distribution_ms": {"p50": 120, "p95": 280, "p99": 460, "samples": 8}
        },
    )

    monkeypatch.setattr(score_routes, "get_scoring_service", lambda: scoring_service)
    monkeypatch.setattr(score_routes, "get_probe_repository", lambda: probe_repository)

    fixture = HAND_SCORED_FIXTURES["stripe"]
    payload = {
        "service_slug": "stripe",
        "dimensions": fixture["dimensions"],
        "evidence_count": 30,
        "freshness": "6 hours ago",
        "probe_types": ["health", "schema"],
        "production_telemetry": False,
    }

    baseline_response = client.post("/v1/score", json=payload)
    assert baseline_response.status_code == 200
    baseline_confidence = baseline_response.json()["confidence"]

    hydrated_response = client.post(
        "/v1/score",
        json={**payload, "hydrate_probe_telemetry": True},
    )
    assert hydrated_response.status_code == 200
    hydrated_confidence = hydrated_response.json()["confidence"]

    assert hydrated_confidence > baseline_confidence


def test_score_endpoint_validation_errors(client) -> None:
    """Pydantic should reject unknown dimensions and invalid score bounds."""
    bad_payload: dict[str, Any] = {
        "service_slug": "example",
        "dimensions": {"X1": 9.0, "I1": 11.0},
        "access_dimensions": {"A9": 7.0},
        "evidence_count": 2,
        "freshness": "12 minutes ago",
    }

    response = client.post("/v1/score", json=bad_payload)
    assert response.status_code == 422
