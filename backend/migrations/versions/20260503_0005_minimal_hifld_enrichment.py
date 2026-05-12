"""minimal hifld enrichment

Revision ID: 20260503_0005
Revises: 20260502_0004
Create Date: 2026-05-03 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260503_0005"
down_revision = "20260502_0004"
branch_labels = None
depends_on = None


def _uuid() -> sa.UUID:
    return postgresql.UUID(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    ]


def upgrade() -> None:
    op.add_column("projects", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("projects", sa.Column("longitude", sa.Float(), nullable=True))

    op.create_table(
        "grid_retail_territories",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("utility_name", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_feature_id", sa.String(length=128), nullable=True),
        sa.Column("geometry_json", sa.JSON(), nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "project_enrichment_snapshot",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("project_id", _uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("retail_utility_name", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("project_enrichment_snapshot")
    op.drop_table("grid_retail_territories")
    op.drop_column("projects", "longitude")
    op.drop_column("projects", "latitude")
