from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ClaimEntityType, ClaimReviewStatus, ClaimType, ReviewerStatus, SourceType, enum_values
from app.models.base import Base, GUID, TimestampMixin, UUIDPrimaryKeyMixin


class Evidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence"

    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type", native_enum=False, values_callable=enum_values), nullable=False
    )
    source_date: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_rank: Mapped[int | None] = mapped_column(nullable=True)
    title: Mapped[str | None] = mapped_column(String(255))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    reviewer_status: Mapped[ReviewerStatus] = mapped_column(
        Enum(ReviewerStatus, name="reviewer_status", native_enum=False, values_callable=enum_values), nullable=False
    )


class Claim(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "claims"

    evidence_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("evidence.id"), nullable=False)
    entity_type: Mapped[ClaimEntityType | None] = mapped_column(
        Enum(ClaimEntityType, name="claim_entity_type", native_enum=False, values_callable=enum_values), nullable=True
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    claim_type: Mapped[ClaimType] = mapped_column(
        Enum(ClaimType, name="claim_type", native_enum=False, values_callable=enum_values), nullable=False
    )
    claim_value_json: Mapped[dict | list | None] = mapped_column(JSON)
    claim_date: Mapped[date | None] = mapped_column(Date)
    confidence: Mapped[str | None] = mapped_column(String(32))
    is_contradictory: Mapped[bool] = mapped_column(nullable=False, default=False)
    review_status: Mapped[ClaimReviewStatus] = mapped_column(
        Enum(ClaimReviewStatus, name="claim_review_status", native_enum=False, values_callable=enum_values),
        nullable=False,
        default=ClaimReviewStatus.UNREVIEWED,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    review_notes: Mapped[str | None] = mapped_column(Text)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by: Mapped[str | None] = mapped_column(String(255))


class FieldProvenance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "field_provenance"

    entity_type: Mapped[ClaimEntityType] = mapped_column(
        Enum(ClaimEntityType, name="field_provenance_entity_type", native_enum=False, values_callable=enum_values), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("evidence.id"), nullable=False)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("claims.id"), nullable=True)
