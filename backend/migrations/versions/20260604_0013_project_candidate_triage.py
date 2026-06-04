"""add project candidate triage fields

Revision ID: 20260604_0013
Revises: 20260518_0012
Create Date: 2026-06-04 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260604_0013"
down_revision = "20260518_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("project_candidates") as batch_op:
        batch_op.add_column(sa.Column("triage_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("triage_tier", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("triage_reasons_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("triage_warnings_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("recommended_action", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("triaged_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_project_candidates_triage_tier", "project_candidates", ["triage_tier"])
    op.create_index("ix_project_candidates_recommended_action", "project_candidates", ["recommended_action"])


def downgrade() -> None:
    op.drop_index("ix_project_candidates_recommended_action", table_name="project_candidates")
    op.drop_index("ix_project_candidates_triage_tier", table_name="project_candidates")
    with op.batch_alter_table("project_candidates") as batch_op:
        batch_op.drop_column("triaged_at")
        batch_op.drop_column("recommended_action")
        batch_op.drop_column("triage_warnings_json")
        batch_op.drop_column("triage_reasons_json")
        batch_op.drop_column("triage_tier")
        batch_op.drop_column("triage_score")
