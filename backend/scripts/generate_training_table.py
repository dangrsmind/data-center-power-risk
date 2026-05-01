from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal, create_db_and_tables, engine
from app.core.enums import ClaimEntityType, ClaimReviewStatus, ClaimType, EventFamily, SourceSignalType, StressEntityType
from app.models.evidence import Claim, Evidence
from app.models.event import Event
from app.models.project import Phase, Project
from app.models.quarterly import ProjectPhaseQuarter, QuarterlyLabel, QuarterlySnapshot, StressObservation, StressScore


FEATURE_VERSION = "project_phase_quarter_features_v1"
TRAILING_4Q_MONTHS = 12
UNRESOLVED_STATUSES = {
    ClaimReviewStatus.UNREVIEWED,
    ClaimReviewStatus.LINKED,
    ClaimReviewStatus.ACCEPTED_CANDIDATE,
    ClaimReviewStatus.AMBIGUOUS,
    ClaimReviewStatus.NEEDS_MORE_REVIEW,
}
CRITICAL_CLAIM_TYPES = {
    "modeled_load_mw": ClaimType.MODELED_LOAD_MW,
    "utility_named": ClaimType.UTILITY_NAMED,
    "region_or_rto_named": ClaimType.REGION_OR_RTO_NAMED,
    "target_energization_date": ClaimType.TARGET_ENERGIZATION_DATE,
    "power_path_support": ClaimType.POWER_PATH_IDENTIFIED_FLAG,
}


@dataclass
class TrainingRow:
    project_id: str
    phase_id: str
    quarter: str
    is_active: bool
    is_censored: bool
    target_E1_next_quarter: bool
    target_E1_within_4q: bool
    features_as_of_prior_quarter: dict[str, Any]
    cutoff_date: str
    generated_at: str
    feature_version: str


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        normalized = value.normalize()
        if normalized == normalized.to_integral():
            return int(normalized)
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def claim_scope_filter(project_id: Any, phase_id: Any) -> Any:
    return or_(
        and_(Claim.entity_type == ClaimEntityType.PROJECT, Claim.entity_id == project_id),
        and_(Claim.entity_type == ClaimEntityType.PHASE, Claim.entity_id == phase_id),
    )


def event_scope_filter(project: Project, phase_id: Any) -> Any:
    filters = [
        Event.project_id == project.id,
        Event.phase_id == phase_id,
    ]
    if project.region_id:
        filters.append(Event.region_id == project.region_id)
    if project.utility_id:
        filters.append(Event.utility_id == project.utility_id)
    return or_(*filters)


def latest_prior_snapshot(db: Session, ppq: ProjectPhaseQuarter) -> QuarterlySnapshot | None:
    stmt = (
        select(QuarterlySnapshot)
        .join(ProjectPhaseQuarter, QuarterlySnapshot.project_phase_quarter_id == ProjectPhaseQuarter.id)
        .where(
            ProjectPhaseQuarter.project_id == ppq.project_id,
            ProjectPhaseQuarter.phase_id == ppq.phase_id,
            ProjectPhaseQuarter.quarter < ppq.quarter,
        )
        .order_by(ProjectPhaseQuarter.quarter.desc(), QuarterlySnapshot.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def latest_prior_stress_score(db: Session, project_id: Any, cutoff: date) -> StressScore | None:
    stmt = (
        select(StressScore)
        .where(
            StressScore.entity_type == StressEntityType.PROJECT,
            StressScore.entity_id == project_id,
            StressScore.quarter < cutoff,
        )
        .order_by(StressScore.quarter.desc(), StressScore.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def accepted_claims_as_of(db: Session, project_id: Any, phase_id: Any, cutoff: date) -> list[Claim]:
    stmt = (
        select(Claim)
        .join(Evidence, Claim.evidence_id == Evidence.id)
        .where(
            claim_scope_filter(project_id, phase_id),
            Claim.review_status == ClaimReviewStatus.ACCEPTED,
            Claim.accepted_at.is_not(None),
            Claim.accepted_at < cutoff,
            or_(Evidence.source_date.is_(None), Evidence.source_date < cutoff),
        )
        .order_by(Claim.accepted_at.asc(), Claim.created_at.asc())
    )
    return list(db.execute(stmt).scalars().all())


def claims_created_as_of(db: Session, project_id: Any, phase_id: Any, cutoff: date) -> list[Claim]:
    stmt = (
        select(Claim)
        .join(Evidence, Claim.evidence_id == Evidence.id)
        .where(
            claim_scope_filter(project_id, phase_id),
            Claim.created_at < cutoff,
            or_(Evidence.source_date.is_(None), Evidence.source_date < cutoff),
        )
        .order_by(Claim.created_at.asc())
    )
    return list(db.execute(stmt).scalars().all())


def evidence_count_as_of(db: Session, project_id: Any, phase_id: Any, cutoff: date, accepted_claims: list[Claim]) -> int:
    evidence_ids = {claim.evidence_id for claim in accepted_claims}
    if not evidence_ids:
        return 0
    stmt = select(Evidence.id).where(
        Evidence.id.in_(evidence_ids),
        or_(Evidence.source_date.is_(None), Evidence.source_date < cutoff),
    )
    return len(set(db.execute(stmt).scalars().all()))


def claim_value(claim: Claim, key: str, default: Any = None) -> Any:
    value = claim.claim_value_json if isinstance(claim.claim_value_json, dict) else {}
    return value.get(key, default)


def first_claim_value(claims: list[Claim], claim_type: ClaimType, key: str) -> Any:
    for claim in reversed(claims):
        if claim.claim_type == claim_type:
            return claim_value(claim, key)
    return None


def months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def parse_iso_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def accepted_claim_features(claims: list[Claim]) -> dict[str, Any]:
    modeled_load = first_claim_value(claims, ClaimType.MODELED_LOAD_MW, "modeled_primary_load_mw")
    optional_expansion = first_claim_value(claims, ClaimType.OPTIONAL_EXPANSION_MW, "optional_expansion_mw")
    target_date = first_claim_value(claims, ClaimType.TARGET_ENERGIZATION_DATE, "target_energization_date")
    accepted_state = first_claim_value(claims, ClaimType.LOCATION_STATE, "state")
    accepted_county = first_claim_value(claims, ClaimType.LOCATION_COUNTY, "county")
    power_path = first_claim_value(claims, ClaimType.POWER_PATH_IDENTIFIED_FLAG, "value")
    new_transmission = first_claim_value(claims, ClaimType.NEW_TRANSMISSION_REQUIRED_FLAG, "value")
    new_substation = first_claim_value(claims, ClaimType.NEW_SUBSTATION_REQUIRED_FLAG, "value")
    onsite_generation = first_claim_value(claims, ClaimType.ONSITE_GENERATION_FLAG, "value")

    accepted_types = {claim.claim_type for claim in claims}
    return {
        "accepted_claim_count": len(claims),
        "accepted_evidence_claim_types": sorted(claim_type.value for claim_type in accepted_types),
        "accepted_location_state": to_jsonable(accepted_state),
        "accepted_location_county": to_jsonable(accepted_county),
        "accepted_modeled_primary_load_mw": to_jsonable(modeled_load),
        "accepted_optional_expansion_mw": to_jsonable(optional_expansion),
        "accepted_target_energization_date": to_jsonable(target_date),
        "accepted_utility_identified": ClaimType.UTILITY_NAMED in accepted_types,
        "accepted_region_or_rto_identified": ClaimType.REGION_OR_RTO_NAMED in accepted_types,
        "accepted_power_path_identified": bool(power_path) if power_path is not None else None,
        "accepted_new_transmission_required": bool(new_transmission) if new_transmission is not None else None,
        "accepted_new_substation_required": bool(new_substation) if new_substation is not None else None,
        "accepted_onsite_generation_planned": bool(onsite_generation) if onsite_generation is not None else None,
        "missing_critical_field_count": sum(1 for claim_type in CRITICAL_CLAIM_TYPES.values() if claim_type not in accepted_types),
        "missing_critical_fields": [
            field_name for field_name, claim_type in CRITICAL_CLAIM_TYPES.items() if claim_type not in accepted_types
        ],
    }


def evidence_features(db: Session, project_id: Any, phase_id: Any, cutoff: date, accepted_claims: list[Claim]) -> dict[str, Any]:
    all_claims = claims_created_as_of(db, project_id, phase_id, cutoff)
    unresolved_count = sum(1 for claim in all_claims if claim.review_status in UNRESOLVED_STATUSES)
    contradictory_count = sum(1 for claim in all_claims if claim.is_contradictory)
    return {
        "accepted_evidence_count": evidence_count_as_of(db, project_id, phase_id, cutoff, accepted_claims),
        "claim_count_asof": len(all_claims),
        "unresolved_claim_count": unresolved_count,
        "contradictory_claim_count": contradictory_count,
    }


def stress_features(db: Session, project: Project, phase_id: Any, cutoff: date) -> dict[str, Any]:
    window_start = add_months(cutoff, -TRAILING_4Q_MONTHS)
    event_stmt = select(Event).where(
        event_scope_filter(project, phase_id),
        Event.event_date >= window_start,
        Event.event_date < cutoff,
    )
    events = list(db.execute(event_stmt).scalars().all())

    obs_filters = [
        and_(StressObservation.entity_type == StressEntityType.PROJECT, StressObservation.entity_id == project.id),
    ]
    if project.region_id:
        obs_filters.append(StressObservation.region_id == project.region_id)
    if project.utility_id:
        obs_filters.append(StressObservation.utility_id == project.utility_id)
    obs_stmt = select(StressObservation).where(
        or_(*obs_filters),
        StressObservation.quarter >= window_start,
        StressObservation.quarter < cutoff,
    )
    observations = list(db.execute(obs_stmt).scalars().all())
    latest_score = latest_prior_stress_score(db, project.id, cutoff)

    def event_count(family: EventFamily) -> int:
        return sum(1 for event in events if event.event_family == family)

    def event_weight(family: EventFamily) -> float:
        return float(sum((event.weak_label_weight or Decimal("0")) for event in events if event.event_family == family))

    def observation_sum(signal_type: SourceSignalType) -> float:
        return float(sum(obs.signal_value * obs.signal_weight for obs in observations if obs.source_signal_type == signal_type))

    return {
        "E1_event_count_trailing_4q": event_count(EventFamily.E1),
        "E2_event_count_trailing_4q": event_count(EventFamily.E2),
        "E2_event_weight_trailing_4q": event_weight(EventFamily.E2),
        "E3_event_count_trailing_4q": event_count(EventFamily.E3),
        "E3_event_weight_trailing_4q": event_weight(EventFamily.E3),
        "E4_event_count_trailing_4q": event_count(EventFamily.E4),
        "E4_event_weight_trailing_4q": event_weight(EventFamily.E4),
        "E2_stress_observation_sum_trailing_4q": observation_sum(SourceSignalType.E2),
        "E3_stress_observation_sum_trailing_4q": observation_sum(SourceSignalType.E3),
        "E4_stress_observation_sum_trailing_4q": observation_sum(SourceSignalType.E4),
        "latest_project_stress_score": to_jsonable(latest_score.project_stress_score) if latest_score else None,
        "latest_regional_stress_score": to_jsonable(latest_score.regional_stress_score) if latest_score else None,
        "latest_anomaly_score": to_jsonable(latest_score.anomaly_score) if latest_score else None,
        "latest_stress_score_quarter": to_jsonable(latest_score.quarter) if latest_score else None,
    }


def snapshot_features(db: Session, ppq: ProjectPhaseQuarter) -> dict[str, Any]:
    snapshot = latest_prior_snapshot(db, ppq)
    feature_json = snapshot.feature_json if snapshot and isinstance(snapshot.feature_json, dict) else {}
    return {
        "prior_snapshot_version": snapshot.snapshot_version if snapshot else None,
        "observability_score": to_jsonable(snapshot.observability_score) if snapshot else None,
        "data_quality_score": to_jsonable(snapshot.data_quality_score) if snapshot else None,
        "snapshot_utility_identified": feature_json.get("utility_identified"),
        "snapshot_power_path_identified": feature_json.get("power_path_identified"),
        "snapshot_new_transmission_required": feature_json.get("new_transmission_required"),
        "snapshot_new_substation_required": feature_json.get("new_substation_required"),
        "snapshot_onsite_generation_planned": feature_json.get("onsite_generation_planned"),
        "snapshot_electrical_dependency_complexity_score": feature_json.get("electrical_dependency_complexity_score"),
    }


def structural_features(phase: Phase, ppq: ProjectPhaseQuarter) -> dict[str, Any]:
    return {
        "project_age_quarters": ppq.project_age_quarters,
        "phase_order": phase.phase_order,
    }


def has_e1_between(db: Session, project: Project, phase_id: Any, start: date, end: date) -> bool:
    label_stmt = (
        select(QuarterlyLabel)
        .join(ProjectPhaseQuarter, QuarterlyLabel.project_phase_quarter_id == ProjectPhaseQuarter.id)
        .where(
            ProjectPhaseQuarter.project_id == project.id,
            ProjectPhaseQuarter.phase_id == phase_id,
            ProjectPhaseQuarter.quarter >= start,
            ProjectPhaseQuarter.quarter < end,
            QuarterlyLabel.E1_label.is_(True),
        )
        .limit(1)
    )
    if db.execute(label_stmt).scalar_one_or_none() is not None:
        return True

    event_stmt = select(Event.id).where(
        event_scope_filter(project, phase_id),
        Event.event_family == EventFamily.E1,
        Event.event_date >= start,
        Event.event_date < end,
    ).limit(1)
    return db.execute(event_stmt).scalar_one_or_none() is not None


def build_row(db: Session, ppq: ProjectPhaseQuarter, generated_at: str) -> TrainingRow:
    project = db.get(Project, ppq.project_id)
    phase = db.get(Phase, ppq.phase_id)
    if project is None or phase is None:
        raise RuntimeError(f"Missing project or phase for project_phase_quarter {ppq.id}")

    cutoff = ppq.quarter
    accepted_claims = accepted_claims_as_of(db, ppq.project_id, ppq.phase_id, cutoff)
    accepted_features = accepted_claim_features(accepted_claims)
    accepted_target_date = parse_iso_date(accepted_features.get("accepted_target_energization_date"))
    if accepted_target_date is not None:
        accepted_features["accepted_months_to_target_energization"] = months_between(cutoff, accepted_target_date)
    else:
        accepted_features["accepted_months_to_target_energization"] = None

    features: dict[str, Any] = {
        "cutoff_rule": "features use records source-dated and accepted/created before the row quarter start",
        "prediction_origin_quarter": cutoff.isoformat(),
        **structural_features(phase, ppq),
        **accepted_features,
        **evidence_features(db, ppq.project_id, ppq.phase_id, cutoff, accepted_claims),
        **stress_features(db, project, ppq.phase_id, cutoff),
        **snapshot_features(db, ppq),
    }

    next_quarter = add_months(ppq.quarter, 3)
    after_next_quarter = add_months(ppq.quarter, 6)
    within_4q_end = add_months(ppq.quarter, 15)

    return TrainingRow(
        project_id=str(ppq.project_id),
        phase_id=str(ppq.phase_id),
        quarter=ppq.quarter.isoformat(),
        is_active=ppq.is_active,
        is_censored=ppq.is_censored,
        target_E1_next_quarter=has_e1_between(db, project, ppq.phase_id, next_quarter, after_next_quarter),
        target_E1_within_4q=has_e1_between(db, project, ppq.phase_id, next_quarter, within_4q_end),
        features_as_of_prior_quarter=features,
        cutoff_date=cutoff.isoformat(),
        generated_at=generated_at,
        feature_version=FEATURE_VERSION,
    )


def create_training_table() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS project_phase_quarter_features (
                    project_id TEXT NOT NULL,
                    phase_id TEXT NOT NULL,
                    quarter DATE NOT NULL,
                    is_active INTEGER NOT NULL,
                    is_censored INTEGER NOT NULL,
                    target_E1_next_quarter INTEGER NOT NULL,
                    target_E1_within_4q INTEGER NOT NULL,
                    features_as_of_prior_quarter TEXT NOT NULL,
                    cutoff_date DATE NOT NULL,
                    generated_at TEXT NOT NULL,
                    feature_version TEXT NOT NULL,
                    PRIMARY KEY (project_id, phase_id, quarter)
                )
                """
            )
        )


def replace_training_rows(db: Session, rows: list[TrainingRow]) -> None:
    db.execute(text("DELETE FROM project_phase_quarter_features"))
    payloads = [
        {
            "project_id": row.project_id,
            "phase_id": row.phase_id,
            "quarter": row.quarter,
            "is_active": int(row.is_active),
            "is_censored": int(row.is_censored),
            "target_E1_next_quarter": int(row.target_E1_next_quarter),
            "target_E1_within_4q": int(row.target_E1_within_4q),
            "features_as_of_prior_quarter": json.dumps(row.features_as_of_prior_quarter, sort_keys=True, default=to_jsonable),
            "cutoff_date": row.cutoff_date,
            "generated_at": row.generated_at,
            "feature_version": row.feature_version,
        }
        for row in rows
    ]
    if payloads:
        db.execute(
            text(
                """
                INSERT INTO project_phase_quarter_features (
                    project_id,
                    phase_id,
                    quarter,
                    is_active,
                    is_censored,
                    target_E1_next_quarter,
                    target_E1_within_4q,
                    features_as_of_prior_quarter,
                    cutoff_date,
                    generated_at,
                    feature_version
                ) VALUES (
                    :project_id,
                    :phase_id,
                    :quarter,
                    :is_active,
                    :is_censored,
                    :target_E1_next_quarter,
                    :target_E1_within_4q,
                    :features_as_of_prior_quarter,
                    :cutoff_date,
                    :generated_at,
                    :feature_version
                )
                """
            ),
            payloads,
        )
    db.commit()


def write_csv(rows: list[TrainingRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "project_id",
                "phase_id",
                "quarter",
                "is_active",
                "is_censored",
                "target_E1_next_quarter",
                "target_E1_within_4q",
                "features_as_of_prior_quarter",
                "cutoff_date",
                "generated_at",
                "feature_version",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "project_id": row.project_id,
                    "phase_id": row.phase_id,
                    "quarter": row.quarter,
                    "is_active": int(row.is_active),
                    "is_censored": int(row.is_censored),
                    "target_E1_next_quarter": int(row.target_E1_next_quarter),
                    "target_E1_within_4q": int(row.target_E1_within_4q),
                    "features_as_of_prior_quarter": json.dumps(row.features_as_of_prior_quarter, sort_keys=True, default=to_jsonable),
                    "cutoff_date": row.cutoff_date,
                    "generated_at": row.generated_at,
                    "feature_version": row.feature_version,
                }
            )


def build_training_rows(db: Session) -> list[TrainingRow]:
    generated_at = datetime.now(timezone.utc).isoformat()
    ppqs = list(
        db.execute(
            select(ProjectPhaseQuarter).order_by(
                ProjectPhaseQuarter.quarter.asc(),
                ProjectPhaseQuarter.project_id.asc(),
                ProjectPhaseQuarter.phase_id.asc(),
            )
        ).scalars().all()
    )
    return [build_row(db, ppq, generated_at) for ppq in ppqs]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate as-of project_phase_quarter training features.")
    parser.add_argument("--csv", type=Path, default=None, help="Optional CSV output path.")
    parser.add_argument("--no-sqlite", action="store_true", help="Only write CSV; do not create/replace the SQLite table.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    create_db_and_tables()
    if not args.no_sqlite:
        create_training_table()

    with SessionLocal() as db:
        rows = build_training_rows(db)
        if not args.no_sqlite:
            replace_training_rows(db, rows)
        if args.csv:
            write_csv(rows, args.csv)

    destinations = []
    if not args.no_sqlite:
        destinations.append("SQLite table project_phase_quarter_features")
    if args.csv:
        destinations.append(str(args.csv))
    print(f"Generated {len(rows)} project_phase_quarter feature rows -> {', '.join(destinations) or 'no output'}")


if __name__ == "__main__":
    main()
