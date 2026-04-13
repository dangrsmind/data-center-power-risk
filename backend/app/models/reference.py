from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, GUID, TimestampMixin, UUIDPrimaryKeyMixin


class Region(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "regions"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    region_type: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str | None] = mapped_column(String(2))


class Utility(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "utilities"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    code: Mapped[str | None] = mapped_column(String(64))
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("regions.id"), nullable=True
    )
