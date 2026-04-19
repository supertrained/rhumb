"""Persistence helpers for scores and probe records."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import quote
from uuid import UUID, uuid4

from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from db.models import ANScore, Base, ProbeResult, ProbeRun, Service
from routes._supabase import (
    supabase_fetch,
    supabase_score_insert_required,
    supabase_score_insert_returning_required,
    supabase_score_patch_required,
)
from services.chain_integrity import (
    build_score_audit_payload,
    canonicalize_payload,
    compute_chain_hmac,
    get_signing_key_version,
)

if TYPE_CHECKING:
    from services.scoring import ANScoreResult


_SCORE_TIER_LABELS = {
    "L1": "Emerging",
    "L2": "Developing",
    "L3": "Ready",
    "L4": "Native",
}


def _stored_service_slug_key(service_slug: str | None) -> str | None:
    cleaned = str(service_slug or "").strip().lower()
    return cleaned or None


@dataclass(slots=True)
class StoredScore:
    """Stored AN score payload used by services/routes."""

    id: UUID
    service_slug: str
    score: float
    confidence: float
    tier: str
    explanation: str
    dimension_snapshot: dict[str, Any]
    calculated_at: datetime | None


@dataclass(slots=True)
class StoredProbe:
    """Stored probe payload used by probe services/routes."""

    id: UUID
    run_id: UUID | None
    service_slug: str
    probe_type: str
    status: str
    latency_ms: int | None
    response_code: int | None
    response_schema_hash: str | None
    raw_response: dict[str, Any] | None
    probe_metadata: dict[str, Any] | None
    runner_version: str | None
    trigger_source: str | None
    probed_at: datetime | None


class ScoreRepository(Protocol):
    """Protocol for score persistence implementations."""

    async def save_score(
        self,
        service_slug: str,
        result: ANScoreResult,
    ) -> UUID | str: ...

    async def fetch_latest_score(self, service_slug: str) -> StoredScore | None: ...

    async def query_by_score_range(
        self, min_score: float = 0.0, max_score: float = 10.0
    ) -> list[StoredScore]: ...


class ProbeRepository(Protocol):
    """Protocol for probe persistence implementations."""

    def save_probe(
        self,
        service_slug: str,
        probe_type: str,
        status: str,
        latency_ms: int | None = None,
        response_code: int | None = None,
        response_schema_hash: str | None = None,
        raw_response: dict[str, Any] | None = None,
        probe_metadata: dict[str, Any] | None = None,
        trigger_source: str = "internal",
        runner_version: str = "scaffold-v1",
        error_message: str | None = None,
    ) -> StoredProbe: ...

    def fetch_latest_probe(
        self, service_slug: str, probe_type: str | None = None
    ) -> StoredProbe | None: ...

    def list_recent_probes(
        self,
        service_slug: str,
        probe_type: str | None = None,
        limit: int = 10,
    ) -> list[StoredProbe]: ...


@dataclass(slots=True)
class InMemoryScoreRepository:
    """Simple in-memory repository for tests and fallbacks."""

    _rows: list[StoredScore] = field(default_factory=list)

    async def save_score(
        self,
        service_slug: str,
        result: ANScoreResult,
    ) -> UUID:
        entry = StoredScore(
            id=uuid4(),
            service_slug=service_slug,
            score=result.score,
            confidence=result.confidence,
            tier=result.tier,
            explanation=result.explanation,
            dimension_snapshot=result.dimension_snapshot,
            calculated_at=result.calculated_at,
        )
        self._rows.append(entry)
        return entry.id

    async def fetch_latest_score(self, service_slug: str) -> StoredScore | None:
        matches = [row for row in self._rows if row.service_slug == service_slug]
        if not matches:
            return None
        min_utc = datetime.min.replace(tzinfo=timezone.utc)
        return sorted(matches, key=lambda row: row.calculated_at or min_utc)[-1]

    async def query_by_score_range(
        self, min_score: float = 0.0, max_score: float = 10.0
    ) -> list[StoredScore]:
        return [row for row in self._rows if min_score <= row.score <= max_score]


class SupabaseScoreRepository:
    """Supabase-backed score persistence on the protected score-truth surface."""

    GENESIS_HASH = "0" * 64

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def _score_probe_metadata(result: ANScoreResult) -> dict[str, Any]:
        return {
            "explanation": result.explanation,
            "dimension_snapshot": result.dimension_snapshot,
            "an_score_version": result.an_score_version,
            "writer_surface": "publisher",
        }

    @staticmethod
    def _autonomy_column_payload(result: ANScoreResult) -> dict[str, Any]:
        autonomy_section = (
            result.dimension_snapshot.get("autonomy")
            if isinstance(result.dimension_snapshot, dict)
            else None
        )
        raw_dimensions = (
            autonomy_section.get("dimensions", []) if isinstance(autonomy_section, dict) else []
        )

        by_code: dict[str, dict[str, Any]] = {}
        for entry in raw_dimensions:
            if not isinstance(entry, dict):
                continue
            code = entry.get("code")
            if isinstance(code, str) and code:
                by_code[code] = entry

        def _value(code: str, field: str) -> Any:
            candidate = by_code.get(code, {})
            return candidate.get(field)

        return {
            "payment_autonomy": _value("P1", "score"),
            "payment_autonomy_rationale": _value("P1", "rationale"),
            "payment_autonomy_confidence": _value("P1", "confidence"),
            "governance_readiness": _value("G1", "score"),
            "governance_readiness_rationale": _value("G1", "rationale"),
            "governance_readiness_confidence": _value("G1", "confidence"),
            "web_accessibility": _value("W1", "score"),
            "web_accessibility_rationale": _value("W1", "rationale"),
            "web_accessibility_confidence": _value("W1", "confidence"),
            "autonomy_score": result.autonomy_score,
        }

    @classmethod
    def _score_row_payload(cls, service_slug: str, result: ANScoreResult) -> dict[str, Any]:
        tier_labels = (
            result.dimension_snapshot.get("tier_labels", {})
            if isinstance(result.dimension_snapshot, dict)
            else {}
        )
        tier_label = tier_labels.get(result.tier, _SCORE_TIER_LABELS.get(result.tier, result.tier))

        payload: dict[str, Any] = {
            "service_slug": service_slug,
            "aggregate_recommendation_score": round(
                float(result.aggregate_recommendation_score), 2
            ),
            "execution_score": round(float(result.execution_score), 2),
            "access_readiness_score": (
                None
                if result.access_readiness_score is None
                else round(float(result.access_readiness_score), 2)
            ),
            "confidence": round(float(result.confidence), 4),
            "tier": result.tier,
            "tier_label": tier_label,
            "probe_metadata": cls._score_probe_metadata(result),
            "calculated_at": result.calculated_at.isoformat(),
        }
        payload.update(cls._autonomy_column_payload(result))
        return payload

    @staticmethod
    def _stored_from_score_row(row: dict[str, Any]) -> StoredScore | None:
        score_value = row.get("aggregate_recommendation_score")
        if score_value is None:
            score_value = row.get("score")
        if score_value is None:
            return None

        probe_metadata = row.get("probe_metadata")
        if not isinstance(probe_metadata, dict):
            probe_metadata = {}
        dimension_snapshot = probe_metadata.get("dimension_snapshot")
        if not isinstance(dimension_snapshot, dict):
            dimension_snapshot = {}

        raw_id = row.get("id")
        try:
            parsed_id = UUID(str(raw_id)) if raw_id is not None else uuid4()
        except (TypeError, ValueError):
            parsed_id = uuid4()

        return StoredScore(
            id=parsed_id,
            service_slug=str(row.get("service_slug") or ""),
            score=float(score_value),
            confidence=float(row.get("confidence") or 0.0),
            tier=str(row.get("tier") or "L1"),
            explanation=str(probe_metadata.get("explanation") or ""),
            dimension_snapshot=dimension_snapshot,
            calculated_at=SupabaseScoreRepository._parse_datetime(row.get("calculated_at")),
        )

    @staticmethod
    async def _ensure_service_exists(service_slug: str) -> None:
        rows = await supabase_fetch(f"services?slug=eq.{quote(service_slug)}&select=slug&limit=1")
        if not rows:
            raise ValueError(
                f"Cannot publish score for unknown canonical service_slug '{service_slug}'"
            )

    @staticmethod
    async def _latest_audit_hash() -> str:
        rows = await supabase_fetch(
            "score_audit_chain?select=chain_hash&order=created_at.desc&limit=1"
        )
        if not rows:
            return SupabaseScoreRepository.GENESIS_HASH
        latest = rows[0].get("chain_hash")
        return str(latest) if latest else SupabaseScoreRepository.GENESIS_HASH

    async def save_score(
        self,
        service_slug: str,
        result: ANScoreResult,
    ) -> UUID | str:
        await self._ensure_service_exists(service_slug)

        existing_rows = await supabase_fetch(
            f"scores?service_slug=eq.{quote(service_slug)}"
            "&select=id,aggregate_recommendation_score&limit=1"
        )
        existing = existing_rows[0] if existing_rows else None
        old_score = (
            float(existing.get("aggregate_recommendation_score"))
            if existing and existing.get("aggregate_recommendation_score") is not None
            else None
        )

        score_payload = self._score_row_payload(service_slug, result)
        persisted_id: UUID | str
        if existing is None:
            created = await supabase_score_insert_returning_required("scores", score_payload)
            persisted_id = str(created.get("id") or "") or str(uuid4())
        else:
            await supabase_score_patch_required(
                f"scores?service_slug=eq.{quote(service_slug)}",
                score_payload,
            )
            persisted_id = str(existing.get("id") or "") or str(uuid4())

        created_at = result.calculated_at.isoformat()
        change_reason = "initial" if old_score is None else "recalculation"
        entry_id = f"saud_{uuid4().hex}"
        prev_hash = await self._latest_audit_hash()
        audit_payload = build_score_audit_payload(
            {
                "entry_id": entry_id,
                "service_slug": service_slug,
                "old_score": old_score,
                "new_score": round(float(result.aggregate_recommendation_score), 2),
                "change_reason": change_reason,
                "created_at": created_at,
            }
        )
        payload_canonical_json = canonicalize_payload(audit_payload)
        key_version = get_signing_key_version()
        chain_hash = compute_chain_hmac(prev_hash, audit_payload, key_version=key_version)

        await supabase_score_insert_required(
            "score_audit_chain",
            {
                **audit_payload,
                "chain_hash": chain_hash,
                "prev_hash": prev_hash,
                "payload_canonical_json": payload_canonical_json,
                "key_version": key_version,
            },
        )

        return persisted_id

    async def fetch_latest_score(self, service_slug: str) -> StoredScore | None:
        rows = await supabase_fetch(
            f"scores?service_slug=eq.{quote(service_slug)}"
            "&select=id,service_slug,aggregate_recommendation_score,confidence,tier,probe_metadata,calculated_at"
            "&order=calculated_at.desc&limit=1"
        )
        if not rows:
            return None
        return self._stored_from_score_row(rows[0])

    async def query_by_score_range(
        self,
        min_score: float = 0.0,
        max_score: float = 10.0,
    ) -> list[StoredScore]:
        rows = await supabase_fetch(
            "scores?"
            f"aggregate_recommendation_score=gte.{min_score}"
            f"&aggregate_recommendation_score=lte.{max_score}"
            "&select=id,service_slug,aggregate_recommendation_score,confidence,tier,probe_metadata,calculated_at"
            "&order=aggregate_recommendation_score.desc.nullslast"
        )
        if not rows:
            return []
        stored: list[StoredScore] = []
        for row in rows:
            parsed = self._stored_from_score_row(row)
            if parsed is not None:
                stored.append(parsed)
        return stored


class DirectPostgresScorePublisherRepository:
    """Direct Postgres publisher rail for protected score truth.

    This exists for AUD-8 when the runtime can hold a restricted Postgres DSN
    for the `score_publisher` role but cannot mint a meaningfully distinct
    PostgREST/JWT credential. It writes `scores` and `score_audit_chain`
    directly, preserving the fail-closed score publication invariant while
    keeping the publisher boundary structurally separate from the broad
    service-role REST surface.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._sessionmaker = sessionmaker(bind=engine, expire_on_commit=False)

    @classmethod
    def from_url(cls, database_url: str) -> "DirectPostgresScorePublisherRepository":
        return cls(create_engine(database_url))

    @staticmethod
    def _json_dumps(value: dict[str, Any]) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _json_loads(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value:
            try:
                parsed = json.loads(value)
            except ValueError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        return None

    @classmethod
    def _stored_from_score_row(cls, row: dict[str, Any]) -> StoredScore | None:
        score_value = row.get("aggregate_recommendation_score")
        if score_value is None:
            score_value = row.get("score")
        if score_value is None:
            return None

        probe_metadata = cls._json_loads(row.get("probe_metadata"))
        dimension_snapshot = probe_metadata.get("dimension_snapshot")
        if not isinstance(dimension_snapshot, dict):
            dimension_snapshot = {}

        raw_id = row.get("id")
        try:
            parsed_id = UUID(str(raw_id)) if raw_id is not None else uuid4()
        except (TypeError, ValueError):
            parsed_id = uuid4()

        return StoredScore(
            id=parsed_id,
            service_slug=str(row.get("service_slug") or ""),
            score=float(score_value),
            confidence=float(row.get("confidence") or 0.0),
            tier=str(row.get("tier") or "L1"),
            explanation=str(probe_metadata.get("explanation") or ""),
            dimension_snapshot=dimension_snapshot,
            calculated_at=cls._parse_datetime(row.get("calculated_at")),
        )

    async def save_score(
        self,
        service_slug: str,
        result: ANScoreResult,
    ) -> UUID | str:
        score_payload = SupabaseScoreRepository._score_row_payload(service_slug, result)
        persisted_id: str

        with self._sessionmaker() as session:
            existing = (
                session.execute(
                    text(
                        "SELECT id, aggregate_recommendation_score "
                        "FROM scores WHERE service_slug = :slug LIMIT 1"
                    ),
                    {"slug": service_slug},
                )
                .mappings()
                .first()
            )

            old_score = (
                float(existing.get("aggregate_recommendation_score"))
                if existing and existing.get("aggregate_recommendation_score") is not None
                else None
            )

            score_params = {
                "service_slug": service_slug,
                "aggregate_recommendation_score": score_payload["aggregate_recommendation_score"],
                "execution_score": score_payload["execution_score"],
                "access_readiness_score": score_payload["access_readiness_score"],
                "confidence": score_payload["confidence"],
                "tier": score_payload["tier"],
                "tier_label": score_payload["tier_label"],
                "probe_metadata": self._json_dumps(score_payload["probe_metadata"]),
                "calculated_at": score_payload["calculated_at"],
                "payment_autonomy": score_payload.get("payment_autonomy"),
                "payment_autonomy_rationale": score_payload.get("payment_autonomy_rationale"),
                "payment_autonomy_confidence": score_payload.get("payment_autonomy_confidence"),
                "governance_readiness": score_payload.get("governance_readiness"),
                "governance_readiness_rationale": score_payload.get(
                    "governance_readiness_rationale"
                ),
                "governance_readiness_confidence": score_payload.get(
                    "governance_readiness_confidence"
                ),
                "web_accessibility": score_payload.get("web_accessibility"),
                "web_accessibility_rationale": score_payload.get("web_accessibility_rationale"),
                "web_accessibility_confidence": score_payload.get("web_accessibility_confidence"),
                "autonomy_score": score_payload.get("autonomy_score"),
            }

            try:
                if existing is None:
                    persisted_id = str(uuid4())
                    session.execute(
                        text(
                            "INSERT INTO scores ("
                            "id, service_slug, aggregate_recommendation_score, execution_score, "
                            "access_readiness_score, confidence, tier, tier_label, probe_metadata, "
                            "calculated_at, payment_autonomy, payment_autonomy_rationale, "
                            "payment_autonomy_confidence, governance_readiness, "
                            "governance_readiness_rationale, governance_readiness_confidence, "
                            "web_accessibility, web_accessibility_rationale, "
                            "web_accessibility_confidence, autonomy_score"
                            ") VALUES ("
                            ":id, :service_slug, :aggregate_recommendation_score, :execution_score, "
                            ":access_readiness_score, :confidence, :tier, :tier_label, :probe_metadata, "
                            ":calculated_at, :payment_autonomy, :payment_autonomy_rationale, "
                            ":payment_autonomy_confidence, :governance_readiness, "
                            ":governance_readiness_rationale, :governance_readiness_confidence, "
                            ":web_accessibility, :web_accessibility_rationale, "
                            ":web_accessibility_confidence, :autonomy_score"
                            ")"
                        ),
                        {"id": persisted_id, **score_params},
                    )
                else:
                    persisted_id = str(existing.get("id") or uuid4())
                    session.execute(
                        text(
                            "UPDATE scores SET "
                            "aggregate_recommendation_score = :aggregate_recommendation_score, "
                            "execution_score = :execution_score, "
                            "access_readiness_score = :access_readiness_score, "
                            "confidence = :confidence, "
                            "tier = :tier, "
                            "tier_label = :tier_label, "
                            "probe_metadata = :probe_metadata, "
                            "calculated_at = :calculated_at, "
                            "payment_autonomy = :payment_autonomy, "
                            "payment_autonomy_rationale = :payment_autonomy_rationale, "
                            "payment_autonomy_confidence = :payment_autonomy_confidence, "
                            "governance_readiness = :governance_readiness, "
                            "governance_readiness_rationale = :governance_readiness_rationale, "
                            "governance_readiness_confidence = :governance_readiness_confidence, "
                            "web_accessibility = :web_accessibility, "
                            "web_accessibility_rationale = :web_accessibility_rationale, "
                            "web_accessibility_confidence = :web_accessibility_confidence, "
                            "autonomy_score = :autonomy_score "
                            "WHERE service_slug = :service_slug"
                        ),
                        score_params,
                    )

                latest = (
                    session.execute(
                        text(
                            "SELECT chain_hash FROM score_audit_chain ORDER BY created_at DESC LIMIT 1"
                        )
                    )
                    .mappings()
                    .first()
                )
                prev_hash = (
                    str(latest.get("chain_hash"))
                    if latest and latest.get("chain_hash")
                    else self.GENESIS_HASH
                )

                created_at = result.calculated_at.isoformat()
                change_reason = "initial" if old_score is None else "recalculation"
                entry_id = f"saud_{uuid4().hex}"
                audit_payload = build_score_audit_payload(
                    {
                        "entry_id": entry_id,
                        "service_slug": service_slug,
                        "old_score": old_score,
                        "new_score": round(float(result.aggregate_recommendation_score), 2),
                        "change_reason": change_reason,
                        "created_at": created_at,
                    }
                )
                payload_canonical_json = canonicalize_payload(audit_payload)
                key_version = get_signing_key_version()
                chain_hash = compute_chain_hmac(
                    prev_hash,
                    audit_payload,
                    key_version=key_version,
                )

                session.execute(
                    text(
                        "INSERT INTO score_audit_chain ("
                        "entry_id, service_slug, old_score, new_score, change_reason, created_at, chain_hash, prev_hash, payload_canonical_json, key_version"
                        ") VALUES ("
                        ":entry_id, :service_slug, :old_score, :new_score, :change_reason, :created_at, :chain_hash, :prev_hash, :payload_canonical_json, :key_version"
                        ")"
                    ),
                    {
                        **audit_payload,
                        "chain_hash": chain_hash,
                        "prev_hash": prev_hash,
                        "payload_canonical_json": payload_canonical_json,
                        "key_version": key_version,
                    },
                )
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                if "foreign key" in str(exc).lower():
                    raise ValueError(
                        f"Cannot publish score for unknown canonical service_slug '{service_slug}'"
                    ) from exc
                raise

        return persisted_id

    async def fetch_latest_score(self, service_slug: str) -> StoredScore | None:
        with self._sessionmaker() as session:
            row = (
                session.execute(
                    text(
                        "SELECT id, service_slug, aggregate_recommendation_score, confidence, tier, "
                        "probe_metadata, calculated_at "
                        "FROM scores WHERE service_slug = :slug "
                        "ORDER BY calculated_at DESC LIMIT 1"
                    ),
                    {"slug": service_slug},
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            return self._stored_from_score_row(dict(row))

    async def query_by_score_range(
        self,
        min_score: float = 0.0,
        max_score: float = 10.0,
    ) -> list[StoredScore]:
        with self._sessionmaker() as session:
            rows = (
                session.execute(
                    text(
                        "SELECT id, service_slug, aggregate_recommendation_score, confidence, tier, "
                        "probe_metadata, calculated_at "
                        "FROM scores "
                        "WHERE aggregate_recommendation_score >= :min_score "
                        "AND aggregate_recommendation_score <= :max_score "
                        "ORDER BY aggregate_recommendation_score DESC"
                    ),
                    {"min_score": min_score, "max_score": max_score},
                )
                .mappings()
                .all()
            )
            stored: list[StoredScore] = []
            for row in rows:
                parsed = self._stored_from_score_row(dict(row))
                if parsed is not None:
                    stored.append(parsed)
            return stored


@dataclass(slots=True)
class InMemoryProbeRepository:
    """Simple in-memory probe repository for tests and fallbacks."""

    _rows: list[StoredProbe] = field(default_factory=list)

    def save_probe(
        self,
        service_slug: str,
        probe_type: str,
        status: str,
        latency_ms: int | None = None,
        response_code: int | None = None,
        response_schema_hash: str | None = None,
        raw_response: dict[str, Any] | None = None,
        probe_metadata: dict[str, Any] | None = None,
        trigger_source: str = "internal",
        runner_version: str = "scaffold-v1",
        error_message: str | None = None,
    ) -> StoredProbe:
        from uuid import uuid4

        now = datetime.now(timezone.utc)
        metadata = dict(probe_metadata or {})
        if error_message:
            metadata.setdefault("error_message", error_message)

        entry = StoredProbe(
            id=uuid4(),
            run_id=uuid4(),
            service_slug=service_slug,
            probe_type=probe_type,
            status=status,
            latency_ms=latency_ms,
            response_code=response_code,
            response_schema_hash=response_schema_hash,
            raw_response=raw_response,
            probe_metadata=metadata,
            runner_version=runner_version,
            trigger_source=trigger_source,
            probed_at=now,
        )
        self._rows.append(entry)
        return entry

    def fetch_latest_probe(
        self, service_slug: str, probe_type: str | None = None
    ) -> StoredProbe | None:
        service_key = _stored_service_slug_key(service_slug)
        if service_key is None:
            return None

        matches = [
            row for row in self._rows if _stored_service_slug_key(row.service_slug) == service_key
        ]
        if probe_type:
            matches = [row for row in matches if row.probe_type == probe_type]
        if not matches:
            return None
        min_utc = datetime.min.replace(tzinfo=timezone.utc)
        return sorted(matches, key=lambda row: row.probed_at or min_utc)[-1]

    def list_recent_probes(
        self,
        service_slug: str,
        probe_type: str | None = None,
        limit: int = 10,
    ) -> list[StoredProbe]:
        service_key = _stored_service_slug_key(service_slug)
        if service_key is None:
            return []

        matches = [
            row for row in self._rows if _stored_service_slug_key(row.service_slug) == service_key
        ]
        if probe_type:
            matches = [row for row in matches if row.probe_type == probe_type]

        min_utc = datetime.min.replace(tzinfo=timezone.utc)
        ordered = sorted(matches, key=lambda row: row.probed_at or min_utc, reverse=True)
        return ordered[: max(1, limit)]


class SQLAlchemyScoreRepository:
    """SQLAlchemy-backed score persistence implementation."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._sessionmaker = sessionmaker(bind=engine, expire_on_commit=False)
        self._initialized = False

    @classmethod
    def from_url(cls, database_url: str) -> "SQLAlchemyScoreRepository":
        """Create a repository from a DB URL."""
        engine = create_engine(database_url)
        return cls(engine)

    def create_tables(self) -> None:
        """Create required tables if they do not already exist."""
        Base.metadata.create_all(self._engine)
        self._initialized = True

    def _ensure_service(self, session: Session, service_slug: str) -> Service:
        service = session.scalar(select(Service).where(Service.slug == service_slug))
        if service is None:
            service = Service(
                slug=service_slug,
                name=service_slug.replace("-", " ").title(),
                category="unknown",
            )
            session.add(service)
            session.flush()
        return service

    @staticmethod
    def _to_stored_score(record: ANScore, service_slug: str) -> StoredScore:
        return StoredScore(
            id=record.id,
            service_slug=service_slug,
            score=float(record.score),
            confidence=float(record.confidence),
            tier=record.tier,
            explanation=record.explanation,
            dimension_snapshot=record.dimension_snapshot,
            calculated_at=record.calculated_at,
        )

    async def save_score(
        self,
        service_slug: str,
        result: ANScoreResult,
    ) -> UUID:
        if not self._initialized:
            self.create_tables()

        try:
            with self._sessionmaker() as session:
                service = self._ensure_service(session, service_slug)
                record = ANScore(
                    service_id=service.id,
                    score=round(result.score, 1),
                    confidence=round(result.confidence, 2),
                    tier=result.tier,
                    explanation=result.explanation,
                    dimension_snapshot=result.dimension_snapshot,
                )
                session.add(record)
                session.commit()
                return record.id
        except SQLAlchemyError:
            if not self._initialized:
                self.create_tables()
                return await self.save_score(
                    service_slug,
                    result,
                )
            raise

    async def fetch_latest_score(self, service_slug: str) -> StoredScore | None:
        if not self._initialized:
            self.create_tables()

        with self._sessionmaker() as session:
            stmt = (
                select(ANScore, Service.slug)
                .join(Service, Service.id == ANScore.service_id)
                .where(Service.slug == service_slug)
                .order_by(ANScore.calculated_at.desc())
                .limit(1)
            )
            row = session.execute(stmt).first()
            if row is None:
                return None
            score_record, slug = row
            return self._to_stored_score(score_record, slug)

    async def query_by_score_range(
        self, min_score: float = 0.0, max_score: float = 10.0
    ) -> list[StoredScore]:
        if not self._initialized:
            self.create_tables()

        with self._sessionmaker() as session:
            stmt = (
                select(ANScore, Service.slug)
                .join(Service, Service.id == ANScore.service_id)
                .where(ANScore.score >= min_score)
                .where(ANScore.score <= max_score)
                .order_by(ANScore.score.desc())
            )
            rows = session.execute(stmt).all()
            return [self._to_stored_score(score_record, slug) for score_record, slug in rows]


class SQLAlchemyProbeRepository:
    """SQLAlchemy-backed probe persistence implementation."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._sessionmaker = sessionmaker(bind=engine, expire_on_commit=False)
        self._initialized = False

    @classmethod
    def from_url(cls, database_url: str) -> "SQLAlchemyProbeRepository":
        """Create a repository from a DB URL."""
        engine = create_engine(database_url)
        return cls(engine)

    def create_tables(self) -> None:
        """Create required tables if they do not already exist."""
        Base.metadata.create_all(self._engine)
        self._initialized = True

    def _ensure_service(self, session: Session, service_slug: str) -> Service:
        service = session.scalar(select(Service).where(Service.slug == service_slug))
        if service is None:
            service = Service(
                slug=service_slug,
                name=service_slug.replace("-", " ").title(),
                category="unknown",
            )
            session.add(service)
            session.flush()
        return service

    @staticmethod
    def _to_stored_probe(
        record: ProbeResult,
        service_slug: str,
        runner_version: str | None,
        trigger_source: str | None,
    ) -> StoredProbe:
        return StoredProbe(
            id=record.id,
            run_id=record.run_id,
            service_slug=service_slug,
            probe_type=record.probe_type,
            status=record.status,
            latency_ms=record.latency_ms,
            response_code=record.response_code,
            response_schema_hash=record.response_schema_hash,
            raw_response=record.raw_response,
            probe_metadata=record.probe_metadata,
            runner_version=runner_version,
            trigger_source=trigger_source,
            probed_at=record.probed_at,
        )

    def save_probe(
        self,
        service_slug: str,
        probe_type: str,
        status: str,
        latency_ms: int | None = None,
        response_code: int | None = None,
        response_schema_hash: str | None = None,
        raw_response: dict[str, Any] | None = None,
        probe_metadata: dict[str, Any] | None = None,
        trigger_source: str = "internal",
        runner_version: str = "scaffold-v1",
        error_message: str | None = None,
    ) -> StoredProbe:
        if not self._initialized:
            self.create_tables()

        now = datetime.now(timezone.utc)
        metadata = dict(probe_metadata or {})
        if error_message:
            metadata.setdefault("error_message", error_message)

        try:
            with self._sessionmaker() as session:
                service = self._ensure_service(session, service_slug)

                run = ProbeRun(
                    service_id=service.id,
                    probe_type=probe_type,
                    status=status,
                    trigger_source=trigger_source,
                    runner_version=runner_version,
                    error_message=error_message,
                    run_metadata=metadata,
                    started_at=now,
                    finished_at=now,
                )
                session.add(run)
                session.flush()

                record = ProbeResult(
                    service_id=service.id,
                    run_id=run.id,
                    probe_type=probe_type,
                    status=status,
                    latency_ms=latency_ms,
                    response_code=response_code,
                    response_schema_hash=response_schema_hash,
                    raw_response=raw_response,
                    probe_metadata=metadata,
                    probed_at=now,
                )
                session.add(record)
                session.commit()

                return self._to_stored_probe(
                    record,
                    service_slug=service.slug,
                    runner_version=run.runner_version,
                    trigger_source=run.trigger_source,
                )
        except SQLAlchemyError:
            if not self._initialized:
                self.create_tables()
                return self.save_probe(
                    service_slug=service_slug,
                    probe_type=probe_type,
                    status=status,
                    latency_ms=latency_ms,
                    response_code=response_code,
                    response_schema_hash=response_schema_hash,
                    raw_response=raw_response,
                    probe_metadata=probe_metadata,
                    trigger_source=trigger_source,
                    runner_version=runner_version,
                    error_message=error_message,
                )
            raise

    def fetch_latest_probe(
        self, service_slug: str, probe_type: str | None = None
    ) -> StoredProbe | None:
        if not self._initialized:
            self.create_tables()

        service_key = _stored_service_slug_key(service_slug)
        if service_key is None:
            return None

        with self._sessionmaker() as session:
            stmt = (
                select(ProbeResult, Service.slug, ProbeRun.runner_version, ProbeRun.trigger_source)
                .join(Service, Service.id == ProbeResult.service_id)
                .outerjoin(ProbeRun, ProbeRun.id == ProbeResult.run_id)
                .where(func.lower(Service.slug) == service_key)
                .order_by(ProbeResult.probed_at.desc())
                .limit(1)
            )
            if probe_type:
                stmt = stmt.where(ProbeResult.probe_type == probe_type)

            row = session.execute(stmt).first()
            if row is None:
                return None

            probe_record, slug, runner_version, trigger_source = row
            return self._to_stored_probe(
                probe_record,
                service_slug=slug,
                runner_version=runner_version,
                trigger_source=trigger_source,
            )

    def list_recent_probes(
        self,
        service_slug: str,
        probe_type: str | None = None,
        limit: int = 10,
    ) -> list[StoredProbe]:
        if not self._initialized:
            self.create_tables()

        service_key = _stored_service_slug_key(service_slug)
        if service_key is None:
            return []

        with self._sessionmaker() as session:
            stmt = (
                select(ProbeResult, Service.slug, ProbeRun.runner_version, ProbeRun.trigger_source)
                .join(Service, Service.id == ProbeResult.service_id)
                .outerjoin(ProbeRun, ProbeRun.id == ProbeResult.run_id)
                .where(func.lower(Service.slug) == service_key)
                .order_by(ProbeResult.probed_at.desc())
                .limit(max(1, limit))
            )
            if probe_type:
                stmt = stmt.where(ProbeResult.probe_type == probe_type)

            rows = session.execute(stmt).all()
            return [
                self._to_stored_probe(
                    probe_record,
                    service_slug=slug,
                    runner_version=runner_version,
                    trigger_source=trigger_source,
                )
                for probe_record, slug, runner_version, trigger_source in rows
            ]
