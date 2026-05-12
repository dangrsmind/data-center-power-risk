from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, GUID, UUIDPrimaryKeyMixin


class ProjectPrediction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "project_predictions"
    __table_args__ = (
        UniqueConstraint("project_id", "model_name", "model_version", name="uq_project_predictions_project_model"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("projects.id"), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    p_delay_6mo: Mapped[float] = mapped_column(Float, nullable=False)
    p_delay_12mo: Mapped[float] = mapped_column(Float, nullable=False)
    p_delay_18mo: Mapped[float] = mapped_column(Float, nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    drivers_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
