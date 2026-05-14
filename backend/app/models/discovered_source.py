from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


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
