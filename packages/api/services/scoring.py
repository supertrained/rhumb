"""AN score computation, confidence calibration, and explanation generation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx

from config import settings
from db.repository import ScoreRepository, StoredScore

DIMENSION_WEIGHTS: dict[str, float] = {
    "I1": 0.10,
    "I2": 0.08,
    "I3": 0.10,
    "I4": 0.06,
    "I5": 0.05,
    "I6": 0.04,
    "I7": 0.05,
    "F1": 0.08,
    "F2": 0.07,
    "F3": 0.06,
    "F4": 0.06,
    "F5": 0.05,
    "F6": 0.05,
    "F7": 0.05,
    "O1": 0.04,
    "O2": 0.03,
    "O3": 0.03,
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
        self, dimensions: dict[str, float | None]
    ) -> tuple[dict[str, float], dict[str, float]]:
        applicable = {
            key: DIMENSION_WEIGHTS[key]
            for key, value in dimensions.items()
            if key in DIMENSION_WEIGHTS and value is not None
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

    def _confidence_from_probe_latency(self, latency_distribution_ms: dict[str, int] | None) -> float:
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

    def _category_scores(self, dimensions: dict[str, float | None]) -> dict[str, float]:
        category_scores: dict[str, float] = {}

        for category, category_dims in CATEGORY_DIMENSIONS.items():
            applicable = [dim for dim in category_dims if dimensions.get(dim) is not None]
            if not applicable:
                category_scores[category] = 0.0
                continue

            raw_weight = sum(DIMENSION_WEIGHTS[dim] for dim in applicable)
            weighted_score = sum(
                float(dimensions[dim] or 0.0) * DIMENSION_WEIGHTS[dim] for dim in applicable
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

    def build_dimension_snapshot(self, dimensions: dict[str, float | None]) -> dict[str, Any]:
        """Build normalized score snapshot returned by API and persisted in DB."""
        applicable_weights, normalized_weights = self._normalized_dimension_weights(dimensions)
        return {
            "dimensions": {
                key: value for key, value in dimensions.items() if key in DIMENSION_WEIGHTS
            },
            "raw_weights": applicable_weights,
            "normalized_weights": normalized_weights,
            "category_scores": self._category_scores(dimensions),
            "tier_labels": TIER_LABELS,
        }

    async def score_service(
        self,
        service_slug: str,
        dimensions: dict[str, float | None],
        evidence: EvidenceInput,
    ) -> ANScoreResult:
        """Calculate AN score bundle for a service."""
        raw_score = self._calculate_composite_raw(dimensions)
        rounded_score = round(raw_score, 1)
        confidence = self.calculate_confidence(evidence)
        tier = self.assign_tier(raw_score)
        explanation = await self.generate_explanation(service_slug, rounded_score, dimensions)
        snapshot = self.build_dimension_snapshot(dimensions)

        return ANScoreResult(
            service_slug=service_slug,
            score=rounded_score,
            score_raw=raw_score,
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
