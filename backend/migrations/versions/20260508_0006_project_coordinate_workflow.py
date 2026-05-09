"""project coordinate workflow

Revision ID: 20260508_0006
Revises: 20260503_0005
Create Date: 2026-05-08 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260508_0006"
down_revision = "20260503_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    project_columns = {column["name"] for column in inspector.get_columns("projects")}
    columns_to_add = [
        sa.Column("coordinate_status", sa.String(length=32), nullable=True),
        sa.Column("coordinate_precision", sa.String(length=32), nullable=True),
        sa.Column("coordinate_source", sa.String(length=64), nullable=True),
        sa.Column("coordinate_source_url", sa.String(length=1024), nullable=True),
        sa.Column("coordinate_notes", sa.Text(), nullable=True),
        sa.Column("coordinate_confidence", sa.Float(), nullable=True),
        sa.Column("coordinate_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("coordinate_verified_at", sa.DateTime(timezone=True), nullable=True),
    ]
    for column in columns_to_add:
        if column.name not in project_columns:
            op.add_column("projects", column)

    if "project_coordinate_history" not in inspector.get_table_names():
        op.create_table(
            "project_coordinate_history",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.UUID(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("old_latitude", sa.Float(), nullable=True),
            sa.Column("old_longitude", sa.Float(), nullable=True),
            sa.Column("new_latitude", sa.Float(), nullable=True),
            sa.Column("new_longitude", sa.Float(), nullable=True),
            sa.Column("old_coordinate_precision", sa.String(length=32), nullable=True),
            sa.Column("new_coordinate_precision", sa.String(length=32), nullable=True),
            sa.Column("old_coordinate_status", sa.String(length=32), nullable=True),
            sa.Column("new_coordinate_status", sa.String(length=32), nullable=True),
            sa.Column("source", sa.String(length=64), nullable=True),
            sa.Column("source_url", sa.String(length=1024), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("changed_by", sa.String(length=255), nullable=True, server_default="manual"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    history_indexes = {
        index["name"]
        for index in inspector.get_indexes("project_coordinate_history")
    }
    if "ix_project_coordinate_history_project_id" not in history_indexes:
        op.create_index(
            "ix_project_coordinate_history_project_id",
            "project_coordinate_history",
            ["project_id"],
        )

    op.execute(
        """
        UPDATE projects
        SET coordinate_status = 'missing'
        WHERE coordinate_status IS NULL
          AND (latitude IS NULL OR longitude IS NULL)
        """
    )
    op.execute(
        """
        UPDATE projects
        SET coordinate_status = 'unverified'
        WHERE coordinate_status IS NULL
          AND latitude IS NOT NULL
          AND longitude IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_project_coordinate_history_project_id", table_name="project_coordinate_history")
    op.drop_table("project_coordinate_history")
    op.drop_column("projects", "coordinate_verified_at")
    op.drop_column("projects", "coordinate_updated_at")
    op.drop_column("projects", "coordinate_confidence")
    op.drop_column("projects", "coordinate_notes")
    op.drop_column("projects", "coordinate_source_url")
    op.drop_column("projects", "coordinate_source")
    op.drop_column("projects", "coordinate_precision")
    op.drop_column("projects", "coordinate_status")
