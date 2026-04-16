"""Route Explanation Engine (WU-41.3).

Every routing decision produces a complete, queryable explanation per
Resolve Product Spec §2.3.  Explanations include:
- the winning provider and why it was chosen
- all candidates with composite scores and factor breakdowns
- policy checks applied
- a human-readable summary

Explanations are attached to v2 execution responses and queryable via
``GET /v2/explanations/{explanation_id}``.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote

from routes._supabase import supabase_fetch, supabase_insert
from services.service_slugs import canonicalize_service_slug, normalize_proxy_slug

logger = logging.getLogger(__name__)

# Factor weights (must sum to 1.0 across the 5 factors)
DEFAULT_WEIGHTS = {
    "an_score": 0.20,
    "availability": 0.30,
    "estimated_cost": 0.25,
    "latency": 0.15,
    "credential_mode": 0.10,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CandidateFactor:
    """A single scoring factor for a candidate provider."""

    name: str
    raw_value: float
    normalized_score: float
    weight: float

    @property
    def weighted_contribution(self) -> float:
        return round(self.normalized_score * self.weight, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.raw_value,
            "normalized_score": round(self.normalized_score, 4),
            "weight": self.weight,
            "weighted_contribution": self.weighted_contribution,
        }


@dataclass
class CandidateExplanation:
    """Explanation for a single candidate provider."""

    provider_id: str
    eligible: bool
    composite_score: float
    factors: dict[str, CandidateFactor] = field(default_factory=dict)
    policy_checks: dict[str, bool] = field(default_factory=dict)
    ineligible_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "provider_id": self.provider_id,
            "eligible": self.eligible,
            "composite_score": round(self.composite_score, 4),
            "factors": {k: v.to_dict() for k, v in self.factors.items()},
            "policy_checks": self.policy_checks,
        }
        if self.ineligible_reason:
            d["ineligible_reason"] = self.ineligible_reason
        return d


@dataclass
class RouteExplanation:
    """Complete route explanation for a single execution."""

    explanation_id: str
    capability_id: str
    winner_provider_id: str | None
    winner_composite_score: float | None
    selection_reason: str
    candidates: list[CandidateExplanation] = field(default_factory=list)
    human_summary: str = ""
    layer: int = 2
    strategy: str = "balanced"
    policy_active: bool = False
    created_at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "explanation_id": self.explanation_id,
            "capability_id": self.capability_id,
            "winner": {
                "provider_id": self.winner_provider_id,
                "composite_score": (
                    round(self.winner_composite_score, 4)
                    if self.winner_composite_score is not None
                    else None
                ),
                "selection_reason": self.selection_reason,
            },
            "candidates": [c.to_dict() for c in self.candidates],
            "human_summary": self.human_summary,
            "layer": self.layer,
            "strategy": self.strategy,
            "policy_active": self.policy_active,
        }

    def to_compact(self) -> dict[str, Any]:
        """Compact explanation for embedding in execution responses."""
        return {
            "explanation_id": self.explanation_id,
            "winner": self.winner_provider_id,
            "reason": self.selection_reason,
            "candidates_evaluated": len(self.candidates),
            "candidates_eligible": sum(1 for c in self.candidates if c.eligible),
            "human_summary": self.human_summary,
        }


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------

def _generate_explanation_id(capability_id: str, timestamp_ms: int) -> str:
    """Generate a deterministic explanation ID."""
    raw = f"{capability_id}:{timestamp_ms}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"rexp_{digest}"


# ---------------------------------------------------------------------------
# Explanation builder
# ---------------------------------------------------------------------------

def _normalize_slug(slug: str | None) -> str | None:
    if slug is None:
        return None
    cleaned = str(slug).strip().lower()
    if not cleaned:
        return None
    return normalize_proxy_slug(canonicalize_service_slug(cleaned))


def _normalize_slug_list(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        slug = _normalize_slug(value)
        if not slug or slug in seen:
            continue
        normalized.append(slug)
        seen.add(slug)
    return normalized


def build_explanation(
    *,
    capability_id: str,
    mappings: list[dict[str, Any]],
    scores_by_slug: dict[str, float],
    circuit_states: dict[str, str],
    selected_provider: str | None,
    strategy: str = "balanced",
    quality_floor: float = 6.0,
    max_cost_usd: float | None = None,
    policy_pin: str | None = None,
    policy_deny: list[str] | None = None,
    policy_allow_only: list[str] | None = None,
    layer: int = 2,
    weights: dict[str, float] | None = None,
) -> RouteExplanation:
    """Build a complete route explanation from routing inputs and result.

    This is called *after* the routing engine has selected a provider,
    so we can reconstruct the explanation from the same inputs.
    """
    w = weights or DEFAULT_WEIGHTS
    ts = int(time.time() * 1000)
    explanation_id = _generate_explanation_id(capability_id, ts)

    normalized_selected_provider = _normalize_slug(selected_provider) or selected_provider
    normalized_policy_pin = _normalize_slug(policy_pin)
    deny_set = set(_normalize_slug_list(policy_deny))
    allow_set = set(_normalize_slug_list(policy_allow_only))
    policy_active = bool(normalized_policy_pin or deny_set or allow_set)

    # Find max cost for normalization
    costs = [
        float(m.get("cost_per_call") or 0)
        for m in mappings
        if m.get("cost_per_call") is not None
    ]
    max_cost = max(costs) if costs else 1.0
    if max_cost == 0:
        max_cost = 1.0

    candidates: list[CandidateExplanation] = []
    winner_candidate: CandidateExplanation | None = None

    for m in mappings:
        slug = m.get("service_slug", "unknown")
        an_score = scores_by_slug.get(slug, 0.0)
        cost = float(m.get("cost_per_call") or 0)
        circuit = circuit_states.get(slug, "closed")

        # Policy checks
        checks: dict[str, bool] = {
            "pinned": normalized_policy_pin == slug if normalized_policy_pin else False,
            "denied": slug in deny_set,
            "cost_ceiling_ok": (
                cost <= max_cost_usd if max_cost_usd is not None else True
            ),
            "quality_floor_ok": an_score >= quality_floor,
            "circuit_healthy": circuit != "open",
            "allow_list_ok": (
                slug in allow_set if allow_set else True
            ),
        }

        # Determine eligibility
        ineligible_reason: str | None = None
        eligible = True

        if checks["denied"]:
            eligible = False
            ineligible_reason = "excluded_by_deny_list"
        elif allow_set and not checks["allow_list_ok"]:
            eligible = False
            ineligible_reason = "not_in_allow_list"
        elif not checks["circuit_healthy"]:
            eligible = False
            ineligible_reason = "circuit_open"
        elif not checks["quality_floor_ok"]:
            eligible = False
            ineligible_reason = "below_quality_floor"
        elif not checks["cost_ceiling_ok"]:
            eligible = False
            ineligible_reason = "exceeds_cost_ceiling"

        # Compute factors
        health = 1.0 if circuit == "closed" else (0.5 if circuit == "half_open" else 0.0)
        norm_score = min(an_score / 10.0, 1.0)
        norm_cost = 1.0 - (cost / max_cost) if max_cost > 0 else 1.0

        # Credential mode: prefer rhumb_managed
        cred_modes = m.get("credential_modes") or []
        cred_score = 1.0 if "rhumb_managed" in cred_modes else 0.5

        factors = {
            "an_score": CandidateFactor(
                name="an_score",
                raw_value=an_score,
                normalized_score=norm_score,
                weight=w.get("an_score", 0.20),
            ),
            "availability": CandidateFactor(
                name="availability",
                raw_value=health,
                normalized_score=health,
                weight=w.get("availability", 0.30),
            ),
            "estimated_cost": CandidateFactor(
                name="estimated_cost",
                raw_value=cost,
                normalized_score=norm_cost,
                weight=w.get("estimated_cost", 0.25),
            ),
            "latency": CandidateFactor(
                name="latency",
                raw_value=health,  # Using circuit health as latency proxy
                normalized_score=health,
                weight=w.get("latency", 0.15),
            ),
            "credential_mode": CandidateFactor(
                name="credential_mode",
                raw_value=cred_score,
                normalized_score=cred_score,
                weight=w.get("credential_mode", 0.10),
            ),
        }

        composite = sum(f.weighted_contribution for f in factors.values()) if eligible else 0.0

        candidate = CandidateExplanation(
            provider_id=slug,
            eligible=eligible,
            composite_score=composite,
            factors=factors,
            policy_checks=checks,
            ineligible_reason=ineligible_reason,
        )
        candidates.append(candidate)

        if slug == normalized_selected_provider:
            winner_candidate = candidate

    # Sort candidates: eligible first (by composite desc), then ineligible
    candidates.sort(key=lambda c: (-int(c.eligible), -c.composite_score))

    # Determine selection reason
    if normalized_policy_pin and normalized_selected_provider == normalized_policy_pin:
        selection_reason = "agent_pinned"
    elif len(candidates) == 1 and candidates[0].eligible:
        selection_reason = "only_eligible_provider"
    elif normalized_selected_provider and winner_candidate:
        selection_reason = "highest_composite_score_within_policy"
    elif normalized_selected_provider:
        selection_reason = "routing_engine_selected"
    else:
        selection_reason = "no_provider_available"

    # Build human summary
    human_summary = _build_human_summary(
        selected_provider=normalized_selected_provider,
        candidates=candidates,
        selection_reason=selection_reason,
        strategy=strategy,
        policy_pin=normalized_policy_pin,
        deny_set=deny_set,
    )

    return RouteExplanation(
        explanation_id=explanation_id,
        capability_id=capability_id,
        winner_provider_id=normalized_selected_provider,
        winner_composite_score=(
            winner_candidate.composite_score if winner_candidate else None
        ),
        selection_reason=selection_reason,
        candidates=candidates,
        human_summary=human_summary,
        layer=layer,
        strategy=strategy,
        policy_active=policy_active,
        created_at_ms=ts,
    )


def build_layer1_explanation(
    *,
    capability_id: str,
    provider_id: str,
) -> RouteExplanation:
    """Build a trivial Layer 1 explanation (agent pinned the provider)."""
    ts = int(time.time() * 1000)
    return RouteExplanation(
        explanation_id=_generate_explanation_id(capability_id, ts),
        capability_id=capability_id,
        winner_provider_id=provider_id,
        winner_composite_score=None,
        selection_reason="agent_pinned_layer1",
        candidates=[],
        human_summary=(
            f"{provider_id} selected directly by agent via Layer 1 (raw provider access). "
            f"No routing intelligence applied."
        ),
        layer=1,
        strategy="none",
        policy_active=False,
        created_at_ms=ts,
    )


# ---------------------------------------------------------------------------
# Human summary
# ---------------------------------------------------------------------------

def _build_human_summary(
    *,
    selected_provider: str | None,
    candidates: list[CandidateExplanation],
    selection_reason: str,
    strategy: str,
    policy_pin: str | None,
    deny_set: set[str],
) -> str:
    """Build a human-readable routing summary."""
    eligible = [c for c in candidates if c.eligible]
    ineligible = [c for c in candidates if not c.eligible]
    total = len(candidates)

    if not selected_provider:
        if total == 0:
            return "No providers available for this capability."
        reasons = set(c.ineligible_reason or "unknown" for c in ineligible)
        return (
            f"No eligible provider found among {total} candidate(s). "
            f"Exclusion reasons: {', '.join(reasons)}."
        )

    parts: list[str] = []

    if policy_pin:
        parts.append(f"{selected_provider} pinned by policy.")
    elif len(eligible) == 1:
        parts.append(f"{selected_provider} selected as the only eligible provider.")
    else:
        parts.append(
            f"{selected_provider} selected over {len(eligible) - 1} other eligible candidate(s)."
        )

    # Winning factors
    winner = next((c for c in candidates if c.provider_id == selected_provider), None)
    if winner and winner.factors:
        top_factors = sorted(
            winner.factors.values(),
            key=lambda f: -f.weighted_contribution,
        )[:2]
        factor_strs = [
            f"{f.name} ({f.weighted_contribution:.3f})"
            for f in top_factors
        ]
        parts.append(f"Strongest factors: {', '.join(factor_strs)}.")

    # Exclusions
    denied = [c for c in ineligible if c.ineligible_reason == "excluded_by_deny_list"]
    if denied:
        parts.append(
            f"{len(denied)} provider(s) excluded by deny list: "
            f"{', '.join(c.provider_id for c in denied)}."
        )

    circuit_open = [c for c in ineligible if c.ineligible_reason == "circuit_open"]
    if circuit_open:
        parts.append(
            f"{len(circuit_open)} provider(s) excluded (circuit open): "
            f"{', '.join(c.provider_id for c in circuit_open)}."
        )

    parts.append(f"Strategy: {strategy}.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# In-memory explanation store (for v2 query endpoint)
# ---------------------------------------------------------------------------

_explanation_store: dict[str, RouteExplanation] = {}
_MAX_STORED = 1000


def store_explanation(explanation: RouteExplanation) -> None:
    """Store an explanation for later retrieval. Bounded in-memory store."""
    if len(_explanation_store) >= _MAX_STORED:
        # Evict oldest entries (by timestamp)
        sorted_keys = sorted(
            _explanation_store.keys(),
            key=lambda k: _explanation_store[k].created_at_ms,
        )
        for k in sorted_keys[:_MAX_STORED // 2]:
            del _explanation_store[k]

    _explanation_store[explanation.explanation_id] = explanation


def get_explanation(explanation_id: str) -> RouteExplanation | None:
    """Retrieve a stored explanation by ID from the hot in-memory cache."""
    return _explanation_store.get(explanation_id)


def _row_to_explanation(row: dict[str, Any]) -> RouteExplanation:
    """Hydrate a RouteExplanation from a persisted route_explanations row."""
    created_at_ms = 0
    created_at = row.get("created_at")
    if isinstance(created_at, str):
        try:
            parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            created_at_ms = int(parsed.timestamp() * 1000)
        except ValueError:
            created_at_ms = 0

    candidates_raw = row.get("candidates_json") or []
    candidates: list[CandidateExplanation] = []
    if isinstance(candidates_raw, list):
        for candidate in candidates_raw:
            if not isinstance(candidate, dict):
                continue
            factor_objs: dict[str, CandidateFactor] = {}
            factors = candidate.get("factors") or {}
            if isinstance(factors, dict):
                for name, factor in factors.items():
                    if not isinstance(factor, dict):
                        continue
                    factor_objs[name] = CandidateFactor(
                        name=name,
                        raw_value=float(factor.get("value") or 0.0),
                        normalized_score=float(factor.get("normalized_score") or 0.0),
                        weight=float(factor.get("weight") or 0.0),
                    )
            candidates.append(
                CandidateExplanation(
                    provider_id=str(candidate.get("provider_id") or "unknown"),
                    eligible=bool(candidate.get("eligible", False)),
                    composite_score=float(candidate.get("composite_score") or 0.0),
                    factors=factor_objs,
                    policy_checks=(candidate.get("policy_checks") if isinstance(candidate.get("policy_checks"), dict) else {}),
                    ineligible_reason=candidate.get("ineligible_reason"),
                )
            )

    return RouteExplanation(
        explanation_id=str(row.get("explanation_id") or ""),
        capability_id=str(row.get("capability_id") or "unknown"),
        winner_provider_id=row.get("winner_provider_id"),
        winner_composite_score=(float(row["winner_composite_score"]) if row.get("winner_composite_score") is not None else None),
        selection_reason=str(row.get("winner_reason") or "persisted_route_explanation"),
        candidates=candidates,
        human_summary=str(row.get("human_summary") or ""),
        created_at_ms=created_at_ms,
    )


async def persist_explanation(
    explanation: RouteExplanation,
    *,
    receipt_id: str | None = None,
) -> bool:
    """Persist a route explanation so receipt/explanation reads survive restarts.

    The hot in-memory cache remains useful for immediate same-process reads, but
    the durable source of truth for read surfaces should be Supabase.
    """
    return await supabase_insert(
        "route_explanations",
        {
            "explanation_id": explanation.explanation_id,
            "receipt_id": receipt_id,
            "capability_id": explanation.capability_id,
            "winner_provider_id": explanation.winner_provider_id,
            "winner_composite_score": explanation.winner_composite_score,
            "winner_reason": explanation.selection_reason,
            "candidates_json": [candidate.to_dict() for candidate in explanation.candidates],
            "human_summary": explanation.human_summary,
        },
    )


async def get_persisted_explanation(explanation_id: str) -> RouteExplanation | None:
    """Retrieve a persisted explanation by explanation_id."""
    rows = await supabase_fetch(
        f"route_explanations?explanation_id=eq.{quote(explanation_id)}&limit=1"
    )
    if not rows:
        return None
    return _row_to_explanation(rows[0])


async def get_persisted_explanation_by_receipt(receipt_id: str) -> RouteExplanation | None:
    """Retrieve the latest persisted explanation linked to a receipt."""
    rows = await supabase_fetch(
        f"route_explanations?receipt_id=eq.{quote(receipt_id)}&order=created_at.desc&limit=1"
    )
    if not rows:
        return None
    return _row_to_explanation(rows[0])


def clear_explanation_store() -> None:
    """Clear the explanation store (for tests)."""
    _explanation_store.clear()
