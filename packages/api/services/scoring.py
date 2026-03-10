"""AN score computation, confidence calibration, and explanation generation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from config import settings
from db.repository import ScoreRepository, StoredScore

# Execution dimensions keep legacy v0.2 relative shape (sum = 1.0) and are now
# blended into aggregate scoring with a 45% axis weight.
EXECUTION_DIMENSION_WEIGHTS: dict[str, float] = {
    "I1": 0.09166666666666667,
    "I2": 0.07333333333333333,
    "I3": 0.09166666666666667,
    "I4": 0.055,
    "I5": 0.04583333333333334,
    "I6": 0.03666666666666667,
    "I7": 0.04583333333333334,
    "F1": 0.0761904761904762,
    "F2": 0.06666666666666667,
    "F3": 0.05714285714285715,
    "F4": 0.05714285714285715,
    "F5": 0.04761904761904762,
    "F6": 0.04761904761904762,
    "F7": 0.04761904761904762,
    "O1": 0.07,
    "O2": 0.04,
    "O3": 0.05,
}

ACCESS_DIMENSION_WEIGHTS: dict[str, float] = {
    "A1": 0.24,
    "A2": 0.20,
    "A3": 0.18,
    "A4": 0.14,
    "A5": 0.14,
    "A6": 0.10,
}

# Aggregate axis weights for v0.3.
AXIS_WEIGHTS: dict[str, float] = {
    "execution": 0.45,
    "access": 0.40,
    "autonomy": 0.15,
}

# New autonomy dimensions (15% total).
AUTONOMY_DIMENSION_WEIGHTS: dict[str, float] = {
    "P1": 0.06,
    "G1": 0.05,
    "W1": 0.04,
}

# Effective aggregate weights by dimension (sum = 1.0).
DIMENSION_WEIGHTS: dict[str, float] = {
    **{key: weight * AXIS_WEIGHTS["execution"] for key, weight in EXECUTION_DIMENSION_WEIGHTS.items()},
    **{key: weight * AXIS_WEIGHTS["access"] for key, weight in ACCESS_DIMENSION_WEIGHTS.items()},
    **AUTONOMY_DIMENSION_WEIGHTS,
}

AUTONOMY_DIMENSION_NAME_MAP: dict[str, str] = {
    "P1": "payment_autonomy",
    "G1": "governance_readiness",
    "W1": "web_accessibility",
}

AN_SCORE_VERSION = "0.3"


@lru_cache(maxsize=1)
def load_autonomy_score_artifact() -> dict[str, dict[str, Any]]:
    """Load autonomy reference scores from artifacts/autonomy-scores.json."""
    artifact_path = Path(__file__).resolve().parents[3] / "artifacts" / "autonomy-scores.json"
    if not artifact_path.exists():
        return {}

    try:
        with artifact_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}

    raw_scores = payload.get("scores")
    if not isinstance(raw_scores, dict):
        return {}

    return {
        str(service_slug): value
        for service_slug, value in raw_scores.items()
        if isinstance(value, dict)
    }

CATEGORY_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "infrastructure": ("I1", "I2", "I3", "I4", "I5", "I6", "I7"),
    "interface": ("F1", "F2", "F3", "F4", "F5", "F6", "F7"),
    "operational": ("O1", "O2", "O3"),
}

DIMENSION_SUMMARIES: dict[str, tuple[str, str]] = {
    "I1": ("availability stays high", "availability gaps interrupt autonomous runs"),
    "I2": ("latency is predictable", "tail latency forces agents to hold state"),
    "I3": ("schema changes are stable", "schema churn breaks prompts and parsers"),
    "I4": ("rate limits are explicit", "rate limits are opaque and hard to recover from"),
    "I5": ("concurrency is handled cleanly", "concurrent calls degrade unpredictably"),
    "I6": ("cold starts stay fast", "cold starts add avoidable wait time"),
    "I7": ("degradation is graceful", "load spikes can trigger hard failures"),
    "F1": ("API parity is strong", "API parity gaps force UI-only workarounds"),
    "F2": ("errors are machine-readable", "error ergonomics slow automatic recovery"),
    "F3": (
        "responses are consistently structured",
        "response structures are inconsistent for automation",
    ),
    "F4": ("auth is straightforward", "auth flow friction interrupts agent autonomy"),
    "F5": (
        "idempotency supports safe retries",
        "weak idempotency increases duplicate-risk on retries",
    ),
    "F6": ("docs are integration-ready", "docs increase integration overhead for agents"),
    "F7": ("integration context cost is low", "high token overhead raises integration cost"),
    "O1": (
        "state handling is deterministic",
        "state leakage returns stale or inconsistent results",
    ),
    "O2": ("versioning is predictable", "versioning behavior creates migration risk"),
    "O3": ("webhooks deliver reliably", "webhook reliability can block event-driven agents"),
}

TIER_LABELS: dict[str, str] = {
    "L1": "Emerging",
    "L2": "Developing",
    "L3": "Ready",
    "L4": "Native",
}


@dataclass(slots=True)
class EvidenceInput:
    """Evidence metadata used to compute confidence."""

    evidence_count: int
    freshness: str
    probe_types: list[str]
    production_telemetry: bool = False
    probe_freshness: str | None = None
    probe_latency_distribution_ms: dict[str, int] | None = None


@dataclass(slots=True)
class ANScoreResult:
    """Computed AN score payload."""

    service_slug: str
    score: float
    score_raw: float
    execution_score: float
    access_readiness_score: float | None
    autonomy_score: float | None
    aggregate_recommendation_score: float
    an_score_version: str
    confidence: float
    tier: str
    explanation: str
    dimension_snapshot: dict[str, Any]
    calculated_at: datetime


class ScoringService:
    """Service object that calculates AN scores and persists them."""

    def __init__(self, repository: ScoreRepository | None = None) -> None:
        self._repository = repository

    def _normalized_dimension_weights(
        self,
        dimensions: dict[str, float | None],
        weight_map: dict[str, float] | None = None,
    ) -> tuple[dict[str, float], dict[str, float]]:
        selected_weights = weight_map or EXECUTION_DIMENSION_WEIGHTS
        applicable = {
            key: selected_weights[key]
            for key, value in dimensions.items()
            if key in selected_weights and value is not None
        }
        total_weight = sum(applicable.values())
        if total_weight <= 0:
            return {}, {}
        normalized = {key: weight / total_weight for key, weight in applicable.items()}
        return applicable, normalized

    def calculate_composite(self, dimensions: dict[str, float | None]) -> float:
        """Calculate weighted AN composite (0.0-10.0), redistributing N/A weight."""
        _, normalized = self._normalized_dimension_weights(dimensions)
        if not normalized:
            return 0.0

        composite = sum(
            float(dimensions[dim] or 0.0) * weight for dim, weight in normalized.items()
        )
        return round(composite, 1)

    def _calculate_composite_raw(self, dimensions: dict[str, float | None]) -> float:
        _, normalized = self._normalized_dimension_weights(dimensions)
        if not normalized:
            return 0.0
        return sum(float(dimensions[dim] or 0.0) * weight for dim, weight in normalized.items())

    def calculate_access_readiness(
        self, access_dimensions: dict[str, float | None] | None
    ) -> float | None:
        """Calculate weighted Access Readiness score (0.0-10.0) when access dimensions exist."""
        raw = self._calculate_access_readiness_raw(access_dimensions)
        if raw is None:
            return None
        return round(raw, 1)

    def _calculate_access_readiness_raw(
        self, access_dimensions: dict[str, float | None] | None
    ) -> float | None:
        if not access_dimensions:
            return None

        _, normalized = self._normalized_dimension_weights(
            access_dimensions,
            weight_map=ACCESS_DIMENSION_WEIGHTS,
        )
        if not normalized:
            return None

        return sum(
            float(access_dimensions[dim] or 0.0) * weight for dim, weight in normalized.items()
        )

    def _extract_service_slug(self, service_profile: dict[str, Any] | str) -> str:
        if isinstance(service_profile, str):
            return service_profile.strip().lower()

        for key in ("slug", "service_slug", "service"):
            value = service_profile.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()

        return ""

    def _autonomy_reference(self, service_slug: str, dimension: str) -> float | None:
        if not service_slug:
            return None

        service_scores = load_autonomy_score_artifact().get(service_slug)
        if not service_scores:
            return None

        value = service_scores.get(dimension)
        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _autonomy_rationale(self, dimension: str, score: float) -> str:
        if dimension == "P1":
            if score >= 9:
                return "x402 / API-native payments"
            if score >= 7:
                return "automated card billing"
            if score >= 5:
                return "semi-automated payment flow"
            if score >= 2:
                return "human-gated billing path"
            return "manual payment required"

        if dimension == "G1":
            if score >= 9:
                return "RBAC + audit logs"
            if score >= 7:
                return "strong access controls"
            if score >= 5:
                return "basic governance controls"
            if score >= 2:
                return "limited governance coverage"
            return "no governance primitives"

        if score >= 8:
            return "AAG AA/AAA structure"
        if score >= 6:
            return "AAG AA navigable UI"
        if score >= 4:
            return "AAG A parseable UI"
        if score >= 2:
            return "limited accessibility signals"
        return "agent-hostile web UI"

    def calculate_payment_autonomy(
        self, service_profile: dict[str, Any] | str
    ) -> tuple[float, str, float]:
        """Return P1 payment autonomy score tuple (score, rationale, confidence)."""
        service_slug = self._extract_service_slug(service_profile)
        score = self._autonomy_reference(service_slug, "P1")
        if score is None:
            return (0.0, "manual payment required", 0.35)
        return (score, self._autonomy_rationale("P1", score), 0.9)

    def calculate_governance_readiness(
        self, service_profile: dict[str, Any] | str
    ) -> tuple[float, str, float]:
        """Return G1 governance readiness tuple (score, rationale, confidence)."""
        service_slug = self._extract_service_slug(service_profile)
        score = self._autonomy_reference(service_slug, "G1")
        if score is None:
            return (0.0, "no governance primitives", 0.35)
        return (score, self._autonomy_rationale("G1", score), 0.9)

    def calculate_web_accessibility(
        self, service_profile: dict[str, Any] | str
    ) -> tuple[float, str, float]:
        """Return W1 web accessibility tuple (score, rationale, confidence)."""
        service_slug = self._extract_service_slug(service_profile)
        score = self._autonomy_reference(service_slug, "W1")
        if score is None:
            return (0.0, "agent-hostile web UI", 0.35)
        return (score, self._autonomy_rationale("W1", score), 0.9)

    def _calculate_autonomy_dimensions(
        self,
        service_slug: str,
        autonomy_dimensions: dict[str, float | None] | None = None,
    ) -> tuple[dict[str, float], dict[str, str], dict[str, float]]:
        computed_scores: dict[str, float] = {}
        rationales: dict[str, str] = {}
        confidences: dict[str, float] = {}

        prefilled = autonomy_dimensions or {}
        for dimension in AUTONOMY_DIMENSION_WEIGHTS:
            candidate = prefilled.get(dimension)
            if candidate is not None:
                score = float(candidate)
                computed_scores[dimension] = score
                rationales[dimension] = self._autonomy_rationale(dimension, score)
                confidences[dimension] = 0.7
                continue

            calculator_map = {
                "P1": self.calculate_payment_autonomy,
                "G1": self.calculate_governance_readiness,
                "W1": self.calculate_web_accessibility,
            }
            score, rationale, confidence = calculator_map[dimension](service_slug)
            computed_scores[dimension] = float(score)
            rationales[dimension] = rationale
            confidences[dimension] = float(confidence)

        return computed_scores, rationales, confidences

    def _calculate_autonomy_raw(
        self,
        service_slug: str,
        autonomy_dimensions: dict[str, float | None] | None = None,
    ) -> tuple[float | None, dict[str, float], dict[str, str], dict[str, float], float | None]:
        scores, rationales, confidences = self._calculate_autonomy_dimensions(
            service_slug,
            autonomy_dimensions=autonomy_dimensions,
        )
        if not scores:
            return None, {}, {}, {}, None

        _, normalized = self._normalized_dimension_weights(
            {key: value for key, value in scores.items()},
            weight_map=AUTONOMY_DIMENSION_WEIGHTS,
        )
        if not normalized:
            return None, {}, {}, {}, None

        autonomy_raw = sum(scores[dimension] * weight for dimension, weight in normalized.items())
        autonomy_confidence = sum(
            confidences.get(dimension, 0.5) * weight for dimension, weight in normalized.items()
        )

        return autonomy_raw, scores, rationales, confidences, autonomy_confidence

    def calculate_aggregate_recommendation(
        self,
        execution_score_raw: float,
        access_readiness_score_raw: float | None,
        autonomy_score_raw: float | None,
    ) -> float:
        """Calculate aggregate recommendation score using v0.3 three-axis weighting.

        Formula: (execution × 0.45) + (access × 0.40) + (autonomy × 0.15)
        Missing axes are re-normalized across available weights.
        """
        axes = {
            "execution": execution_score_raw,
            "access": access_readiness_score_raw,
            "autonomy": autonomy_score_raw,
        }
        available = {
            axis: value
            for axis, value in axes.items()
            if value is not None and axis in AXIS_WEIGHTS
        }
        if not available:
            return 0.0

        available_weight_total = sum(AXIS_WEIGHTS[axis] for axis in available)
        if available_weight_total <= 0:
            return 0.0

        aggregate = sum(
            float(value) * (AXIS_WEIGHTS[axis] / available_weight_total)
            for axis, value in available.items()
        )
        return round(aggregate, 1)

    def _parse_freshness_hours(self, freshness: str) -> float:
        normalized = freshness.strip().lower()
        if not normalized:
            return 24.0

        if "just now" in normalized:
            return 0.0

        compact_match = re.search(r"(\d+(?:\.\d+)?)\s*([smhdw])\b", normalized)
        if compact_match:
            value = float(compact_match.group(1))
            unit = compact_match.group(2)
            multipliers = {"s": 1 / 3600, "m": 1 / 60, "h": 1, "d": 24, "w": 168}
            return value * multipliers[unit]

        verbose_match = re.search(r"(\d+(?:\.\d+)?)\s*(second|minute|hour|day|week)s?", normalized)
        if verbose_match:
            value = float(verbose_match.group(1))
            unit = verbose_match.group(2)
            multipliers = {
                "second": 1 / 3600,
                "minute": 1 / 60,
                "hour": 1,
                "day": 24,
                "week": 168,
            }
            return value * multipliers[unit]

        return 24.0

    def _confidence_from_count(self, evidence_count: int) -> float:
        count = max(evidence_count, 0)
        if count < 3:
            return 0.2 + (0.1 * count)
        if count >= 50:
            return 1.0
        return 0.5 + ((count - 3) / 47) * 0.5

    def _confidence_from_freshness(self, freshness_hours: float) -> float:
        if freshness_hours <= 1:
            return 1.0
        if freshness_hours <= 24:
            return 0.9
        if freshness_hours <= 72:
            return 0.7
        if freshness_hours <= 24 * 7:
            return 0.5
        if freshness_hours <= 24 * 30:
            return 0.3
        return 0.2

    def _confidence_from_diversity(
        self, probe_types: list[str], production_telemetry: bool = False
    ) -> float:
        unique_types = len({probe.strip().lower() for probe in probe_types if probe.strip()})
        if unique_types <= 0:
            score = 0.3
        elif unique_types == 1:
            score = 0.4
        elif unique_types == 2:
            score = 0.6
        elif unique_types == 3:
            score = 0.8
        else:
            score = 1.0

        if production_telemetry:
            score = min(1.0, score + 0.1)
        return score

    def _confidence_from_probe_freshness(self, probe_freshness: str | None) -> float:
        if not probe_freshness:
            return 0.5

        freshness_hours = self._parse_freshness_hours(probe_freshness)
        if freshness_hours <= 1:
            return 1.0
        if freshness_hours <= 6:
            return 0.9
        if freshness_hours <= 24:
            return 0.75
        if freshness_hours <= 72:
            return 0.55
        return 0.35

    def _confidence_from_probe_latency(
        self, latency_distribution_ms: dict[str, int] | None
    ) -> float:
        if not latency_distribution_ms:
            return 0.5

        p95 = latency_distribution_ms.get("p95")
        p99 = latency_distribution_ms.get("p99")
        if p95 is None:
            return 0.5

        if p95 <= 300 and (p99 is None or p99 <= 800):
            return 1.0
        if p95 <= 700 and (p99 is None or p99 <= 1500):
            return 0.8
        if p95 <= 1200:
            return 0.6
        if p95 <= 2500:
            return 0.4
        return 0.25

    def calculate_confidence(self, evidence: EvidenceInput) -> float:
        """Compute confidence (0.0-1.0) from evidence count/freshness/diversity + probe telemetry."""
        count_score = self._confidence_from_count(evidence.evidence_count)
        freshness_score = self._confidence_from_freshness(
            self._parse_freshness_hours(evidence.freshness)
        )
        diversity_score = self._confidence_from_diversity(
            evidence.probe_types, evidence.production_telemetry
        )
        probe_freshness_score = self._confidence_from_probe_freshness(evidence.probe_freshness)
        probe_latency_score = self._confidence_from_probe_latency(
            evidence.probe_latency_distribution_ms
        )

        confidence = (
            (0.40 * count_score)
            + (0.30 * freshness_score)
            + (0.15 * diversity_score)
            + (0.10 * probe_freshness_score)
            + (0.05 * probe_latency_score)
        )
        return round(max(0.0, min(1.0, confidence)), 2)

    def assign_tier(self, score: float) -> str:
        """Assign certification tier from exact score boundaries."""
        if score < 4.0:
            return "L1"
        if score < 6.0:
            return "L2"
        if score < 8.0:
            return "L3"
        return "L4"

    def apply_tier_guardrails(
        self,
        base_tier: str,
        execution_score: float,
        access_readiness_score: float | None,
    ) -> str:
        """Apply tier caps for weak execution/access readiness."""
        tier_order = {"L1": 1, "L2": 2, "L3": 3, "L4": 4}
        l2_cap_required = execution_score < 6.0 or (
            access_readiness_score is not None and access_readiness_score < 4.0
        )

        if not l2_cap_required:
            return base_tier

        if tier_order.get(base_tier, 1) > tier_order["L2"]:
            return "L2"
        return base_tier

    def _category_scores(self, dimensions: dict[str, float | None]) -> dict[str, float]:
        category_scores: dict[str, float] = {}

        for category, category_dims in CATEGORY_DIMENSIONS.items():
            applicable = [dim for dim in category_dims if dimensions.get(dim) is not None]
            if not applicable:
                category_scores[category] = 0.0
                continue

            raw_weight = sum(EXECUTION_DIMENSION_WEIGHTS[dim] for dim in applicable)
            weighted_score = sum(
                float(dimensions[dim] or 0.0) * EXECUTION_DIMENSION_WEIGHTS[dim]
                for dim in applicable
            )
            category_scores[category] = round(weighted_score / raw_weight, 1) if raw_weight else 0.0

        return category_scores

    def _limitation_dimension(self, dimensions: dict[str, float | None]) -> str:
        scored = {key: value for key, value in dimensions.items() if value is not None}
        if not scored:
            return "F6"
        return min(scored, key=lambda key: float(scored[key] or 0.0))

    def _positive_dimension(self, dimensions: dict[str, float | None]) -> str:
        scored = {key: value for key, value in dimensions.items() if value is not None}
        if not scored:
            return "I1"
        return max(scored, key=lambda key: float(scored[key] or 0.0))

    def _fallback_explanation(
        self, service_slug: str, score: float, dimensions: dict[str, float | None]
    ) -> str:
        service_name = service_slug.replace("-", " ").title()
        positive_dimension = self._positive_dimension(dimensions)
        limitation_dimension = self._limitation_dimension(dimensions)

        positive_text = DIMENSION_SUMMARIES[positive_dimension][0]
        limitation_text = DIMENSION_SUMMARIES[limitation_dimension][1]
        return (
            f"{service_name} scores {score:.1f} because {positive_text}, " f"but {limitation_text}."
        )

    def _normalize_explanation(self, text: str, fallback: str) -> str:
        candidate = " ".join(text.strip().split())
        if not candidate:
            candidate = fallback

        sentence_match = re.split(r"(?<=[.!?])\s+", candidate)
        first_sentence = sentence_match[0] if sentence_match else candidate
        if first_sentence and first_sentence[-1] not in ".!?":
            first_sentence = f"{first_sentence}."

        max_chars = max(40, settings.score_explanation_max_chars)
        if len(first_sentence) > max_chars:
            truncated = first_sentence[: max_chars - 1].rstrip(" ,;:-")
            if truncated and truncated[-1] not in ".!?":
                truncated = f"{truncated}."
            first_sentence = truncated

        if len(first_sentence) < 15:
            return fallback if len(fallback) <= max_chars else fallback[: max_chars - 1] + "."

        return first_sentence

    async def _generate_with_claude(
        self,
        service_slug: str,
        score: float,
        dimensions: dict[str, float | None],
    ) -> str | None:
        api_key = settings.anthropic_api_key
        if not api_key:
            return None

        fallback = self._fallback_explanation(service_slug, score, dimensions)
        prompt = (
            "Return exactly one sentence, max 150 characters, in this format: "
            "'[Service] scores [X.X] because [positive] but [limitation].' "
            "No markdown, no extra lines. "
            f"Service: {service_slug}. Score: {score:.1f}. "
            f"Strongest dimension: {self._positive_dimension(dimensions)}. "
            f"Weakest dimension: {self._limitation_dimension(dimensions)}."
        )

        payload = {
            "model": settings.anthropic_model,
            "max_tokens": 128,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{settings.anthropic_base_url.rstrip('/')}/v1/messages",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError:
            return None

        data = response.json()
        content = data.get("content", [])
        if not content or not isinstance(content, list):
            return None

        text_blocks = [entry.get("text", "") for entry in content if isinstance(entry, dict)]
        generated = " ".join(block for block in text_blocks if block).strip()
        if not generated:
            return None

        return self._normalize_explanation(generated, fallback)

    async def generate_explanation(
        self, service_slug: str, score: float, dimensions: dict[str, float | None]
    ) -> str:
        """Generate a contextual explanation sentence (Claude Sonnet + fallback)."""
        fallback = self._fallback_explanation(service_slug, score, dimensions)
        llm_generated = await self._generate_with_claude(service_slug, score, dimensions)
        if llm_generated:
            return llm_generated
        return self._normalize_explanation(fallback, fallback)

    def build_dimension_snapshot(
        self,
        dimensions: dict[str, float | None],
        execution_score: float,
        access_dimensions: dict[str, float | None] | None,
        access_readiness_score: float | None,
        autonomy_scores: dict[str, float],
        autonomy_rationales: dict[str, str],
        autonomy_confidences: dict[str, float],
        autonomy_score: float | None,
        autonomy_confidence: float | None,
        aggregate_recommendation_score: float,
    ) -> dict[str, Any]:
        """Build normalized score snapshot returned by API and persisted in DB."""
        applicable_weights, normalized_weights = self._normalized_dimension_weights(
            dimensions,
            weight_map=EXECUTION_DIMENSION_WEIGHTS,
        )
        access_raw_weights, access_normalized_weights = self._normalized_dimension_weights(
            access_dimensions or {},
            weight_map=ACCESS_DIMENSION_WEIGHTS,
        )
        autonomy_raw_weights, autonomy_normalized_weights = self._normalized_dimension_weights(
            {key: value for key, value in autonomy_scores.items()},
            weight_map=AUTONOMY_DIMENSION_WEIGHTS,
        )

        autonomy_dimension_payload = []
        for dimension in ("P1", "G1", "W1"):
            if dimension not in autonomy_scores:
                continue
            autonomy_dimension_payload.append(
                {
                    "code": dimension,
                    "name": AUTONOMY_DIMENSION_NAME_MAP[dimension],
                    "score": round(float(autonomy_scores[dimension]), 1),
                    "rationale": autonomy_rationales.get(dimension, ""),
                    "confidence": round(float(autonomy_confidences.get(dimension, 0.5)), 2),
                }
            )

        return {
            "dimensions": {
                key: value
                for key, value in dimensions.items()
                if key in EXECUTION_DIMENSION_WEIGHTS
            },
            "raw_weights": applicable_weights,
            "normalized_weights": normalized_weights,
            "category_scores": self._category_scores(dimensions),
            "tier_labels": TIER_LABELS,
            "access_dimensions": {
                key: value
                for key, value in (access_dimensions or {}).items()
                if key in ACCESS_DIMENSION_WEIGHTS
            },
            "access_raw_weights": access_raw_weights,
            "access_normalized_weights": access_normalized_weights,
            "autonomy_dimensions": autonomy_scores,
            "autonomy_raw_weights": autonomy_raw_weights,
            "autonomy_normalized_weights": autonomy_normalized_weights,
            "autonomy": {
                "avg": None if autonomy_score is None else round(autonomy_score, 1),
                "confidence": (
                    None if autonomy_confidence is None else round(float(autonomy_confidence), 2)
                ),
                "dimensions": autonomy_dimension_payload,
            },
            "score_breakdown": {
                "execution": execution_score,
                "access_readiness": access_readiness_score,
                "autonomy": autonomy_score,
                "aggregate_recommendation": aggregate_recommendation_score,
                "axis_weights": AXIS_WEIGHTS,
                "autonomy_dimension_weights": AUTONOMY_DIMENSION_WEIGHTS,
                "version": AN_SCORE_VERSION,
                "aggregate_aliases_score": False,
            },
        }

    async def score_service(
        self,
        service_slug: str,
        dimensions: dict[str, float | None],
        evidence: EvidenceInput,
        access_dimensions: dict[str, float | None] | None = None,
        autonomy_dimensions: dict[str, float | None] | None = None,
    ) -> ANScoreResult:
        """Calculate AN score bundle for a service."""
        execution_raw = self._calculate_composite_raw(dimensions)
        execution_score = round(execution_raw, 1)
        access_raw = self._calculate_access_readiness_raw(access_dimensions)
        access_readiness_score = round(access_raw, 1) if access_raw is not None else None

        (
            autonomy_raw,
            autonomy_scores,
            autonomy_rationales,
            autonomy_confidences,
            autonomy_confidence,
        ) = self._calculate_autonomy_raw(service_slug, autonomy_dimensions=autonomy_dimensions)
        autonomy_score = round(autonomy_raw, 1) if autonomy_raw is not None else None

        aggregate_recommendation_score = self.calculate_aggregate_recommendation(
            execution_raw,
            access_raw,
            autonomy_raw,
        )

        confidence = self.calculate_confidence(evidence)
        if autonomy_confidence is not None:
            confidence = round((confidence * 0.85) + (autonomy_confidence * 0.15), 2)

        base_tier = self.assign_tier(float(aggregate_recommendation_score))
        tier = self.apply_tier_guardrails(
            base_tier=base_tier,
            execution_score=execution_score,
            access_readiness_score=access_readiness_score,
        )
        explanation = await self.generate_explanation(service_slug, execution_score, dimensions)
        snapshot = self.build_dimension_snapshot(
            dimensions=dimensions,
            execution_score=execution_score,
            access_dimensions=access_dimensions,
            access_readiness_score=access_readiness_score,
            autonomy_scores=autonomy_scores,
            autonomy_rationales=autonomy_rationales,
            autonomy_confidences=autonomy_confidences,
            autonomy_score=autonomy_score,
            autonomy_confidence=autonomy_confidence,
            aggregate_recommendation_score=aggregate_recommendation_score,
        )

        return ANScoreResult(
            service_slug=service_slug,
            score=aggregate_recommendation_score,
            score_raw=float(aggregate_recommendation_score),
            execution_score=execution_score,
            access_readiness_score=access_readiness_score,
            autonomy_score=autonomy_score,
            aggregate_recommendation_score=aggregate_recommendation_score,
            an_score_version=AN_SCORE_VERSION,
            confidence=confidence,
            tier=tier,
            explanation=explanation,
            dimension_snapshot=snapshot,
            calculated_at=datetime.now(timezone.utc),
        )

    def save_score(self, service_slug: str, result: ANScoreResult) -> UUID | None:
        """Persist score in configured repository."""
        if self._repository is None:
            return None

        return self._repository.save_score(
            service_slug=service_slug,
            score=result.score,
            confidence=result.confidence,
            tier=result.tier,
            explanation=result.explanation,
            dimension_snapshot=result.dimension_snapshot,
        )

    def fetch_latest_score(self, service_slug: str) -> StoredScore | None:
        """Fetch latest stored score for a service."""
        if self._repository is None:
            return None
        return self._repository.fetch_latest_score(service_slug)

    def query_scores_by_range(
        self, min_score: float = 0.0, max_score: float = 10.0
    ) -> list[StoredScore]:
        """Query scores in a numeric range (e.g., L3+ services)."""
        if self._repository is None:
            return []
        return self._repository.query_by_score_range(min_score=min_score, max_score=max_score)
