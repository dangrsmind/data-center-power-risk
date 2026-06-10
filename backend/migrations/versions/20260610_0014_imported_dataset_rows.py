"""add imported dataset audit tables

Revision ID: 20260610_0014
Revises: 20260604_0013
Create Date: 2026-06-10 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260610_0014"
down_revision = "20260604_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "imported_dataset_runs",
        sa.Column("dataset_name", sa.String(length=128), nullable=False),
        sa.Column("dataset_version", sa.String(length=128), nullable=True),
        sa.Column("dataset_source", sa.Text(), nullable=True),
        sa.Column("source_file", sa.Text(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("license_note", sa.Text(), nullable=True),
        sa.Column("citation", sa.Text(), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_imported_dataset_runs")),
    )
    op.create_index("ix_imported_dataset_runs_dataset_name", "imported_dataset_runs", ["dataset_name"])
    op.create_index("ix_imported_dataset_runs_source_file", "imported_dataset_runs", ["source_file"])

    op.create_table(
        "imported_dataset_rows",
        sa.Column("run_id", sa.CHAR(length=36), nullable=False),
        sa.Column("dataset_name", sa.String(length=128), nullable=False),
        sa.Column("dataset_version", sa.String(length=128), nullable=True),
        sa.Column("dataset_source", sa.Text(), nullable=True),
        sa.Column("source_file", sa.Text(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw_row_json", sa.JSON(), nullable=True),
        sa.Column("normalized_row_json", sa.JSON(), nullable=True),
        sa.Column("source_urls_json", sa.JSON(), nullable=True),
        sa.Column("duplicate_status", sa.String(length=64), nullable=False),
        sa.Column("duplicate_cluster_key", sa.String(length=255), nullable=True),
        sa.Column("linked_project_candidate_id", sa.CHAR(length=36), nullable=True),
        sa.Column("warnings_json", sa.JSON(), nullable=True),
        sa.Column("errors_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["linked_project_candidate_id"], ["project_candidates.id"], name=op.f("fk_imported_dataset_rows_linked_project_candidate_id_project_candidates")),
        sa.ForeignKeyConstraint(["run_id"], ["imported_dataset_runs.id"], name=op.f("fk_imported_dataset_rows_run_id_imported_dataset_runs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_imported_dataset_rows")),
        sa.UniqueConstraint("run_id", "source_file", "row_number", name="uq_imported_dataset_rows_run_file_row"),
    )
    op.create_index("ix_imported_dataset_rows_cluster_key", "imported_dataset_rows", ["duplicate_cluster_key"])
    op.create_index("ix_imported_dataset_rows_dataset_name", "imported_dataset_rows", ["dataset_name"])
    op.create_index("ix_imported_dataset_rows_duplicate_status", "imported_dataset_rows", ["duplicate_status"])
    op.create_index("ix_imported_dataset_rows_linked_candidate", "imported_dataset_rows", ["linked_project_candidate_id"])

    op.create_table(
        "imported_candidate_links",
        sa.Column("imported_row_id", sa.CHAR(length=36), nullable=False),
        sa.Column("linked_record_type", sa.String(length=64), nullable=False),
        sa.Column("linked_record_id", sa.CHAR(length=36), nullable=True),
        sa.Column("duplicate_status", sa.String(length=64), nullable=False),
        sa.Column("duplicate_cluster_key", sa.String(length=255), nullable=True),
        sa.Column("match_reasons_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["imported_row_id"], ["imported_dataset_rows.id"], name=op.f("fk_imported_candidate_links_imported_row_id_imported_dataset_rows")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_imported_candidate_links")),
        sa.UniqueConstraint("imported_row_id", "linked_record_type", "linked_record_id", name="uq_imported_candidate_link"),
    )
    op.create_index("ix_imported_candidate_links_cluster_key", "imported_candidate_links", ["duplicate_cluster_key"])


def downgrade() -> None:
    op.drop_index("ix_imported_candidate_links_cluster_key", table_name="imported_candidate_links")
    op.drop_table("imported_candidate_links")
    op.drop_index("ix_imported_dataset_rows_linked_candidate", table_name="imported_dataset_rows")
    op.drop_index("ix_imported_dataset_rows_duplicate_status", table_name="imported_dataset_rows")
    op.drop_index("ix_imported_dataset_rows_dataset_name", table_name="imported_dataset_rows")
    op.drop_index("ix_imported_dataset_rows_cluster_key", table_name="imported_dataset_rows")
    op.drop_table("imported_dataset_rows")
    op.drop_index("ix_imported_dataset_runs_source_file", table_name="imported_dataset_runs")
    op.drop_index("ix_imported_dataset_runs_dataset_name", table_name="imported_dataset_runs")
    op.drop_table("imported_dataset_runs")
