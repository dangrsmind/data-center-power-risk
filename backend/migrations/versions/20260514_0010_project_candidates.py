"""add project candidates

Revision ID: 20260514_0010
Revises: 20260514_0009
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260514_0010"
down_revision = "20260514_0009"
branch_labels = None
depends_on = None


def _uuid() -> sa.UUID:
    return sa.UUID().with_variant(sa.CHAR(36), "sqlite")


def upgrade() -> None:
    op.create_table(
        "project_candidates",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("candidate_key", sa.String(length=255), nullable=False),
        sa.Column("candidate_name", sa.String(length=255), nullable=False),
        sa.Column("developer", sa.String(length=255), nullable=True),
        sa.Column("state", sa.String(length=64), nullable=True),
        sa.Column("county", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=255), nullable=True),
        sa.Column("utility", sa.String(length=255), nullable=True),
        sa.Column("load_mw", sa.Float(), nullable=True),
        sa.Column("lifecycle_state", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="needs_review"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claim_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("primary_source_url", sa.Text(), nullable=True),
        sa.Column("discovered_source_ids_json", sa.JSON(), nullable=True),
        sa.Column("discovered_source_claim_ids_json", sa.JSON(), nullable=True),
        sa.Column("evidence_excerpt", sa.Text(), nullable=True),
        sa.Column("raw_metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("status in ('candidate', 'needs_review', 'rejected', 'promoted')", name="status_valid"),
        sa.CheckConstraint("confidence >= 0 and confidence <= 1", name="confidence_range"),
        sa.UniqueConstraint("candidate_key", name="uq_project_candidates_candidate_key"),
    )
    op.create_index("ix_project_candidates_status", "project_candidates", ["status"])
    op.create_index("ix_project_candidates_state", "project_candidates", ["state"])
    op.create_index("ix_project_candidates_candidate_name", "project_candidates", ["candidate_name"])


def downgrade() -> None:
    op.drop_index("ix_project_candidates_candidate_name", table_name="project_candidates")
    op.drop_index("ix_project_candidates_state", table_name="project_candidates")
    op.drop_index("ix_project_candidates_status", table_name="project_candidates")
    op.drop_table("project_candidates")
