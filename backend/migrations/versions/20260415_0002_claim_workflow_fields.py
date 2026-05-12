"""claim workflow fields

Revision ID: 20260415_0002
Revises: 20260411_0001
Create Date: 2026-04-15 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260415_0002"
down_revision = "20260411_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    claim_type = sa.Enum(
        "project_name_mention",
        "phase_name_mention",
        "developer_named",
        "operator_named",
        "location_state",
        "location_county",
        "utility_named",
        "region_or_rto_named",
        "modeled_load_mw",
        "optional_expansion_mw",
        "announcement_date",
        "target_energization_date",
        "latest_update_date",
        "power_path_identified_flag",
        "new_transmission_required_flag",
        "new_substation_required_flag",
        "onsite_generation_flag",
        "timeline_disruption_signal",
        "event_support_e2",
        "event_support_e3",
        "event_support_e4",
        name="claim_type",
        native_enum=False,
    )
    claim_review_status = sa.Enum(
        "unreviewed",
        "linked",
        "accepted_candidate",
        "accepted",
        "rejected",
        "ambiguous",
        "needs_more_review",
        name="claim_review_status",
        native_enum=False,
    )
    bind = op.get_bind()
    claim_type.create(bind, checkfirst=True)
    claim_review_status.create(bind, checkfirst=True)

    with op.batch_alter_table("claims") as batch_op:
        batch_op.alter_column("entity_type", existing_type=sa.String(length=7), nullable=True)
        batch_op.alter_column("entity_id", existing_type=sa.CHAR(length=36), nullable=True)
        batch_op.add_column(sa.Column("review_status", claim_review_status, nullable=False, server_default="unreviewed"))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("reviewed_by", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("review_notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("accepted_by", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("claim_type_v2", claim_type, nullable=True))
    op.execute("UPDATE claims SET claim_type_v2 = claim_type")
    with op.batch_alter_table("claims") as batch_op:
        batch_op.drop_column("claim_type")
        batch_op.alter_column("claim_type_v2", new_column_name="claim_type", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("claims") as batch_op:
        batch_op.add_column(sa.Column("claim_type_old", sa.String(length=128), nullable=True))
    op.execute("UPDATE claims SET claim_type_old = claim_type")
    with op.batch_alter_table("claims") as batch_op:
        batch_op.drop_column("claim_type")
        batch_op.alter_column("claim_type_old", new_column_name="claim_type", nullable=False)
        batch_op.drop_column("accepted_by")
        batch_op.drop_column("accepted_at")
        batch_op.drop_column("review_notes")
        batch_op.drop_column("reviewed_by")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("review_status")
        batch_op.alter_column("entity_id", existing_type=sa.CHAR(length=36), nullable=False)
        batch_op.alter_column("entity_type", existing_type=sa.String(length=7), nullable=False)

    bind = op.get_bind()
    sa.Enum(name="claim_review_status", native_enum=False).drop(bind, checkfirst=True)
    sa.Enum(name="claim_type", native_enum=False).drop(bind, checkfirst=True)
