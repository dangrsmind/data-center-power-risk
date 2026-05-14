"""add discovered sources

Revision ID: 20260513_0008
Revises: 20260509_0007
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260513_0008"
down_revision = "20260509_0007"
branch_labels = None
depends_on = None


def _uuid() -> sa.UUID:
    return sa.UUID().with_variant(sa.CHAR(36), "sqlite")


def upgrade() -> None:
    op.create_table(
        "discovered_sources",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_title", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=128), nullable=True),
        sa.Column("publisher", sa.String(length=255), nullable=True),
        sa.Column("geography", sa.String(length=255), nullable=True),
        sa.Column("discovery_method", sa.String(length=128), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.String(length=64), nullable=True),
        sa.Column("search_term", sa.String(length=255), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("case_number", sa.String(length=128), nullable=True),
        sa.Column("document_type", sa.String(length=128), nullable=True),
        sa.Column("source_registry_id", sa.String(length=255), nullable=True),
        sa.Column("adapter_id", sa.String(length=128), nullable=True),
        sa.Column("discovery_run_id", sa.String(length=128), nullable=True),
        sa.Column("raw_metadata_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="discovered"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "status in ('discovered', 'candidate', 'rejected', 'promoted')",
            name="status_valid",
        ),
        sa.UniqueConstraint("source_url", name="uq_discovered_sources_source_url"),
    )
    op.create_index("ix_discovered_sources_source_type", "discovered_sources", ["source_type"])
    op.create_index("ix_discovered_sources_publisher", "discovered_sources", ["publisher"])
    op.create_index("ix_discovered_sources_status", "discovered_sources", ["status"])


def downgrade() -> None:
    op.drop_index("ix_discovered_sources_status", table_name="discovered_sources")
    op.drop_index("ix_discovered_sources_publisher", table_name="discovered_sources")
    op.drop_index("ix_discovered_sources_source_type", table_name="discovered_sources")
    op.drop_table("discovered_sources")
