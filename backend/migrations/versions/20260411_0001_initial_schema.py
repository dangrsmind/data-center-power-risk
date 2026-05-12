"""initial schema

Revision ID: 20260411_0001
Revises:
Create Date: 2026-04-11 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260411_0001"
down_revision = None
branch_labels = None
depends_on = None


def _uuid() -> sa.UUID:
    return postgresql.UUID(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    ]


def upgrade() -> None:
    lifecycle_state = sa.Enum(
        "candidate_unverified",
        "named_verified",
        "location_verified",
        "load_partially_resolved",
        "phase_resolved",
        "power_path_partial",
        "monitoring_ready",
        "production_ready",
        name="lifecycle_state",
        native_enum=False,
    )
    source_type = sa.Enum(
        "official_filing",
        "utility_statement",
        "regulatory_record",
        "county_record",
        "press",
        "developer_statement",
        "other",
        name="source_type",
        native_enum=False,
    )
    reviewer_status = sa.Enum("pending", "reviewed", "rejected", name="reviewer_status", native_enum=False)
    claim_entity_type = sa.Enum(
        "project",
        "phase",
        "event",
        "region",
        "utility",
        "evidence",
        name="claim_entity_type",
        native_enum=False,
    )
    field_prov_entity_type = sa.Enum(
        "project",
        "phase",
        "event",
        "region",
        "utility",
        "evidence",
        name="field_provenance_entity_type",
        native_enum=False,
    )
    event_family = sa.Enum("E1", "E2", "E3", "E4", name="event_family", native_enum=False)
    event_scope = sa.Enum(
        "project_phase", "project", "utility", "county", "region", "RTO", name="event_scope", native_enum=False
    )
    causal_strength = sa.Enum(
        "explicit_primary",
        "explicit_secondary",
        "implied",
        "unknown",
        name="causal_strength",
        native_enum=False,
    )
    stress_direction = sa.Enum("increase", "decrease", "neutral", name="stress_direction", native_enum=False)
    adjudication_status = sa.Enum(
        "qualifying_positive",
        "ambiguous_near_positive",
        "non_event",
        name="adjudication_status",
        native_enum=False,
    )
    load_kind = sa.Enum(
        "headline", "modeled_primary", "optional_expansion", name="load_kind", native_enum=False
    )
    stress_entity_type = sa.Enum(
        "project_phase", "project", "utility", "county", "region", "RTO", name="stress_entity_type", native_enum=False
    )
    stress_score_entity_type = sa.Enum(
        "project_phase",
        "project",
        "utility",
        "county",
        "region",
        "RTO",
        name="stress_score_entity_type",
        native_enum=False,
    )
    source_signal_type = sa.Enum(
        "feature", "E2", "E3", "E4", "anomaly", name="source_signal_type", native_enum=False
    )
    score_run_type = sa.Enum("snapshot", "mock_scoring", name="score_run_type", native_enum=False)

    bind = op.get_bind()
    for enum_obj in [
        lifecycle_state,
        source_type,
        reviewer_status,
        claim_entity_type,
        field_prov_entity_type,
        event_family,
        event_scope,
        causal_strength,
        stress_direction,
        adjudication_status,
        load_kind,
        stress_entity_type,
        stress_score_entity_type,
        source_signal_type,
        score_run_type,
    ]:
        enum_obj.create(bind, checkfirst=True)

    op.create_table(
        "regions",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("region_type", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("state", sa.String(length=2), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("name", name="uq_regions_name"),
    )

    op.create_table(
        "utilities",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("region_id", _uuid(), sa.ForeignKey("regions.id"), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("name", name="uq_utilities_name"),
    )

    op.create_table(
        "projects",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("developer", sa.String(length=255), nullable=True),
        sa.Column("operator", sa.String(length=255), nullable=True),
        sa.Column("state", sa.String(length=2), nullable=True),
        sa.Column("county", sa.String(length=255), nullable=True),
        sa.Column("announcement_date", sa.Date(), nullable=True),
        sa.Column("latest_update_date", sa.Date(), nullable=True),
        sa.Column("lifecycle_state", lifecycle_state, nullable=False),
        sa.Column("region_id", _uuid(), sa.ForeignKey("regions.id"), nullable=True),
        sa.Column("utility_id", _uuid(), sa.ForeignKey("utilities.id"), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "project_aliases",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("project_id", _uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("alias_type", sa.String(length=64), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "phases",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("project_id", _uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("phase_name", sa.String(length=255), nullable=False),
        sa.Column("phase_order", sa.Integer(), nullable=True),
        sa.Column("announcement_date", sa.Date(), nullable=True),
        sa.Column("target_energization_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "phase_loads",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("phase_id", _uuid(), sa.ForeignKey("phases.id"), nullable=False),
        sa.Column("load_kind", load_kind, nullable=False),
        sa.Column("load_mw", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("load_basis_type", sa.String(length=64), nullable=True),
        sa.Column("load_source", sa.String(length=255), nullable=True),
        sa.Column("load_confidence", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("is_optional_expansion", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_firm", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.CheckConstraint(
            "(load_kind = 'optional_expansion' AND is_optional_expansion = true) "
            "OR (load_kind <> 'optional_expansion' AND is_optional_expansion = false)",
            name="ck_phase_loads_phase_load_optional_consistency",
        ),
        sa.UniqueConstraint("phase_id", "load_kind", name="uq_phase_loads_phase_id"),
    )

    op.create_table(
        "evidence",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_rank", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("reviewer_status", reviewer_status, nullable=False),
        *_timestamps(),
    )

    op.create_table(
        "claims",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("evidence_id", _uuid(), sa.ForeignKey("evidence.id"), nullable=False),
        sa.Column("entity_type", claim_entity_type, nullable=False),
        sa.Column("entity_id", _uuid(), nullable=False),
        sa.Column("claim_type", sa.String(length=128), nullable=False),
        sa.Column("claim_value_json", sa.JSON(), nullable=True),
        sa.Column("claim_date", sa.Date(), nullable=True),
        sa.Column("confidence", sa.String(length=32), nullable=True),
        sa.Column("is_contradictory", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
    )

    op.create_table(
        "field_provenance",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("entity_type", field_prov_entity_type, nullable=False),
        sa.Column("entity_id", _uuid(), nullable=False),
        sa.Column("field_name", sa.String(length=128), nullable=False),
        sa.Column("evidence_id", _uuid(), sa.ForeignKey("evidence.id"), nullable=False),
        sa.Column("claim_id", _uuid(), sa.ForeignKey("claims.id"), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "events",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("event_family", event_family, nullable=False),
        sa.Column("event_scope", event_scope, nullable=False),
        sa.Column("project_id", _uuid(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("phase_id", _uuid(), sa.ForeignKey("phases.id"), nullable=True),
        sa.Column("region_id", _uuid(), sa.ForeignKey("regions.id"), nullable=True),
        sa.Column("utility_id", _uuid(), sa.ForeignKey("utilities.id"), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("severity", sa.String(length=64), nullable=True),
        sa.Column("reason_class", sa.String(length=128), nullable=True),
        sa.Column("confidence", sa.String(length=32), nullable=True),
        sa.Column("evidence_class", sa.String(length=64), nullable=True),
        sa.Column("causal_strength", causal_strength, nullable=False),
        sa.Column("stress_direction", stress_direction, nullable=False),
        sa.Column("weak_label_weight", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("adjudicated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "adjudications",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("event_id", _uuid(), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("adjudication_status", adjudication_status, nullable=False),
        sa.Column("reviewer", sa.String(length=255), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "graph_nodes",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("phase_id", _uuid(), sa.ForeignKey("phases.id"), nullable=False),
        sa.Column("node_type", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("criticality", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("resolved_status", sa.String(length=64), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "graph_edges",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("phase_id", _uuid(), sa.ForeignKey("phases.id"), nullable=False),
        sa.Column("from_node_id", _uuid(), sa.ForeignKey("graph_nodes.id"), nullable=False),
        sa.Column("to_node_id", _uuid(), sa.ForeignKey("graph_nodes.id"), nullable=False),
        sa.Column("edge_type", sa.String(length=64), nullable=False),
        sa.Column("dependency_strength", sa.Numeric(precision=5, scale=2), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "project_phase_quarters",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("project_id", _uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("phase_id", _uuid(), sa.ForeignKey("phases.id"), nullable=False),
        sa.Column("quarter", sa.Date(), nullable=False),
        sa.Column("project_age_quarters", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_censored", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.CheckConstraint("project_id IS NOT NULL AND phase_id IS NOT NULL", name="ck_project_phase_quarters_ppq_project_phase_present"),
        sa.UniqueConstraint("project_id", "phase_id", "quarter", name="uq_project_phase_quarters_project_id"),
    )

    op.create_table(
        "quarterly_labels",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("project_phase_quarter_id", _uuid(), sa.ForeignKey("project_phase_quarters.id"), nullable=False),
        sa.Column("E1_label", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("E2_label", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("E3_intensity", sa.Numeric(precision=7, scale=3), nullable=True),
        sa.Column("E4_label", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("E1_label_confidence", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("E2_label_confidence", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("E3_confidence", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("E4_label_confidence", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("adjudication_status", sa.String(length=64), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("project_phase_quarter_id", name="uq_quarterly_labels_project_phase_quarter_id"),
    )

    op.create_table(
        "quarterly_snapshots",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("project_phase_quarter_id", _uuid(), sa.ForeignKey("project_phase_quarters.id"), nullable=False),
        sa.Column("snapshot_version", sa.String(length=64), nullable=False),
        sa.Column("feature_json", sa.JSON(), nullable=True),
        sa.Column("observability_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("data_quality_score", sa.Numeric(precision=5, scale=2), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "stress_observations",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("entity_type", stress_entity_type, nullable=False),
        sa.Column("entity_id", _uuid(), nullable=False),
        sa.Column("region_id", _uuid(), sa.ForeignKey("regions.id"), nullable=True),
        sa.Column("utility_id", _uuid(), sa.ForeignKey("utilities.id"), nullable=True),
        sa.Column("quarter", sa.Date(), nullable=False),
        sa.Column("source_signal_type", source_signal_type, nullable=False),
        sa.Column("signal_name", sa.String(length=128), nullable=False),
        sa.Column("signal_value", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("signal_weight", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("source_ref_ids", sa.JSON(), nullable=True),
        sa.Column("derived_by", sa.String(length=128), nullable=True),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "stress_scores",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("entity_type", stress_score_entity_type, nullable=False),
        sa.Column("entity_id", _uuid(), nullable=False),
        sa.Column("region_id", _uuid(), sa.ForeignKey("regions.id"), nullable=True),
        sa.Column("utility_id", _uuid(), sa.ForeignKey("utilities.id"), nullable=True),
        sa.Column("quarter", sa.Date(), nullable=False),
        sa.Column("project_stress_score", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("regional_stress_score", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("anomaly_score", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("decomposition_json", sa.JSON(), nullable=True),
        sa.Column("confidence_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "score_runs",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("run_type", score_run_type, nullable=False),
        sa.Column("snapshot_version", sa.String(length=64), nullable=True),
        sa.Column("weight_config_version", sa.String(length=64), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("scoring_method", sa.String(length=128), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
    )

    op.create_table(
        "phase_quarter_scores",
        sa.Column("id", _uuid(), primary_key=True, nullable=False),
        sa.Column("project_phase_quarter_id", _uuid(), sa.ForeignKey("project_phase_quarters.id"), nullable=False),
        sa.Column("score_run_id", _uuid(), sa.ForeignKey("score_runs.id"), nullable=False),
        sa.Column("deadline_date", sa.Date(), nullable=False),
        sa.Column("quarterly_hazard", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column("deadline_probability", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column("top_contributors_json", sa.JSON(), nullable=True),
        sa.Column("graph_fragility_summary_json", sa.JSON(), nullable=True),
        sa.Column("audit_trail_json", sa.JSON(), nullable=True),
        sa.Column("scoring_notes", sa.Text(), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        *_timestamps(),
    )


def downgrade() -> None:
    for table_name in [
        "phase_quarter_scores",
        "score_runs",
        "stress_scores",
        "stress_observations",
        "quarterly_snapshots",
        "quarterly_labels",
        "project_phase_quarters",
        "graph_edges",
        "graph_nodes",
        "adjudications",
        "events",
        "field_provenance",
        "claims",
        "evidence",
        "phase_loads",
        "phases",
        "project_aliases",
        "projects",
        "utilities",
        "regions",
    ]:
        op.drop_table(table_name)

    bind = op.get_bind()
    for enum_name in [
        "score_run_type",
        "source_signal_type",
        "stress_score_entity_type",
        "stress_entity_type",
        "load_kind",
        "adjudication_status",
        "stress_direction",
        "causal_strength",
        "event_scope",
        "event_family",
        "field_provenance_entity_type",
        "claim_entity_type",
        "reviewer_status",
        "source_type",
        "lifecycle_state",
    ]:
        sa.Enum(name=enum_name, native_enum=False).drop(bind, checkfirst=True)
