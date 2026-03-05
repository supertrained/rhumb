"""Persistence helpers for scores and probe records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from db.models import ANScore, Base, ProbeResult, ProbeRun, Service


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

    def save_score(
        self,
        service_slug: str,
        score: float,
        confidence: float,
        tier: str,
        explanation: str,
        dimension_snapshot: dict[str, Any],
    ) -> UUID: ...

    def fetch_latest_score(self, service_slug: str) -> StoredScore | None: ...

    def query_by_score_range(
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

    def save_score(
        self,
        service_slug: str,
        score: float,
        confidence: float,
        tier: str,
        explanation: str,
        dimension_snapshot: dict[str, Any],
    ) -> UUID:
        from uuid import uuid4

        entry = StoredScore(
            id=uuid4(),
            service_slug=service_slug,
            score=score,
            confidence=confidence,
            tier=tier,
            explanation=explanation,
            dimension_snapshot=dimension_snapshot,
            calculated_at=datetime.now(timezone.utc),
        )
        self._rows.append(entry)
        return entry.id

    def fetch_latest_score(self, service_slug: str) -> StoredScore | None:
        matches = [row for row in self._rows if row.service_slug == service_slug]
        if not matches:
            return None
        min_utc = datetime.min.replace(tzinfo=timezone.utc)
        return sorted(matches, key=lambda row: row.calculated_at or min_utc)[-1]

    def query_by_score_range(
        self, min_score: float = 0.0, max_score: float = 10.0
    ) -> list[StoredScore]:
        return [row for row in self._rows if min_score <= row.score <= max_score]


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
        matches = [row for row in self._rows if row.service_slug == service_slug]
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
        matches = [row for row in self._rows if row.service_slug == service_slug]
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

    def save_score(
        self,
        service_slug: str,
        score: float,
        confidence: float,
        tier: str,
        explanation: str,
        dimension_snapshot: dict[str, Any],
    ) -> UUID:
        if not self._initialized:
            self.create_tables()

        try:
            with self._sessionmaker() as session:
                service = self._ensure_service(session, service_slug)
                record = ANScore(
                    service_id=service.id,
                    score=round(score, 1),
                    confidence=round(confidence, 2),
                    tier=tier,
                    explanation=explanation,
                    dimension_snapshot=dimension_snapshot,
                )
                session.add(record)
                session.commit()
                return record.id
        except SQLAlchemyError:
            if not self._initialized:
                self.create_tables()
                return self.save_score(
                    service_slug,
                    score,
                    confidence,
                    tier,
                    explanation,
                    dimension_snapshot,
                )
            raise

    def fetch_latest_score(self, service_slug: str) -> StoredScore | None:
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

    def query_by_score_range(
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

        with self._sessionmaker() as session:
            stmt = (
                select(ProbeResult, Service.slug, ProbeRun.runner_version, ProbeRun.trigger_source)
                .join(Service, Service.id == ProbeResult.service_id)
                .outerjoin(ProbeRun, ProbeRun.id == ProbeResult.run_id)
                .where(Service.slug == service_slug)
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

        with self._sessionmaker() as session:
            stmt = (
                select(ProbeResult, Service.slug, ProbeRun.runner_version, ProbeRun.trigger_source)
                .join(Service, Service.id == ProbeResult.service_id)
                .outerjoin(ProbeRun, ProbeRun.id == ProbeResult.run_id)
                .where(Service.slug == service_slug)
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
