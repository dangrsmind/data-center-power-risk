"""add discovered source review triage fields

Revision ID: 20260618_0016
Revises: 20260612_0015
Create Date: 2026-06-18 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260618_0016"
down_revision = "20260612_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("discovered_sources") as batch_op:
        batch_op.add_column(sa.Column("review_status", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("review_notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("reviewed_by", sa.String(length=255), nullable=True))
    op.create_index("ix_discovered_sources_review_status", "discovered_sources", ["review_status"])


def downgrade() -> None:
    op.drop_index("ix_discovered_sources_review_status", table_name="discovered_sources")
    with op.batch_alter_table("discovered_sources") as batch_op:
        batch_op.drop_column("reviewed_by")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("review_notes")
        batch_op.drop_column("review_status")
