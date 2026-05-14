from __future__ import annotations

from sqlalchemy import JSON, CheckConstraint, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


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
