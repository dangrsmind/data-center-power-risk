"""add project candidate promotion link

Revision ID: 20260514_0011
Revises: 20260514_0010
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260514_0011"
down_revision = "20260514_0010"
branch_labels = None
depends_on = None


def _uuid() -> sa.UUID:
    return sa.UUID().with_variant(sa.CHAR(36), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("project_candidates") as batch_op:
        batch_op.add_column(sa.Column("promoted_project_id", _uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_project_candidates_promoted_project_id_projects",
            "projects",
            ["promoted_project_id"],
            ["id"],
        )
    op.create_index(
        "ix_project_candidates_promoted_project_id",
        "project_candidates",
        ["promoted_project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_candidates_promoted_project_id", table_name="project_candidates")
    with op.batch_alter_table("project_candidates") as batch_op:
        batch_op.drop_constraint(
            "fk_project_candidates_promoted_project_id_projects",
            type_="foreignkey",
        )
        batch_op.drop_column("promoted_project_id")
