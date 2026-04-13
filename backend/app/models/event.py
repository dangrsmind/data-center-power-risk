from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import AdjudicationStatus, CausalStrength, EventFamily, EventScope, StressDirection, enum_values
from app.models.base import Base, GUID, TimestampMixin, UUIDPrimaryKeyMixin


class Event(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "events"

    event_family: Mapped[EventFamily] = mapped_column(
        Enum(EventFamily, name="event_family", native_enum=False, values_callable=enum_values), nullable=False
    )
    event_scope: Mapped[EventScope] = mapped_column(
        Enum(EventScope, name="event_scope", native_enum=False, values_callable=enum_values), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("projects.id"), nullable=True
    )
    phase_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("phases.id"), nullable=True
    )
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("regions.id"), nullable=True
    )
    utility_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("utilities.id"), nullable=True
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    severity: Mapped[str | None] = mapped_column(String(64))
    reason_class: Mapped[str | None] = mapped_column(String(128))
    confidence: Mapped[str | None] = mapped_column(String(32))
    evidence_class: Mapped[str | None] = mapped_column(String(64))
    causal_strength: Mapped[CausalStrength] = mapped_column(
        Enum(CausalStrength, name="causal_strength", native_enum=False, values_callable=enum_values), nullable=False
    )
    stress_direction: Mapped[StressDirection] = mapped_column(
        Enum(StressDirection, name="stress_direction", native_enum=False, values_callable=enum_values), nullable=False
    )
    weak_label_weight: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    adjudicated: Mapped[bool] = mapped_column(nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class Adjudication(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "adjudications"

    event_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("events.id"), nullable=False)
    adjudication_status: Mapped[AdjudicationStatus] = mapped_column(
        Enum(AdjudicationStatus, name="adjudication_status", native_enum=False, values_callable=enum_values), nullable=False
    )
    reviewer: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
