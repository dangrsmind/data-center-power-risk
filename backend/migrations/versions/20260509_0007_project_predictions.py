"""add project predictions

Revision ID: 20260509_0007
Revises: 20260508_0006
Create Date: 2026-05-09 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260509_0007"
down_revision = "20260508_0006"
branch_labels = None
depends_on = None


def _uuid() -> sa.UUID:
    return sa.UUID().with_variant(sa.CHAR(36), "sqlite")


def upgrade() -> None:
    op.create_table(
        "project_predictions",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("project_id", _uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("p_delay_6mo", sa.Float(), nullable=False),
        sa.Column("p_delay_12mo", sa.Float(), nullable=False),
        sa.Column("p_delay_18mo", sa.Float(), nullable=False),
        sa.Column("risk_tier", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("drivers_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("project_id", "model_name", "model_version", name="uq_project_predictions_project_model"),
    )
    op.create_index("ix_project_predictions_project_id", "project_predictions", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_project_predictions_project_id", table_name="project_predictions")
    op.drop_table("project_predictions")
