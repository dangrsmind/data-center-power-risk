from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ScoreRunType, SourceSignalType, StressEntityType, enum_values
from app.models.base import Base, GUID, TimestampMixin, UUIDPrimaryKeyMixin


class ProjectPhaseQuarter(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_phase_quarters"
    __table_args__ = (
        UniqueConstraint("project_id", "phase_id", "quarter"),
        CheckConstraint("project_id IS NOT NULL AND phase_id IS NOT NULL", name="ppq_project_phase_present"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("projects.id"), nullable=False)
    phase_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("phases.id"), nullable=False)
    quarter: Mapped[date] = mapped_column(Date, nullable=False)
    project_age_quarters: Mapped[int | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_censored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class QuarterlyLabel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "quarterly_labels"
    __table_args__ = (UniqueConstraint("project_phase_quarter_id"),)

    project_phase_quarter_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("project_phase_quarters.id"), nullable=False
    )
    E1_label: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    E2_label: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    E3_intensity: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    E4_label: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    E1_label_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    E2_label_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    E3_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    E4_label_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    adjudication_status: Mapped[str | None] = mapped_column(String(64))


class QuarterlySnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "quarterly_snapshots"

    project_phase_quarter_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("project_phase_quarters.id"), nullable=False
    )
    snapshot_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_json: Mapped[dict | list | None] = mapped_column(JSON)
    observability_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    data_quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))


class StressObservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stress_observations"

    entity_type: Mapped[StressEntityType] = mapped_column(
        Enum(StressEntityType, name="stress_entity_type", native_enum=False, values_callable=enum_values), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("regions.id"), nullable=True
    )
    utility_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("utilities.id"), nullable=True
    )
    quarter: Mapped[date] = mapped_column(Date, nullable=False)
    source_signal_type: Mapped[SourceSignalType] = mapped_column(
        Enum(SourceSignalType, name="source_signal_type", native_enum=False, values_callable=enum_values), nullable=False
    )
    signal_name: Mapped[str] = mapped_column(String(128), nullable=False)
    signal_value: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    signal_weight: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    source_ref_ids: Mapped[list | None] = mapped_column(JSON)
    derived_by: Mapped[str | None] = mapped_column(String(128))
    run_id: Mapped[str | None] = mapped_column(String(64))


class StressScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stress_scores"

    entity_type: Mapped[StressEntityType] = mapped_column(
        Enum(StressEntityType, name="stress_score_entity_type", native_enum=False, values_callable=enum_values), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("regions.id"), nullable=True
    )
    utility_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("utilities.id"), nullable=True
    )
    quarter: Mapped[date] = mapped_column(Date, nullable=False)
    project_stress_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    regional_stress_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    anomaly_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    decomposition_json: Mapped[dict | list | None] = mapped_column(JSON)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(64))


class ScoreRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "score_runs"

    run_type: Mapped[ScoreRunType] = mapped_column(
        Enum(ScoreRunType, name="score_run_type", native_enum=False, values_callable=enum_values), nullable=False
    )
    snapshot_version: Mapped[str | None] = mapped_column(String(64))
    weight_config_version: Mapped[str | None] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    scoring_method: Mapped[str] = mapped_column(String(128), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class PhaseQuarterScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "phase_quarter_scores"

    project_phase_quarter_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("project_phase_quarters.id"), nullable=False
    )
    score_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("score_runs.id"), nullable=False
    )
    deadline_date: Mapped[date] = mapped_column(Date, nullable=False)
    quarterly_hazard: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    deadline_probability: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    top_contributors_json: Mapped[dict | list | None] = mapped_column(JSON)
    graph_fragility_summary_json: Mapped[dict | list | None] = mapped_column(JSON)
    audit_trail_json: Mapped[dict | list | None] = mapped_column(JSON)
    scoring_notes: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
