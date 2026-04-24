"""add candidate metadata json to projects

Revision ID: 20260424_0003
Revises: 20260415_0002
Create Date: 2026-04-24 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260424_0003"
down_revision = "20260415_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("candidate_metadata_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "candidate_metadata_json")
