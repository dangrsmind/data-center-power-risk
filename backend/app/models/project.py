from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, Enum, Float, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import LifecycleState, LoadKind, enum_values
from app.models.base import Base, GUID, TimestampMixin, UUIDPrimaryKeyMixin


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    developer: Mapped[str | None] = mapped_column(String(255))
    operator: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[str | None] = mapped_column(String(2))
    county: Mapped[str | None] = mapped_column(String(255))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    announcement_date: Mapped[date | None] = mapped_column(Date)
    latest_update_date: Mapped[date | None] = mapped_column(Date)
    lifecycle_state: Mapped[LifecycleState] = mapped_column(
        Enum(LifecycleState, name="lifecycle_state", native_enum=False, values_callable=enum_values), nullable=False
    )
    candidate_metadata_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("regions.id"), nullable=True
    )
    utility_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("utilities.id"), nullable=True
    )


class ProjectAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_aliases"

    project_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("projects.id"), nullable=False)
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    alias_type: Mapped[str | None] = mapped_column(String(64))


class Phase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "phases"

    project_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("projects.id"), nullable=False)
    phase_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phase_order: Mapped[int | None] = mapped_column(nullable=True)
    announcement_date: Mapped[date | None] = mapped_column(Date)
    target_energization_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)


class PhaseLoad(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "phase_loads"
    __table_args__ = (
        UniqueConstraint("phase_id", "load_kind"),
        CheckConstraint(
            "(load_kind = 'optional_expansion' AND is_optional_expansion = true) "
            "OR (load_kind <> 'optional_expansion' AND is_optional_expansion = false)",
            name="phase_load_optional_consistency",
        ),
    )

    phase_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("phases.id"), nullable=False)
    load_kind: Mapped[LoadKind] = mapped_column(
        Enum(LoadKind, name="load_kind", native_enum=False, values_callable=enum_values), nullable=False
    )
    load_mw: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    load_basis_type: Mapped[str | None] = mapped_column(String(64))
    load_source: Mapped[str | None] = mapped_column(String(255))
    load_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    is_optional_expansion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_firm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
