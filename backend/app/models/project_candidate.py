from __future__ import annotations

import uuid

from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, GUID, TimestampMixin, UUIDPrimaryKeyMixin


class ProjectCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_candidates"
    __table_args__ = (
        UniqueConstraint("candidate_key", name="uq_project_candidates_candidate_key"),
        CheckConstraint(
            "status in ('candidate', 'needs_review', 'rejected', 'promoted')",
            name="status_valid",
        ),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="confidence_range"),
        Index("ix_project_candidates_status", "status"),
        Index("ix_project_candidates_state", "state"),
        Index("ix_project_candidates_candidate_name", "candidate_name"),
        Index("ix_project_candidates_promoted_project_id", "promoted_project_id"),
        Index("ix_project_candidates_verification_status", "verification_status"),
        Index("ix_project_candidates_triage_tier", "triage_tier"),
        Index("ix_project_candidates_recommended_action", "recommended_action"),
        Index("ix_project_candidates_review_decision", "review_decision"),
    )

    candidate_key: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    developer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    county: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    utility: Mapped[str | None] = mapped_column(String(255), nullable=True)
    load_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    lifecycle_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="needs_review")
    source_count: Mapped[int] = mapped_column(nullable=False, default=0)
    claim_count: Mapped[int] = mapped_column(nullable=False, default=0)
    primary_source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovered_source_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    discovered_source_claim_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    evidence_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_metadata_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    promoted_project_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("projects.id"), nullable=True
    )
    verification_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    verification_reasons_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    verification_errors_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    auto_admit_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    triage_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    triage_tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    triage_reasons_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    triage_warnings_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    triaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_decision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectCandidateSourceAttachment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_candidate_source_attachments"
    __table_args__ = (
        UniqueConstraint("project_candidate_id", "source_url", name="uq_candidate_source_attachment_url"),
        CheckConstraint(
            "source_type in ('official', 'utility', 'permit', 'media', 'dataset', 'other') or source_type is null",
            name="source_attachment_type_valid",
        ),
        Index("ix_project_candidate_source_attachments_candidate_id", "project_candidate_id"),
        Index("ix_project_candidate_source_attachments_source_type", "source_type"),
    )

    project_candidate_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("project_candidates.id"), nullable=False
    )
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyst_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    attached_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
