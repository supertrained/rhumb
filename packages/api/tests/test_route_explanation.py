"""Tests for the route explanation engine (WU-41.3).

Verifies explanation building, candidate scoring, human summaries,
store/retrieve, and Layer 1 explanations.
"""

from __future__ import annotations

import pytest

from services.route_explanation import (
    RouteExplanation,
    _row_to_explanation,
    build_explanation,
    build_layer1_explanation,
    clear_explanation_store,
    get_explanation,
    store_explanation,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_store():
    """Clear the explanation store before each test."""
    clear_explanation_store()
    yield
    clear_explanation_store()


def _make_mappings() -> list[dict]:
    return [
        {
            "service_slug": "openai",
            "capability_id": "ai.generate_text",
            "cost_per_call": 0.05,
            "credential_modes": ["rhumb_managed", "byo"],
        },
        {
            "service_slug": "anthropic",
            "capability_id": "ai.generate_text",
            "cost_per_call": 0.04,
            "credential_modes": ["rhumb_managed"],
        },
        {
            "service_slug": "google-ai",
            "capability_id": "ai.generate_text",
            "cost_per_call": 0.02,
            "credential_modes": ["byo"],
        },
    ]


def _make_scores() -> dict[str, float]:
    return {
        "openai": 8.9,
        "anthropic": 8.5,
        "google-ai": 7.8,
    }


def _make_circuits() -> dict[str, str]:
    return {
        "openai": "closed",
        "anthropic": "closed",
        "google-ai": "closed",
    }


def _make_alias_mappings() -> list[dict]:
    return [
        {
            "service_slug": "brave-search",
            "capability_id": "search.query",
            "cost_per_call": 0.01,
            "credential_modes": ["byo"],
        },
        {
            "service_slug": "pdl",
            "capability_id": "search.query",
            "cost_per_call": 0.03,
            "credential_modes": ["byo"],
        },
    ]


def _make_alias_scores() -> dict[str, float]:
    return {
        "brave-search": 8.7,
        "pdl": 7.9,
    }


def _make_alias_circuits() -> dict[str, str]:
    return {
        "brave-search": "closed",
        "pdl": "closed",
    }


# ---------------------------------------------------------------------------
# Explanation building
# ---------------------------------------------------------------------------

class TestBuildExplanation:
    """Test the core explanation builder."""

    def test_basic_explanation(self):
        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=_make_mappings(),
            scores_by_slug=_make_scores(),
            circuit_states=_make_circuits(),
            selected_provider="openai",
        )

        assert exp.explanation_id.startswith("rexp_")
        assert exp.capability_id == "ai.generate_text"
        assert exp.winner_provider_id == "openai"
        assert exp.selection_reason == "highest_composite_score_within_policy"
        assert len(exp.candidates) == 3
        assert exp.layer == 2

    def test_all_candidates_have_factors(self):
        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=_make_mappings(),
            scores_by_slug=_make_scores(),
            circuit_states=_make_circuits(),
            selected_provider="openai",
        )

        for candidate in exp.candidates:
            assert "an_score" in candidate.factors
            assert "availability" in candidate.factors
            assert "estimated_cost" in candidate.factors
            assert "latency" in candidate.factors
            assert "credential_mode" in candidate.factors

    def test_eligible_candidates_sorted_by_composite(self):
        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=_make_mappings(),
            scores_by_slug=_make_scores(),
            circuit_states=_make_circuits(),
            selected_provider="openai",
        )

        eligible = [c for c in exp.candidates if c.eligible]
        scores = [c.composite_score for c in eligible]
        assert scores == sorted(scores, reverse=True)

    def test_only_eligible_provider(self):
        exp = build_explanation(
            capability_id="search.query",
            mappings=[_make_mappings()[0]],
            scores_by_slug={"openai": 8.0},
            circuit_states={"openai": "closed"},
            selected_provider="openai",
        )

        assert exp.selection_reason == "only_eligible_provider"

    def test_pinned_provider(self):
        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=_make_mappings(),
            scores_by_slug=_make_scores(),
            circuit_states=_make_circuits(),
            selected_provider="anthropic",
            policy_pin="anthropic",
        )

        assert exp.selection_reason == "agent_pinned"
        assert exp.policy_active is True

    def test_alias_backed_public_pin_is_normalized_for_explanation(self):
        exp = build_explanation(
            capability_id="search.query",
            mappings=_make_alias_mappings(),
            scores_by_slug=_make_alias_scores(),
            circuit_states=_make_alias_circuits(),
            selected_provider="brave-search",
            policy_pin="brave-search-api",
            policy_allow_only=["brave-search-api"],
        )

        brave = [c for c in exp.candidates if c.provider_id == "brave-search"][0]
        pdl = [c for c in exp.candidates if c.provider_id == "pdl"][0]

        assert exp.selection_reason == "agent_pinned"
        assert exp.winner_provider_id == "brave-search"
        assert exp.policy_active is True
        assert brave.policy_checks["pinned"] is True
        assert brave.policy_checks["allow_list_ok"] is True
        assert brave.eligible is True
        assert pdl.policy_checks["allow_list_ok"] is False
        assert pdl.ineligible_reason == "not_in_allow_list"

    def test_no_provider_available(self):
        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=_make_mappings(),
            scores_by_slug=_make_scores(),
            circuit_states=_make_circuits(),
            selected_provider=None,
        )

        assert exp.selection_reason == "no_provider_available"
        assert exp.winner_provider_id is None


# ---------------------------------------------------------------------------
# Policy filtering
# ---------------------------------------------------------------------------

class TestPolicyFiltering:
    """Test that policy controls show up in candidate explanations."""

    def test_deny_list(self):
        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=_make_mappings(),
            scores_by_slug=_make_scores(),
            circuit_states=_make_circuits(),
            selected_provider="openai",
            policy_deny=["anthropic"],
        )

        denied = [c for c in exp.candidates if c.provider_id == "anthropic"][0]
        assert denied.eligible is False
        assert denied.ineligible_reason == "excluded_by_deny_list"
        assert denied.policy_checks["denied"] is True

    def test_alias_backed_public_deny_is_normalized_for_explanation(self):
        exp = build_explanation(
            capability_id="search.query",
            mappings=_make_alias_mappings(),
            scores_by_slug=_make_alias_scores(),
            circuit_states=_make_alias_circuits(),
            selected_provider="brave-search",
            policy_deny=["people-data-labs"],
        )

        denied = [c for c in exp.candidates if c.provider_id == "pdl"][0]
        allowed = [c for c in exp.candidates if c.provider_id == "brave-search"][0]
        assert denied.eligible is False
        assert denied.ineligible_reason == "excluded_by_deny_list"
        assert denied.policy_checks["denied"] is True
        assert allowed.eligible is True

    def test_allow_only(self):
        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=_make_mappings(),
            scores_by_slug=_make_scores(),
            circuit_states=_make_circuits(),
            selected_provider="openai",
            policy_allow_only=["openai", "google-ai"],
        )

        excluded = [c for c in exp.candidates if c.provider_id == "anthropic"][0]
        assert excluded.eligible is False
        assert excluded.ineligible_reason == "not_in_allow_list"

    def test_circuit_open(self):
        circuits = _make_circuits()
        circuits["google-ai"] = "open"

        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=_make_mappings(),
            scores_by_slug=_make_scores(),
            circuit_states=circuits,
            selected_provider="openai",
        )

        google = [c for c in exp.candidates if c.provider_id == "google-ai"][0]
        assert google.eligible is False
        assert google.ineligible_reason == "circuit_open"

    def test_quality_floor(self):
        scores = _make_scores()
        scores["google-ai"] = 3.0  # Below default quality floor of 6.0

        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=_make_mappings(),
            scores_by_slug=scores,
            circuit_states=_make_circuits(),
            selected_provider="openai",
        )

        google = [c for c in exp.candidates if c.provider_id == "google-ai"][0]
        assert google.eligible is False
        assert google.ineligible_reason == "below_quality_floor"

    def test_cost_ceiling(self):
        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=_make_mappings(),
            scores_by_slug=_make_scores(),
            circuit_states=_make_circuits(),
            selected_provider="google-ai",
            max_cost_usd=0.03,
        )

        openai = [c for c in exp.candidates if c.provider_id == "openai"][0]
        assert openai.eligible is False
        assert openai.ineligible_reason == "exceeds_cost_ceiling"


# ---------------------------------------------------------------------------
# Human summary
# ---------------------------------------------------------------------------

class TestHumanSummary:
    """Test human-readable summary generation."""

    def test_summary_includes_winner(self):
        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=_make_mappings(),
            scores_by_slug=_make_scores(),
            circuit_states=_make_circuits(),
            selected_provider="openai",
        )

        assert "openai" in exp.human_summary.lower()

    def test_summary_mentions_deny(self):
        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=_make_mappings(),
            scores_by_slug=_make_scores(),
            circuit_states=_make_circuits(),
            selected_provider="openai",
            policy_deny=["anthropic"],
        )

        assert "deny" in exp.human_summary.lower()

    def test_no_provider_summary(self):
        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=[],
            scores_by_slug={},
            circuit_states={},
            selected_provider=None,
        )

        assert "no provider" in exp.human_summary.lower()


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    """Test dict and compact serialization."""

    def test_to_dict(self):
        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=_make_mappings(),
            scores_by_slug=_make_scores(),
            circuit_states=_make_circuits(),
            selected_provider="openai",
        )
        d = exp.to_dict()

        assert d["explanation_id"].startswith("rexp_")
        assert d["winner"]["provider_id"] == "openai"
        assert len(d["candidates"]) == 3
        assert isinstance(d["human_summary"], str)

    def test_to_compact(self):
        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=_make_mappings(),
            scores_by_slug=_make_scores(),
            circuit_states=_make_circuits(),
            selected_provider="openai",
        )
        c = exp.to_compact()

        assert c["winner"] == "openai"
        assert c["candidates_evaluated"] == 3
        assert c["candidates_eligible"] == 3

    def test_alias_backed_to_dict_uses_public_provider_ids(self):
        exp = build_explanation(
            capability_id="search.query",
            mappings=_make_alias_mappings(),
            scores_by_slug=_make_alias_scores(),
            circuit_states=_make_alias_circuits(),
            selected_provider="brave-search",
            policy_pin="brave-search-api",
            policy_allow_only=["brave-search-api"],
        )

        data = exp.to_dict()
        compact = exp.to_compact()

        assert data["winner"]["provider_id"] == "brave-search-api"
        assert data["candidates"][0]["provider_id"] == "brave-search-api"
        assert any(candidate["provider_id"] == "people-data-labs" for candidate in data["candidates"])
        assert "brave-search-api" in data["human_summary"]
        assert "brave-search selected" not in data["human_summary"]
        assert compact["winner"] == "brave-search-api"

    def test_candidate_factor_dict(self):
        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=_make_mappings(),
            scores_by_slug=_make_scores(),
            circuit_states=_make_circuits(),
            selected_provider="openai",
        )

        winner = exp.candidates[0]
        factor_dict = winner.factors["an_score"].to_dict()

        assert "value" in factor_dict
        assert "normalized_score" in factor_dict
        assert "weight" in factor_dict
        assert "weighted_contribution" in factor_dict


# ---------------------------------------------------------------------------
# Store / retrieve
# ---------------------------------------------------------------------------

class TestStore:
    """Test the in-memory explanation store."""

    def test_store_and_retrieve(self):
        exp = build_explanation(
            capability_id="ai.generate_text",
            mappings=_make_mappings(),
            scores_by_slug=_make_scores(),
            circuit_states=_make_circuits(),
            selected_provider="openai",
        )
        store_explanation(exp)

        retrieved = get_explanation(exp.explanation_id)
        assert retrieved is not None
        assert retrieved.explanation_id == exp.explanation_id
        assert retrieved.winner_provider_id == "openai"

    def test_retrieve_nonexistent(self):
        assert get_explanation("rexp_nonexistent") is None

    def test_row_to_explanation_canonicalizes_runtime_aliases(self):
        exp = _row_to_explanation(
            {
                "explanation_id": "rexp_persisted",
                "capability_id": "search.query",
                "winner_provider_id": "brave-search",
                "winner_composite_score": 0.91,
                "winner_reason": "persisted_route_explanation",
                "human_summary": "brave-search selected over pdl.",
                "candidates_json": [
                    {
                        "provider_id": "brave-search",
                        "eligible": True,
                        "composite_score": 0.91,
                        "factors": {},
                        "policy_checks": {},
                    },
                    {
                        "provider_id": "pdl",
                        "eligible": False,
                        "composite_score": 0.0,
                        "factors": {},
                        "policy_checks": {},
                        "ineligible_reason": "not_in_allow_list",
                    },
                ],
            }
        )

        assert exp.winner_provider_id == "brave-search-api"
        assert [candidate.provider_id for candidate in exp.candidates] == [
            "brave-search-api",
            "people-data-labs",
        ]
        assert "brave-search-api" in exp.human_summary
        assert "people-data-labs" in exp.human_summary
        assert "brave-search selected" not in exp.human_summary

    def test_store_eviction(self):
        """Store should evict oldest when capacity exceeded."""
        for i in range(1100):
            exp = build_explanation(
                capability_id=f"cap_{i}",
                mappings=[{"service_slug": "test", "cost_per_call": 0.01, "credential_modes": []}],
                scores_by_slug={"test": 7.0},
                circuit_states={"test": "closed"},
                selected_provider="test",
            )
            store_explanation(exp)

        # Should not exceed max capacity (1000)
        from services.route_explanation import _explanation_store
        assert len(_explanation_store) <= 1000


# ---------------------------------------------------------------------------
# Layer 1 explanations
# ---------------------------------------------------------------------------

class TestLayer1:
    """Test Layer 1 (agent-pinned) explanations."""

    def test_layer1_explanation(self):
        exp = build_layer1_explanation(
            capability_id="search.query",
            provider_id="brave-search-api",
        )

        assert exp.explanation_id.startswith("rexp_")
        assert exp.winner_provider_id == "brave-search-api"
        assert exp.selection_reason == "agent_pinned_layer1"
        assert exp.layer == 1
        assert exp.candidates == []
        assert "layer 1" in exp.human_summary.lower()

    def test_layer1_stored_and_retrieved(self):
        exp = build_layer1_explanation(
            capability_id="search.query",
            provider_id="tavily",
        )
        store_explanation(exp)

        retrieved = get_explanation(exp.explanation_id)
        assert retrieved is not None
        assert retrieved.selection_reason == "agent_pinned_layer1"
