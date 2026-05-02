"""evidence review fields

Revision ID: 20260502_0004
Revises: 20260424_0003
Create Date: 2026-05-02 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260502_0004"
down_revision = "20260424_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evidence", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evidence", sa.Column("reviewed_by", sa.String(length=255), nullable=True))
    op.add_column("evidence", sa.Column("review_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("evidence", "review_notes")
    op.drop_column("evidence", "reviewed_by")
    op.drop_column("evidence", "reviewed_at")
