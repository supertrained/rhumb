"""Tests for schema change detector (Round 13 Module 2)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.schema_change_detector import SchemaChangeDetector  # noqa: E402
from services.schema_fingerprint import fingerprint_response  # noqa: E402


class TestSchemaChangeDetector:
    """Schema drift detector behavior and severity mapping."""

    def test_no_changes_for_identical_response(self) -> None:
        detector = SchemaChangeDetector()
        fp = fingerprint_response({"id": "cus_123"})
        detector.detect_changes("stripe", "default:v1/customers", fp)
        result = detector.detect_changes("stripe", "default:v1/customers", fp)
        assert result.changes == tuple()

    def test_field_addition_non_breaking(self) -> None:
        detector = SchemaChangeDetector()
        detector.detect_changes("stripe", "default:v1/customers", fingerprint_response({"id": "1"}))
        result = detector.detect_changes(
            "stripe",
            "default:v1/customers",
            fingerprint_response({"id": "1", "email": "a@example.com"}),
        )
        assert any(change.change_type == "add" for change in result.changes)
        assert all(change.severity != "breaking" for change in result.changes)

    def test_field_removal_breaking(self) -> None:
        detector = SchemaChangeDetector()
        detector.detect_changes(
            "stripe",
            "default:v1/customers",
            fingerprint_response({"id": "1", "email": "a@example.com"}),
        )
        result = detector.detect_changes("stripe", "default:v1/customers", fingerprint_response({"id": "1"}))
        assert any(change.change_type == "remove" and change.severity == "breaking" for change in result.changes)

    def test_type_change_breaking(self) -> None:
        detector = SchemaChangeDetector()
        detector.detect_changes("stripe", "default:v1/payment-intents", fingerprint_response({"amount": 1000}))
        result = detector.detect_changes(
            "stripe",
            "default:v1/payment-intents",
            fingerprint_response({"amount": "1000"}),
        )
        assert any(change.change_type == "type_change" and change.severity == "breaking" for change in result.changes)

    def test_multiple_changes_detected_and_classified(self) -> None:
        detector = SchemaChangeDetector()
        detector.detect_changes(
            "stripe",
            "default:v1/charges",
            fingerprint_response({"id": "1", "amount": 10, "meta": {"mode": "live"}}),
        )
        result = detector.detect_changes(
            "stripe",
            "default:v1/charges",
            fingerprint_response({"id": "1", "total": "10", "meta": [{"mode": "live"}], "new_field": True}),
        )
        change_types = {change.change_type for change in result.changes}
        assert "remove" in change_types
        assert "add" in change_types
        assert "nesting_change" in change_types or "cardinality_change" in change_types

    def test_empty_response_handled_gracefully(self) -> None:
        detector = SchemaChangeDetector()
        first = detector.detect_changes("stripe", "default:v1/empty", fingerprint_response({}))
        second = detector.detect_changes("stripe", "default:v1/empty", fingerprint_response({}))
        assert "baseline_created" in first.warnings
        assert second.changes == tuple()

    def test_breaking_and_advisory_surface_together(self) -> None:
        detector = SchemaChangeDetector()
        detector.detect_changes(
            "stripe",
            "default:v1/invoices",
            fingerprint_response({"customer_name": "A", "email": "a@x.com"}),
        )
        result = detector.detect_changes(
            "stripe",
            "default:v1/invoices",
            fingerprint_response({"customername": "A"}),
        )
        severities = {change.severity for change in result.changes}
        assert "breaking" in severities
        assert "advisory" in severities

    def test_baseline_update_flow(self) -> None:
        detector = SchemaChangeDetector()
        fp_a = fingerprint_response({"id": "1"})
        fp_b = fingerprint_response({"id": "1", "email": "a@example.com"})
        detector.update_baseline("stripe", "default:v1/customers", fp_a)
        assert detector.get_latest_fingerprint("stripe", "default:v1/customers") is not None
        detector.update_baseline("stripe", "default:v1/customers", fp_b)
        latest = detector.get_latest_fingerprint("stripe", "default:v1/customers")
        assert latest is not None
        assert latest.fingerprint_hash == fp_b.fingerprint_hash

    def test_stale_baseline_warning(self) -> None:
        detector = SchemaChangeDetector()
        detector.detect_changes("stripe", "default:v1/stale", fingerprint_response({"id": "1"}))
        detector.age_baseline_for_test("stripe", "default:v1/stale", days=8)
        result = detector.detect_changes("stripe", "default:v1/stale", fingerprint_response({"id": "1", "new": 1}))
        assert "baseline_stale" in result.warnings

    def test_non_json_response_graceful_fallback(self) -> None:
        detector = SchemaChangeDetector()
        html_fp = fingerprint_response("<html><body>error</body></html>")
        detector.detect_changes("stripe", "default:v1/non-json", html_fp, status_code=500)
        result = detector.detect_changes(
            "stripe",
            "default:v1/non-json",
            fingerprint_response("<html><body>error2</body></html>"),
            status_code=500,
        )
        assert result.changes == tuple()

    def test_rate_limit_response_not_schema_drift(self) -> None:
        detector = SchemaChangeDetector()
        result = detector.detect_changes(
            "stripe",
            "default:v1/customers",
            fingerprint_response({"error": "rate_limited"}),
            status_code=429,
        )
        assert result.changes == tuple()
        assert "rate_limited_response_skipped" in result.warnings

    def test_error_schema_separate_from_success_schema(self) -> None:
        detector = SchemaChangeDetector()
        detector.detect_changes(
            "stripe",
            "default:v1/customers",
            fingerprint_response({"id": "cus_1", "email": "a@example.com"}),
            status_code=200,
        )
        detector.detect_changes(
            "stripe",
            "default:v1/customers",
            fingerprint_response({"error": {"message": "boom"}}),
            status_code=500,
        )
        success_fp = detector.get_latest_fingerprint(
            "stripe",
            "default:v1/customers",
            status_code=200,
        )
        error_fp = detector.get_latest_fingerprint(
            "stripe",
            "default:v1/customers",
            status_code=500,
        )
        assert success_fp is not None and error_fp is not None
        assert success_fp.fingerprint_hash != error_fp.fingerprint_hash
