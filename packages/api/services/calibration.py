"""v0.2 calibration fixtures for 20-service regression coverage."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class V02CalibrationCase:
    """Single service fixture for v0.2 calibration verification."""

    service_slug: str
    execution_score: float
    access_readiness_score: float
    expected_v02_rank: int
    expected_execution_rank: int

    @property
    def expected_aggregate_raw(self) -> float:
        return round((self.execution_score * 0.70) + (self.access_readiness_score * 0.30), 2)

    @property
    def expected_aggregate_score(self) -> float:
        return round(self.expected_aggregate_raw, 1)


V02_CALIBRATION_CASES: tuple[V02CalibrationCase, ...] = (
    V02CalibrationCase("stripe", 8.9, 6.59, expected_v02_rank=1, expected_execution_rank=1),
    V02CalibrationCase("resend", 8.6, 6.83, expected_v02_rank=2, expected_execution_rank=2),
    V02CalibrationCase("supabase", 8.1, 7.55, expected_v02_rank=3, expected_execution_rank=6),
    V02CalibrationCase("linear", 8.4, 6.74, expected_v02_rank=4, expected_execution_rank=3),
    V02CalibrationCase(
        "cloudflare-workers",
        8.3,
        6.74,
        expected_v02_rank=5,
        expected_execution_rank=4,
    ),
    V02CalibrationCase("anthropic", 8.1, 7.02, expected_v02_rank=6, expected_execution_rank=5),
    V02CalibrationCase("openai", 7.9, 7.33, expected_v02_rank=7, expected_execution_rank=10),
    V02CalibrationCase("cal-com", 8.0, 7.05, expected_v02_rank=8, expected_execution_rank=9),
    V02CalibrationCase("github", 8.0, 6.32, expected_v02_rank=9, expected_execution_rank=8),
    V02CalibrationCase("vercel", 7.8, 6.74, expected_v02_rank=10, expected_execution_rank=11),
    V02CalibrationCase("postmark", 8.1, 5.71, expected_v02_rank=11, expected_execution_rank=7),
    V02CalibrationCase("hunter", 7.5, 6.38, expected_v02_rank=12, expected_execution_rank=13),
    V02CalibrationCase("twilio", 7.6, 5.61, expected_v02_rank=13, expected_execution_rank=12),
    V02CalibrationCase("sendgrid", 7.4, 5.31, expected_v02_rank=14, expected_execution_rank=14),
    V02CalibrationCase("slack", 7.2, 5.10, expected_v02_rank=15, expected_execution_rank=15),
    V02CalibrationCase("airtable", 6.9, 5.79, expected_v02_rank=16, expected_execution_rank=16),
    V02CalibrationCase("notion", 6.7, 5.48, expected_v02_rank=17, expected_execution_rank=17),
    V02CalibrationCase(
        "peopledatalabs",
        6.6,
        4.79,
        expected_v02_rank=18,
        expected_execution_rank=18,
    ),
    V02CalibrationCase("apollo", 6.3, 4.41, expected_v02_rank=19, expected_execution_rank=19),
    V02CalibrationCase("hubspot", 5.4, 3.49, expected_v02_rank=20, expected_execution_rank=20),
)
