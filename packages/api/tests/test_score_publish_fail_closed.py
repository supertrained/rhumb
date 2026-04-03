"""Route-level fail-closed coverage for score publication."""

from __future__ import annotations

import pytest

from routes._supabase import SupabaseWriteUnavailable
from services.fixtures import HAND_SCORED_FIXTURES
from services.scoring import ScoringService


class _FailingScoreRepository:
    async def save_score(self, service_slug, result):
        raise SupabaseWriteUnavailable("audit chain unavailable")

    async def fetch_latest_score(self, service_slug):  # pragma: no cover - not used here
        return None

    async def query_by_score_range(self, min_score=0.0, max_score=10.0):  # pragma: no cover
        return []


def test_score_route_fails_closed_when_publication_cannot_record_audit_chain(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from routes import scores as score_routes

    score_routes.get_scoring_service.cache_clear()
    monkeypatch.setattr(
        score_routes,
        "get_scoring_service",
        lambda: ScoringService(repository=_FailingScoreRepository()),
    )

    fixture = HAND_SCORED_FIXTURES["stripe"]
    response = client.post(
        "/v1/score",
        json={
            "service_slug": "stripe",
            "dimensions": fixture["dimensions"],
            "evidence_count": fixture["evidence_count"],
            "freshness": fixture["freshness"],
            "probe_types": fixture["probe_types"],
            "production_telemetry": fixture["production_telemetry"],
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Score publication failed before the audit chain could be durably recorded."
    )
