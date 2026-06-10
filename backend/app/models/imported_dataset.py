from __future__ import annotations

import uuid

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, GUID, TimestampMixin, UUIDPrimaryKeyMixin


class ImportedDatasetRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "imported_dataset_runs"
    __table_args__ = (
        Index("ix_imported_dataset_runs_dataset_name", "dataset_name"),
        Index("ix_imported_dataset_runs_source_file", "source_file"),
    )

    dataset_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dataset_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    license_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    dry_run: Mapped[bool] = mapped_column(nullable=False, default=True)
    summary_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)


class ImportedDatasetRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "imported_dataset_rows"
    __table_args__ = (
        UniqueConstraint("run_id", "source_file", "row_number", name="uq_imported_dataset_rows_run_file_row"),
        Index("ix_imported_dataset_rows_dataset_name", "dataset_name"),
        Index("ix_imported_dataset_rows_duplicate_status", "duplicate_status"),
        Index("ix_imported_dataset_rows_cluster_key", "duplicate_cluster_key"),
        Index("ix_imported_dataset_rows_linked_candidate", "linked_project_candidate_id"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("imported_dataset_runs.id"), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dataset_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    row_number: Mapped[int] = mapped_column(nullable=False)
    raw_row_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    normalized_row_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    source_urls_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    duplicate_status: Mapped[str] = mapped_column(String(64), nullable=False, default="insufficient_information")
    duplicate_cluster_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linked_project_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("project_candidates.id"), nullable=True
    )
    warnings_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    errors_json: Mapped[list | None] = mapped_column(JSON, nullable=True)


class ImportedCandidateLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "imported_candidate_links"
    __table_args__ = (
        UniqueConstraint("imported_row_id", "linked_record_type", "linked_record_id", name="uq_imported_candidate_link"),
        Index("ix_imported_candidate_links_cluster_key", "duplicate_cluster_key"),
    )

    imported_row_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("imported_dataset_rows.id"), nullable=False)
    linked_record_type: Mapped[str] = mapped_column(String(64), nullable=False)
    linked_record_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    duplicate_status: Mapped[str] = mapped_column(String(64), nullable=False)
    duplicate_cluster_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    match_reasons_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
