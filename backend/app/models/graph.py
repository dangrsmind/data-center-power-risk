from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, GUID, TimestampMixin, UUIDPrimaryKeyMixin


class GraphNode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "graph_nodes"

    phase_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("phases.id"), nullable=False)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    criticality: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    resolved_status: Mapped[str | None] = mapped_column(String(64))


class GraphEdge(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "graph_edges"

    phase_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("phases.id"), nullable=False)
    from_node_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("graph_nodes.id"), nullable=False
    )
    to_node_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("graph_nodes.id"), nullable=False
    )
    edge_type: Mapped[str] = mapped_column(String(64), nullable=False)
    dependency_strength: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
