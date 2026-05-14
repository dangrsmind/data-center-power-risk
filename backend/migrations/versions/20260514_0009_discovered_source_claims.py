"""add discovered source claims

Revision ID: 20260514_0009
Revises: 20260513_0008
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260514_0009"
down_revision = "20260513_0008"
branch_labels = None
depends_on = None


def _uuid() -> sa.UUID:
    return sa.UUID().with_variant(sa.CHAR(36), "sqlite")


def upgrade() -> None:
    op.create_table(
        "discovered_source_claims",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("discovered_source_id", _uuid(), sa.ForeignKey("discovered_sources.id"), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(length=64), nullable=False),
        sa.Column("claim_value", sa.Text(), nullable=False),
        sa.Column("claim_unit", sa.String(length=64), nullable=True),
        sa.Column("evidence_excerpt", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("extractor_name", sa.String(length=128), nullable=False),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="extracted"),
        sa.Column("raw_metadata_json", sa.JSON(), nullable=True),
        sa.Column("claim_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("status in ('extracted', 'rejected', 'promoted')", name="status_valid"),
        sa.CheckConstraint("confidence >= 0 and confidence <= 1", name="confidence_range"),
        sa.UniqueConstraint("claim_fingerprint", name="uq_discovered_source_claims_fingerprint"),
    )
    op.create_index(
        "ix_discovered_source_claims_discovered_source_id",
        "discovered_source_claims",
        ["discovered_source_id"],
    )
    op.create_index("ix_discovered_source_claims_claim_type", "discovered_source_claims", ["claim_type"])
    op.create_index("ix_discovered_source_claims_status", "discovered_source_claims", ["status"])


def downgrade() -> None:
    op.drop_index("ix_discovered_source_claims_status", table_name="discovered_source_claims")
    op.drop_index("ix_discovered_source_claims_claim_type", table_name="discovered_source_claims")
    op.drop_index("ix_discovered_source_claims_discovered_source_id", table_name="discovered_source_claims")
    op.drop_table("discovered_source_claims")
