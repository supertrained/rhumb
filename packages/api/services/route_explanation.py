"""Route Explanation Engine (WU-41.3).

Generates a complete, queryable explanation for every Layer 2 routing
decision.  The explanation captures *why* a provider was chosen: which
candidates were evaluated, what factors contributed to each candidate's
composite score, what policy checks were applied, and a human-readable
summary of the outcome.

**Spec requirement (§2.3):**
> Every routing decision produces a complete, queryable explanation.

Layer 1 calls do not produce explanations — the agent explicitly chose
the provider, so there is nothing to explain.

Explanations are persisted to the ``route_explanations`` table, keyed by
``explanation_id``, and linked to the receipt via ``receipt_id``.

The ``GET /v2/receipts/{id}/explanation`` endpoint exposes them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from routes._supabase import supabase_fetch, supabase_insert

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Factor weights (from Resolve Product Spec §2.3)
# ---------------------------------------------------------------------------

DEFAULT_FACTOR_WEIGHTS = {
    "an_score": 0.20,
    "availability": 0.30,
    "estimated_cost_usd": 0.25,
    "latency_p50_ms": 0.15,
    "credential_mode_preference": 0.10,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CandidateFactor:
    """A single scoring factor for a candidate provider."""

    name: str
    raw_value: Any
    normalized_score: float
    weight: float
    weighted_contribution: float


@dataclass
class CandidateExplanation:
    """Full explanation for a single candidate provider."""

    provider_id: str
    provider_name: str | None = None
    eligible: bool = True
    composite_score: float = 0.0
    factors: list[CandidateFactor] = field(default_factory=list)
    policy_checks: dict[str, Any] = field(default_factory=dict)
    ineligibility_reason: str | None = None


@dataclass
class RouteExplanation:
    """Complete routing explanation for a Layer 2 execution."""

    explanation_id: str
    receipt_id: str | None = None
    capability_id: str | None = None
    created_at: str | None = None

    # Winner
    winner_provider_id: str | None = None
    winner_composite_score: float | None = None
    winner_reason: str | None = None

    # Candidates
    candidates: list[CandidateExplanation] = field(default_factory=list)

    # Human summary
    human_summary: str = ""

    # Timing
    evaluation_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the spec-defined JSON shape."""
        result: dict[str, Any] = {
            "explanation_id": self.explanation_id,
            "receipt_id": self.receipt_id,
            "capability_id": self.capability_id,
            "created_at": self.created_at,
        }

        if self.winner_provider_id:
            result["winner"] = {
                "provider_id": self.winner_provider_id,
                "composite_score": self.winner_composite_score,
                "selection_reason": self.winner_reason,
            }
        else:
            result["winner"] = None

        result["candidates"] = [
            self._candidate_to_dict(c) for c in self.candidates
        ]
        result["human_summary"] = self.human_summary
        result["evaluation_ms"] = self.evaluation_ms

        return result

    @staticmethod
    def _candidate_to_dict(c: CandidateExplanation) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "provider_id": c.provider_id,
            "provider_name": c.provider_name,
            "eligible": c.eligible,
            "composite_score": round(c.composite_score, 4) if c.composite_score else 0.0,
        }
        if c.factors:
            entry["factors"] = {
                f.name: {
                    "value": f.raw_value,
                    "normalized_score": round(f.normalized_score, 4),
                    "weight": f.weight,
                    "weighted_contribution": round(f.weighted_contribution, 4),
                }
                for f in c.factors
            }
        if c.policy_checks:
            entry["policy_checks"] = c.policy_checks
        if c.ineligibility_reason:
            entry["ineligibility_reason"] = c.ineligibility_reason
        return entry


def _generate_explanation_id() -> str:
    """Generate a unique explanation ID with the rexp_ prefix."""
    return f"rexp_{uuid.uuid4().hex[:16]}"


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Factor normalization helpers
# ---------------------------------------------------------------------------

def _normalize_an_score(score: float | None) -> float:
    """AN Score is already 0-10, normalize to 0-1."""
    if score is None:
        return 0.0
    return min(max(score / 10.0, 0.0), 1.0)


def _normalize_availability(uptime_pct: float | None) -> float:
    """Uptime percentage (0-100) → 0-1 score."""
    if uptime_pct is None:
        return 0.5  # Unknown = neutral
    return min(max(uptime_pct / 100.0, 0.0), 1.0)


def _normalize_cost(cost_usd: float | None, max_cost: float | None) -> float:
    """Lower cost is better. Normalize against max observed cost."""
    if cost_usd is None or max_cost is None or max_cost <= 0:
        return 0.5  # Unknown = neutral
    # Invert: cheaper = higher score
    return min(max(1.0 - (cost_usd / max_cost), 0.0), 1.0)


def _normalize_latency(latency_ms: float | None, max_latency: float | None) -> float:
    """Lower latency is better. Normalize against max observed latency."""
    if latency_ms is None or max_latency is None or max_latency <= 0:
        return 0.5
    return min(max(1.0 - (latency_ms / max_latency), 0.0), 1.0)


def _normalize_credential_preference(
    credential_modes: list[str] | None,
    requested_mode: str,
) -> float:
    """1.0 if the provider supports the requested credential mode, else 0.5."""
    if not credential_modes:
        return 0.5
    if requested_mode == "auto":
        return 1.0  # Any mode works
    return 1.0 if requested_mode in credential_modes else 0.3


# ---------------------------------------------------------------------------
# Explanation builder
# ---------------------------------------------------------------------------

class RouteExplanationEngine:
    """Builds a complete route explanation from routing context."""

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or DEFAULT_FACTOR_WEIGHTS

    def build_explanation(
        self,
        *,
        receipt_id: str | None = None,
        capability_id: str | None = None,
        winner_provider_id: str | None = None,
        winner_reason: str | None = None,
        all_mappings: list[dict[str, Any]],
        eligible_mappings: list[dict[str, Any]],
        policy_summary: dict[str, Any] | None = None,
        credential_mode: str = "auto",
        provider_details: dict[str, dict[str, Any]] | None = None,
    ) -> RouteExplanation:
        """Build a complete route explanation.

        Args:
            receipt_id: The receipt ID for the execution.
            capability_id: The capability that was executed.
            winner_provider_id: The provider that was selected.
            winner_reason: Why the winner was selected (from PolicyEngine).
            all_mappings: All capability_services mappings before policy filters.
            eligible_mappings: Mappings remaining after policy filters.
            policy_summary: Policy controls summary from PolicyEngine.
            credential_mode: Requested credential mode.
            provider_details: Pre-fetched provider details keyed by slug.
        """
        t_start = time.monotonic()
        explanation_id = _generate_explanation_id()
        now = _now_iso()

        provider_details = provider_details or {}
        policy_summary = policy_summary or {}
        pin = policy_summary.get("pin")
        deny_set = set(policy_summary.get("provider_deny", []))
        allow_only_set = set(policy_summary.get("allow_only", []))

        eligible_slugs = {m.get("service_slug") for m in eligible_mappings}

        # Compute normalization ceilings from eligible candidates
        costs = [
            float(m.get("cost_per_call") or 0)
            for m in eligible_mappings
            if m.get("cost_per_call") is not None
        ]
        max_cost = max(costs) if costs else None

        # For latency we use AN score as proxy (no live latency data yet)
        # We'll normalize against known range when real telemetry exists
        max_latency = 5000.0  # Placeholder ceiling

        candidates: list[CandidateExplanation] = []

        for mapping in all_mappings:
            slug = mapping.get("service_slug", "unknown")
            detail = provider_details.get(slug, {})
            an_score_raw = detail.get("aggregate_recommendation_score")
            cost_raw = float(mapping.get("cost_per_call") or 0) if mapping.get("cost_per_call") is not None else None
            credential_modes = mapping.get("credential_modes") or []

            # Policy checks
            is_denied = slug in deny_set
            is_allowed = not allow_only_set or slug in allow_only_set
            is_pinned = pin == slug if pin else False
            is_eligible = slug in eligible_slugs

            policy_checks = {
                "pinned": is_pinned,
                "denied": is_denied,
                "allowed_by_allow_only": is_allowed if allow_only_set else True,
                "cost_ceiling_ok": True,  # Updated below if applicable
            }

            if policy_summary.get("max_cost_usd") is not None and cost_raw is not None:
                policy_checks["cost_ceiling_ok"] = cost_raw <= policy_summary["max_cost_usd"]

            if not is_eligible:
                reason = "denied_by_policy" if is_denied else (
                    "not_in_allow_only" if not is_allowed else "filtered_by_routing"
                )
                candidates.append(CandidateExplanation(
                    provider_id=slug,
                    provider_name=detail.get("name"),
                    eligible=False,
                    composite_score=0.0,
                    policy_checks=policy_checks,
                    ineligibility_reason=reason,
                ))
                continue

            # Score factors
            factors: list[CandidateFactor] = []

            # AN Score
            an_normalized = _normalize_an_score(an_score_raw)
            an_weight = self.weights.get("an_score", 0.20)
            factors.append(CandidateFactor(
                name="an_score",
                raw_value=an_score_raw,
                normalized_score=an_normalized,
                weight=an_weight,
                weighted_contribution=an_normalized * an_weight,
            ))

            # Availability (placeholder until real monitoring)
            avail_normalized = _normalize_availability(None)
            avail_weight = self.weights.get("availability", 0.30)
            factors.append(CandidateFactor(
                name="availability",
                raw_value=None,
                normalized_score=avail_normalized,
                weight=avail_weight,
                weighted_contribution=avail_normalized * avail_weight,
            ))

            # Cost
            cost_normalized = _normalize_cost(cost_raw, max_cost)
            cost_weight = self.weights.get("estimated_cost_usd", 0.25)
            factors.append(CandidateFactor(
                name="estimated_cost_usd",
                raw_value=cost_raw,
                normalized_score=cost_normalized,
                weight=cost_weight,
                weighted_contribution=cost_normalized * cost_weight,
            ))

            # Latency (placeholder)
            latency_normalized = _normalize_latency(None, max_latency)
            latency_weight = self.weights.get("latency_p50_ms", 0.15)
            factors.append(CandidateFactor(
                name="latency_p50_ms",
                raw_value=None,
                normalized_score=latency_normalized,
                weight=latency_weight,
                weighted_contribution=latency_normalized * latency_weight,
            ))

            # Credential mode preference
            cred_normalized = _normalize_credential_preference(
                credential_modes, credential_mode,
            )
            cred_weight = self.weights.get("credential_mode_preference", 0.10)
            factors.append(CandidateFactor(
                name="credential_mode_preference",
                raw_value=credential_modes,
                normalized_score=cred_normalized,
                weight=cred_weight,
                weighted_contribution=cred_normalized * cred_weight,
            ))

            composite = sum(f.weighted_contribution for f in factors)

            candidates.append(CandidateExplanation(
                provider_id=slug,
                provider_name=detail.get("name"),
                eligible=True,
                composite_score=composite,
                factors=factors,
                policy_checks=policy_checks,
            ))

        # Find winner's composite score
        winner_composite = None
        if winner_provider_id:
            for c in candidates:
                if c.provider_id == winner_provider_id:
                    winner_composite = c.composite_score
                    break

        # Sort candidates: eligible first (by composite desc), then ineligible
        eligible_candidates = sorted(
            [c for c in candidates if c.eligible],
            key=lambda c: c.composite_score,
            reverse=True,
        )
        ineligible_candidates = [c for c in candidates if not c.eligible]
        candidates = eligible_candidates + ineligible_candidates

        # Build human summary
        human_summary = self._build_human_summary(
            winner_provider_id=winner_provider_id,
            winner_reason=winner_reason,
            candidates=candidates,
            policy_summary=policy_summary,
            provider_details=provider_details,
        )

        t_elapsed = (time.monotonic() - t_start) * 1000

        return RouteExplanation(
            explanation_id=explanation_id,
            receipt_id=receipt_id,
            capability_id=capability_id,
            created_at=now,
            winner_provider_id=winner_provider_id,
            winner_composite_score=winner_composite,
            winner_reason=winner_reason,
            candidates=candidates,
            human_summary=human_summary,
            evaluation_ms=round(t_elapsed, 2),
        )

    def _build_human_summary(
        self,
        *,
        winner_provider_id: str | None,
        winner_reason: str | None,
        candidates: list[CandidateExplanation],
        policy_summary: dict[str, Any],
        provider_details: dict[str, dict[str, Any]],
    ) -> str:
        """Generate a human-readable explanation of the routing decision."""
        if not winner_provider_id:
            return "No provider was selected."

        winner_detail = provider_details.get(winner_provider_id, {})
        winner_name = winner_detail.get("name", winner_provider_id)

        eligible_count = sum(1 for c in candidates if c.eligible)
        ineligible_count = sum(1 for c in candidates if not c.eligible)
        total_count = len(candidates)
        others = eligible_count - 1

        # Build the selection reason phrase
        reason_phrases = {
            "policy_pin": f"pinned by policy",
            "policy_preference_match": f"matched first preference in the policy preference list",
            "policy_single_candidate": f"was the only eligible candidate after policy filtering",
            "routing_with_policy_filters": f"won on composite score after policy filtering",
            None: f"selected by default routing",
        }
        reason_phrase = reason_phrases.get(winner_reason, f"selected ({winner_reason})")

        parts = [f"{winner_name} ({winner_provider_id}) {reason_phrase}"]

        if others > 0:
            parts.append(f"over {others} other eligible candidate{'s' if others > 1 else ''}")

        if ineligible_count > 0:
            # Describe why providers were excluded
            denied = [c for c in candidates if not c.eligible and c.ineligibility_reason == "denied_by_policy"]
            not_allowed = [c for c in candidates if not c.eligible and c.ineligibility_reason == "not_in_allow_only"]

            exclusions = []
            if denied:
                names = [c.provider_name or c.provider_id for c in denied]
                exclusions.append(f"{', '.join(names)} excluded by deny list")
            if not_allowed:
                names = [c.provider_name or c.provider_id for c in not_allowed]
                exclusions.append(f"{', '.join(names)} excluded by allow_only filter")

            if exclusions:
                parts.append(". " + "; ".join(exclusions))

        # Add leading factor for the winner
        winner_candidate = next(
            (c for c in candidates if c.provider_id == winner_provider_id and c.eligible),
            None,
        )
        if winner_candidate and winner_candidate.factors:
            top_factor = max(
                winner_candidate.factors,
                key=lambda f: f.weighted_contribution,
            )
            if top_factor.raw_value is not None:
                parts.append(
                    f". Leading factor: {top_factor.name} "
                    f"(contributed {top_factor.weighted_contribution:.3f} to composite score)"
                )

        return ". ".join(p.lstrip(". ") for p in parts if p.strip(". ")) + "."

    async def persist_explanation(self, explanation: RouteExplanation) -> bool:
        """Persist an explanation to the database.

        Returns True on success, False on failure (never raises).
        """
        try:
            row = {
                "explanation_id": explanation.explanation_id,
                "receipt_id": explanation.receipt_id,
                "capability_id": explanation.capability_id,
                "created_at": explanation.created_at,
                "winner_provider_id": explanation.winner_provider_id,
                "winner_composite_score": (
                    round(explanation.winner_composite_score, 6)
                    if explanation.winner_composite_score is not None
                    else None
                ),
                "winner_reason": explanation.winner_reason,
                "candidates_json": json.dumps(
                    explanation.to_dict()["candidates"],
                    separators=(",", ":"),
                    default=str,
                ),
                "human_summary": explanation.human_summary,
                "evaluation_ms": explanation.evaluation_ms,
            }
            await supabase_insert("route_explanations", row)
            logger.info(
                "route_explanation_persisted explanation_id=%s receipt_id=%s winner=%s",
                explanation.explanation_id,
                explanation.receipt_id,
                explanation.winner_provider_id,
            )
            return True
        except Exception:
            logger.exception(
                "route_explanation_persist_failed explanation_id=%s",
                explanation.explanation_id,
            )
            return False

    async def get_explanation_by_receipt(self, receipt_id: str) -> dict[str, Any] | None:
        """Fetch an explanation by its linked receipt ID."""
        from urllib.parse import quote

        rows = await supabase_fetch(
            f"route_explanations?receipt_id=eq.{quote(receipt_id)}&limit=1"
        )
        if not rows:
            return None
        row = rows[0]
        # Deserialize candidates_json back to list
        candidates_json = row.get("candidates_json")
        if isinstance(candidates_json, str):
            try:
                row["candidates"] = json.loads(candidates_json)
            except (json.JSONDecodeError, TypeError):
                row["candidates"] = []
        elif isinstance(candidates_json, list):
            row["candidates"] = candidates_json
        else:
            row["candidates"] = []
        return row

    async def get_explanation_by_id(self, explanation_id: str) -> dict[str, Any] | None:
        """Fetch an explanation by its ID."""
        from urllib.parse import quote

        rows = await supabase_fetch(
            f"route_explanations?explanation_id=eq.{quote(explanation_id)}&limit=1"
        )
        if not rows:
            return None
        row = rows[0]
        candidates_json = row.get("candidates_json")
        if isinstance(candidates_json, str):
            try:
                row["candidates"] = json.loads(candidates_json)
            except (json.JSONDecodeError, TypeError):
                row["candidates"] = []
        elif isinstance(candidates_json, list):
            row["candidates"] = candidates_json
        else:
            row["candidates"] = []
        return row


# Module-level singleton
_explanation_engine: RouteExplanationEngine | None = None


def get_explanation_engine() -> RouteExplanationEngine:
    """Get or create the route explanation engine singleton."""
    global _explanation_engine
    if _explanation_engine is None:
        _explanation_engine = RouteExplanationEngine()
    return _explanation_engine
