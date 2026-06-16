"""add project candidate analyst review fields

Revision ID: 20260612_0015
Revises: 20260610_0014
Create Date: 2026-06-12 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260612_0015"
down_revision = "20260610_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("project_candidates") as batch_op:
        batch_op.add_column(sa.Column("review_decision", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("review_notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_by", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_project_candidates_review_decision", "project_candidates", ["review_decision"])


def downgrade() -> None:
    op.drop_index("ix_project_candidates_review_decision", table_name="project_candidates")
    with op.batch_alter_table("project_candidates") as batch_op:
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by")
        batch_op.drop_column("review_notes")
        batch_op.drop_column("review_decision")
