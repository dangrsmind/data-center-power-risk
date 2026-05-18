"""add project candidate verification fields

Revision ID: 20260518_0012
Revises: 20260514_0011
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260518_0012"
down_revision = "20260514_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("project_candidates") as batch_op:
        batch_op.add_column(sa.Column("verification_status", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("verification_confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("verification_reasons_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("verification_errors_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("auto_admit_eligible", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_project_candidates_verification_status",
        "project_candidates",
        ["verification_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_candidates_verification_status", table_name="project_candidates")
    with op.batch_alter_table("project_candidates") as batch_op:
        batch_op.drop_column("verified_at")
        batch_op.drop_column("auto_admit_eligible")
        batch_op.drop_column("verification_errors_json")
        batch_op.drop_column("verification_reasons_json")
        batch_op.drop_column("verification_confidence")
        batch_op.drop_column("verification_status")
