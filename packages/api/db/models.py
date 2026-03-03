"""SQLAlchemy models for Rhumb v0 schema."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for ORM models."""


class Service(Base):
    """Indexed service metadata."""

    __tablename__ = "services"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    base_url: Mapped[str | None] = mapped_column(Text)
    docs_url: Mapped[str | None] = mapped_column(Text)
    openapi_url: Mapped[str | None] = mapped_column(Text)
    mcp_server_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DimensionScore(Base):
    """Per-dimension AN score entry."""

    __tablename__ = "dimension_scores"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    service_id: Mapped[UUID | None] = mapped_column(ForeignKey("services.id"))
    dimension: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Numeric(3, 1), nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    last_evidence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    explanation: Mapped[str | None] = mapped_column(Text)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ANScore(Base):
    """Materialized composite AN score."""

    __tablename__ = "an_scores"
    __table_args__ = (Index("idx_an_scores_service", "service_id", "calculated_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    service_id: Mapped[UUID | None] = mapped_column(ForeignKey("services.id"))
    score: Mapped[float] = mapped_column(Numeric(3, 1), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    dimension_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ProbeResult(Base):
    """Raw probe capture for evidence and diffing."""

    __tablename__ = "probe_results"
    __table_args__ = (Index("idx_probe_results_service", "service_id", "probed_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    service_id: Mapped[UUID | None] = mapped_column(ForeignKey("services.id"))
    probe_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    response_code: Mapped[int | None] = mapped_column(Integer)
    response_schema_hash: Mapped[str | None] = mapped_column(Text)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    probe_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)
    probed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SchemaSnapshot(Base):
    """Schema snapshots for breaking-change detection."""

    __tablename__ = "schema_snapshots"
    __table_args__ = (Index("idx_schema_snapshots_service", "service_id", "captured_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    service_id: Mapped[UUID | None] = mapped_column(ForeignKey("services.id"))
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    schema_hash: Mapped[str] = mapped_column(Text, nullable=False)
    schema_body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(Text)
    is_breaking: Mapped[bool] = mapped_column(Boolean, default=False)
    diff_summary: Mapped[str | None] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FailureMode(Base):
    """Observed service failure modes."""

    __tablename__ = "failure_modes"
    __table_args__ = (Index("idx_failure_modes_service", "service_id", "resolved_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    service_id: Mapped[UUID | None] = mapped_column(ForeignKey("services.id"))
    category: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    frequency: Mapped[str] = mapped_column(Text, nullable=False)
    agent_impact: Mapped[str | None] = mapped_column(Text)
    workaround: Mapped[str | None] = mapped_column(Text)
    first_detected: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
