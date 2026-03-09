"""Schema change detection and baseline tracking."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from services.schema_fingerprint import SchemaDiff, SchemaFingerprint, compare_schema_structures


@dataclass(frozen=True, slots=True)
class SchemaChange:
    """Single detected schema change."""

    change_type: str
    path: str
    severity: str
    old_type: str | None = None
    new_type: str | None = None
    detail: str | None = None
    similarity: float | None = None


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """Result of comparing a candidate fingerprint against baseline."""

    changes: tuple[SchemaChange, ...]
    warnings: tuple[str, ...]
    baseline_hash: str | None
    current_hash: str
    baseline_age_days: float | None


@dataclass(slots=True)
class BaselineEntry:
    """Stored baseline fingerprint metadata."""

    fingerprint: SchemaFingerprint
    fingerprint_hash: str
    captured_at: datetime


class SchemaChangeDetector:
    """Compares fingerprints and classifies schema drift severity."""

    def __init__(
        self,
        *,
        redis_client: Any = None,
        stale_days: int = 7,
    ) -> None:
        self._redis = redis_client
        self._stale_days = stale_days
        self._baselines: dict[str, BaselineEntry] = {}
        self._history: dict[str, list[SchemaChange]] = {}
        self._last_change_at: dict[str, datetime] = {}
        self._diff_cache: dict[tuple[str, str], tuple[SchemaChange, ...]] = {}

    @staticmethod
    def _status_bucket(status_code: int) -> str:
        if status_code == 429:
            return "rate_limited"
        if 200 <= status_code < 400:
            return "success"
        return "error"

    def _baseline_key(self, service: str, endpoint: str, status_code: int) -> str:
        bucket = self._status_bucket(status_code)
        clean_endpoint = endpoint.lstrip("/")
        return f"schema:baseline:{service}:{clean_endpoint}:{bucket}"

    def _history_key(self, service: str, endpoint: str, status_code: int = 200) -> str:
        bucket = self._status_bucket(status_code)
        clean_endpoint = endpoint.lstrip("/")
        return f"schema:history:{service}:{clean_endpoint}:{bucket}"

    def _service_history_key(self, service: str) -> str:
        return f"schema:service:{service}"

    def _set_baseline(self, key: str, fingerprint: SchemaFingerprint) -> None:
        now = datetime.now(tz=UTC)
        self._baselines[key] = BaselineEntry(
            fingerprint=fingerprint,
            fingerprint_hash=fingerprint.fingerprint_hash,
            captured_at=now,
        )

        if self._redis is None:
            return

        try:
            payload = {
                "fingerprint_hash": fingerprint.fingerprint_hash,
                "captured_at": now.isoformat(),
                "schema_tree": fingerprint.schema_tree,
            }
            self._redis.set(key, json.dumps(payload))
        except Exception:
            # Graceful degradation: in-memory baseline remains source of truth.
            return

    def _get_baseline(self, key: str) -> BaselineEntry | None:
        baseline = self._baselines.get(key)
        if baseline is not None:
            return baseline

        if self._redis is None:
            return None

        try:
            raw = self._redis.get(key)
        except Exception:
            return None

        if not raw:
            return None

        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)
            schema_tree = payload.get("schema_tree")
            fingerprint_hash = payload.get("fingerprint_hash")
            captured_at_raw = payload.get("captured_at")
            if not isinstance(schema_tree, dict) or not isinstance(fingerprint_hash, str):
                return None
            captured_at = datetime.fromisoformat(str(captured_at_raw))
            if captured_at.tzinfo is None:
                captured_at = captured_at.replace(tzinfo=UTC)

            fingerprint = SchemaFingerprint(
                schema_tree=schema_tree,
                fingerprint_hash=fingerprint_hash,
                field_paths=tuple(),
                max_depth=1,
                metadata=self._empty_metadata(),
            )
            baseline = BaselineEntry(
                fingerprint=fingerprint,
                fingerprint_hash=fingerprint_hash,
                captured_at=captured_at,
            )
            self._baselines[key] = baseline
            return baseline
        except Exception:
            return None

    @staticmethod
    def _empty_metadata() -> Any:
        from services.schema_fingerprint import SchemaMetadata

        return SchemaMetadata(
            status_code=0,
            latency_ms=0.0,
            content_type=None,
            cache_control=None,
        )

    def update_baseline(
        self,
        service: str,
        endpoint: str,
        fingerprint: SchemaFingerprint,
        *,
        status_code: int = 200,
    ) -> None:
        """Update baseline fingerprint for an endpoint."""
        key = self._baseline_key(service, endpoint, status_code)
        self._set_baseline(key, fingerprint)

    def classify_severity(
        self,
        change_type: str,
        *,
        old_type: str | None = None,
        new_type: str | None = None,
    ) -> str:
        """Classify change severity."""
        if change_type in {"remove", "type_change", "nesting_change", "cardinality_change"}:
            if change_type == "type_change" and {old_type, new_type} == {"null", "string"}:
                return "non_breaking"
            if change_type == "type_change" and {old_type, new_type} == {"null", "integer"}:
                return "non_breaking"
            if change_type == "type_change" and {old_type, new_type} == {"null", "number"}:
                return "non_breaking"
            if change_type == "type_change" and {old_type, new_type} == {"null", "boolean"}:
                return "non_breaking"
            return "breaking"

        if change_type in {"add", "optional_change"}:
            return "non_breaking"

        if change_type in {"rename", "naming_change"}:
            return "advisory"

        return "advisory"

    def alert_required(
        self,
        changes: tuple[SchemaChange, ...],
        *,
        include_non_breaking: bool = False,
    ) -> bool:
        """Decide if detected changes should trigger alerts."""
        if any(change.severity == "breaking" for change in changes):
            return True
        if include_non_breaking and any(change.severity == "non_breaking" for change in changes):
            return True
        return False

    def detect_changes(
        self,
        service: str,
        endpoint: str,
        current: SchemaFingerprint,
        *,
        status_code: int = 200,
    ) -> DetectionResult:
        """Compare current fingerprint with baseline for an endpoint."""
        if status_code == 429:
            return DetectionResult(
                changes=tuple(),
                warnings=("rate_limited_response_skipped",),
                baseline_hash=None,
                current_hash=current.fingerprint_hash,
                baseline_age_days=None,
            )

        key = self._baseline_key(service, endpoint, status_code)
        baseline = self._get_baseline(key)

        if baseline is None:
            self._set_baseline(key, current)
            return DetectionResult(
                changes=tuple(),
                warnings=("baseline_created",),
                baseline_hash=None,
                current_hash=current.fingerprint_hash,
                baseline_age_days=None,
            )

        baseline_age_days = (
            datetime.now(tz=UTC) - baseline.captured_at
        ).total_seconds() / 86400.0

        warnings: list[str] = []
        if baseline_age_days > float(self._stale_days):
            warnings.append("baseline_stale")

        if baseline.fingerprint_hash == current.fingerprint_hash:
            self._set_baseline(key, current)
            return DetectionResult(
                changes=tuple(),
                warnings=tuple(warnings),
                baseline_hash=baseline.fingerprint_hash,
                current_hash=current.fingerprint_hash,
                baseline_age_days=baseline_age_days,
            )

        cache_key = (baseline.fingerprint_hash, current.fingerprint_hash)
        cached = self._diff_cache.get(cache_key)
        if cached is not None:
            changes = cached
        else:
            diff = compare_schema_structures(baseline.fingerprint.schema_tree, current.schema_tree)
            changes = self._changes_from_diff(diff)
            self._diff_cache[cache_key] = changes

        self._record_history(service, endpoint, changes, status_code)
        self._set_baseline(key, current)

        return DetectionResult(
            changes=changes,
            warnings=tuple(warnings),
            baseline_hash=baseline.fingerprint_hash,
            current_hash=current.fingerprint_hash,
            baseline_age_days=baseline_age_days,
        )

    def _changes_from_diff(self, diff: SchemaDiff) -> tuple[SchemaChange, ...]:
        changes: list[SchemaChange] = []

        for path in diff.added_fields:
            changes.append(
                SchemaChange(
                    change_type="add",
                    path=path,
                    severity=self.classify_severity("add"),
                )
            )

        for path in diff.removed_fields:
            changes.append(
                SchemaChange(
                    change_type="remove",
                    path=path,
                    severity=self.classify_severity("remove"),
                )
            )

        for path, old_type, new_type in diff.type_changes:
            change_type = "type_change"
            if "null" in {old_type, new_type}:
                change_type = "optional_change"
            changes.append(
                SchemaChange(
                    change_type=change_type,
                    path=path,
                    old_type=old_type,
                    new_type=new_type,
                    severity=self.classify_severity(
                        change_type,
                        old_type=old_type,
                        new_type=new_type,
                    ),
                )
            )

        for path, old_type, new_type in diff.nesting_changes:
            changes.append(
                SchemaChange(
                    change_type="nesting_change",
                    path=path,
                    old_type=old_type,
                    new_type=new_type,
                    severity=self.classify_severity("nesting_change"),
                )
            )

        for path, old_type, new_type in diff.cardinality_changes:
            changes.append(
                SchemaChange(
                    change_type="cardinality_change",
                    path=path,
                    old_type=old_type,
                    new_type=new_type,
                    severity=self.classify_severity("cardinality_change"),
                )
            )

        for rename in diff.likely_renames:
            changes.append(
                SchemaChange(
                    change_type="rename",
                    path=rename.old_field,
                    detail=f"{rename.old_field} -> {rename.new_field}",
                    similarity=rename.similarity,
                    severity=self.classify_severity("rename"),
                )
            )

        # Stable deterministic ordering for tests and reproducibility.
        return tuple(sorted(changes, key=lambda c: (c.path, c.change_type)))

    def _record_history(
        self,
        service: str,
        endpoint: str,
        changes: tuple[SchemaChange, ...],
        status_code: int,
    ) -> None:
        key = self._history_key(service, endpoint, status_code)
        bucket = self._history.setdefault(key, [])
        bucket.extend(changes)

        if any(change.severity == "breaking" for change in changes):
            self._last_change_at[self._service_history_key(service)] = datetime.now(tz=UTC)

    def get_change_history(
        self,
        service: str,
        endpoint: str,
        *,
        limit: int = 5,
        status_code: int = 200,
    ) -> tuple[SchemaChange, ...]:
        """Get recent change history for an endpoint."""
        key = self._history_key(service, endpoint, status_code)
        history = self._history.get(key, [])
        if not history:
            return tuple()
        return tuple(history[-max(1, limit) :])

    def get_latest_fingerprint(
        self,
        service: str,
        endpoint: str,
        *,
        status_code: int = 200,
    ) -> SchemaFingerprint | None:
        """Return current baseline fingerprint for an endpoint."""
        key = self._baseline_key(service, endpoint, status_code)
        baseline = self._get_baseline(key)
        return baseline.fingerprint if baseline else None

    def get_service_stability_days(self, service: str) -> float | None:
        """Return number of days since last breaking schema change for service."""
        key = self._service_history_key(service)
        last_change = self._last_change_at.get(key)
        if last_change is None:
            # No known breaking change: treat as stable from tracker start.
            return 30.0
        return (datetime.now(tz=UTC) - last_change).total_seconds() / 86400.0

    def age_baseline_for_test(
        self,
        service: str,
        endpoint: str,
        *,
        days: int,
        status_code: int = 200,
    ) -> None:
        """Backdate baseline (test helper)."""
        key = self._baseline_key(service, endpoint, status_code)
        baseline = self._baselines.get(key)
        if baseline is None:
            return
        baseline.captured_at = datetime.now(tz=UTC) - timedelta(days=days)


_detector_singleton: SchemaChangeDetector | None = None


def get_schema_change_detector(redis_client: Any = None) -> SchemaChangeDetector:
    """Return singleton schema change detector."""
    global _detector_singleton
    if _detector_singleton is None:
        _detector_singleton = SchemaChangeDetector(redis_client=redis_client)
    return _detector_singleton


def reset_schema_change_detector() -> None:
    """Reset singleton detector (test helper)."""
    global _detector_singleton
    _detector_singleton = None
