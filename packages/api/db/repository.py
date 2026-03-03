"""Persistence helpers for AN score records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from db.models import ANScore, Base, Service


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
            calculated_at=datetime.utcnow(),
        )
        self._rows.append(entry)
        return entry.id

    def fetch_latest_score(self, service_slug: str) -> StoredScore | None:
        matches = [row for row in self._rows if row.service_slug == service_slug]
        if not matches:
            return None
        return sorted(matches, key=lambda row: row.calculated_at or datetime.min)[-1]

    def query_by_score_range(
        self, min_score: float = 0.0, max_score: float = 10.0
    ) -> list[StoredScore]:
        return [row for row in self._rows if min_score <= row.score <= max_score]


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
