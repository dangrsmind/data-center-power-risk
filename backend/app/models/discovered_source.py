from __future__ import annotations

from datetime import datetime

import uuid

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, GUID, TimestampMixin, UUIDPrimaryKeyMixin


class DiscoveredSourceRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "discovered_sources"
    __table_args__ = (
        UniqueConstraint("source_url", name="uq_discovered_sources_source_url"),
        CheckConstraint(
            "status in ('discovered', 'candidate', 'rejected', 'promoted')",
            name="status_valid",
        ),
        Index("ix_discovered_sources_source_type", "source_type"),
        Index("ix_discovered_sources_publisher", "publisher"),
        Index("ix_discovered_sources_status", "status"),
    )

    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    geography: Mapped[str | None] = mapped_column(String(255), nullable=True)
    discovery_method: Mapped[str | None] = mapped_column(String(128), nullable=True)
    discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(64), nullable=True)
    search_term: Mapped[str | None] = mapped_column(String(255), nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    case_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_registry_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    adapter_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    discovery_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_metadata_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="discovered")


class DiscoveredSourceClaim(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "discovered_source_claims"
    __table_args__ = (
        UniqueConstraint("claim_fingerprint", name="uq_discovered_source_claims_fingerprint"),
        CheckConstraint(
            "status in ('extracted', 'rejected', 'promoted')",
            name="status_valid",
        ),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="confidence_range"),
        Index("ix_discovered_source_claims_discovered_source_id", "discovered_source_id"),
        Index("ix_discovered_source_claims_claim_type", "claim_type"),
        Index("ix_discovered_source_claims_status", "status"),
    )

    discovered_source_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("discovered_sources.id"), nullable=False
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_value: Mapped[str] = mapped_column(Text, nullable=False)
    claim_unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(nullable=False)
    extractor_name: Mapped[str] = mapped_column(String(128), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="extracted")
    raw_metadata_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    claim_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
