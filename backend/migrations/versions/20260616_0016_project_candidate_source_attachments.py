"""add project candidate source attachments

Revision ID: 20260616_0016
Revises: 20260612_0015
Create Date: 2026-06-16 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260616_0016"
down_revision = "20260612_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_candidate_source_attachments",
        sa.Column("project_candidate_id", sa.CHAR(length=36), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("source_title", sa.String(length=500), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=True),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        sa.Column("analyst_notes", sa.Text(), nullable=True),
        sa.Column("attached_by", sa.String(length=255), nullable=True),
        sa.Column("attached_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.CheckConstraint(
            "source_type in ('official', 'utility', 'permit', 'media', 'dataset', 'other') or source_type is null",
            name=op.f("ck_project_candidate_source_attachments_source_attachment_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_candidate_id"],
            ["project_candidates.id"],
            name=op.f("fk_project_candidate_source_attachments_project_candidate_id_project_candidates"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_candidate_source_attachments")),
        sa.UniqueConstraint("project_candidate_id", "source_url", name="uq_candidate_source_attachment_url"),
    )
    op.create_index(
        "ix_project_candidate_source_attachments_candidate_id",
        "project_candidate_source_attachments",
        ["project_candidate_id"],
    )
    op.create_index(
        "ix_project_candidate_source_attachments_source_type",
        "project_candidate_source_attachments",
        ["source_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_candidate_source_attachments_source_type",
        table_name="project_candidate_source_attachments",
    )
    op.drop_index(
        "ix_project_candidate_source_attachments_candidate_id",
        table_name="project_candidate_source_attachments",
    )
    op.drop_table("project_candidate_source_attachments")
