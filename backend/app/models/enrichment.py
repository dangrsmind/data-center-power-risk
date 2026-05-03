from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base, GUID, TimestampMixin, UUIDPrimaryKeyMixin


class GridRetailTerritory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "grid_retail_territories"

    utility_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="HIFLD")
    source_feature_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    geometry_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)


class ProjectEnrichmentSnapshot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "project_enrichment_snapshot"

    project_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("projects.id"), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    retail_utility_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
