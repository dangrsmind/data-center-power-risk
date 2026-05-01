from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import and_, inspect, or_, select, text
from sqlalchemy.orm import Session


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal, engine
from app.core.enums import ClaimEntityType, ClaimReviewStatus, ClaimType
from app.models.evidence import Claim, Evidence


TABLE_NAME = "project_phase_quarter_features"
CRITICAL_FIELDS = [
    "utility_named",
    "region_or_rto_named",
    "modeled_load_mw",
    "target_energization_date",
    "power_path_support",
]
FEATURE_CLAIM_REQUIREMENTS = {
    "accepted_modeled_primary_load_mw": ClaimType.MODELED_LOAD_MW,
    "accepted_optional_expansion_mw": ClaimType.OPTIONAL_EXPANSION_MW,
    "accepted_target_energization_date": ClaimType.TARGET_ENERGIZATION_DATE,
    "accepted_utility_identified": ClaimType.UTILITY_NAMED,
    "accepted_region_or_rto_identified": ClaimType.REGION_OR_RTO_NAMED,
    "accepted_power_path_identified": ClaimType.POWER_PATH_IDENTIFIED_FLAG,
    "accepted_new_transmission_required": ClaimType.NEW_TRANSMISSION_REQUIRED_FLAG,
    "accepted_new_substation_required": ClaimType.NEW_SUBSTATION_REQUIRED_FLAG,
    "accepted_onsite_generation_planned": ClaimType.ONSITE_GENERATION_FLAG,
    "accepted_location_state": ClaimType.LOCATION_STATE,
    "accepted_location_county": ClaimType.LOCATION_COUNTY,
}


@dataclass
class LeakageIssue:
    project_id: str
    phase_id: str
    quarter: str
    cutoff_date: str
    issue: str


@dataclass
class AuditResult:
    table_exists: bool
    row_count: int
    target_E1_next_quarter_positive_count: int
    target_E1_within_4q_positive_count: int
    null_or_empty_feature_json_count: int
    duplicate_project_phase_quarter_count: int
    feature_version_counts: dict[str, int]
    top_missing_critical_fields: dict[str, int]
    leakage_issue_count: int
    leakage_issues: list[LeakageIssue]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit generated project_phase_quarter training features.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print machine-readable JSON.")
    parser.add_argument(
        "--max-leakage-details",
        type=int,
        default=20,
        help="Maximum leakage issue details to include in the output.",
    )
    return parser.parse_args()


def parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def feature_is_populated(value: Any) -> bool:
    if value is None:
        return False
    if value is False:
        return False
    if value == "":
        return False
    if isinstance(value, list | dict) and len(value) == 0:
        return False
    return True


def table_exists() -> bool:
    return inspect(engine).has_table(TABLE_NAME)


def load_training_rows(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            f"""
            SELECT
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
            FROM {TABLE_NAME}
            ORDER BY quarter, project_id, phase_id
            """
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def accepted_claim_types_before_cutoff(db: Session, project_id: str, phase_id: str, cutoff: date) -> list[ClaimType]:
    stmt = (
        select(Claim.claim_type)
        .join(Evidence, Claim.evidence_id == Evidence.id)
        .where(
            or_(
                and_(Claim.entity_type == ClaimEntityType.PROJECT, Claim.entity_id == project_id),
                and_(Claim.entity_type == ClaimEntityType.PHASE, Claim.entity_id == phase_id),
            ),
            Claim.review_status == ClaimReviewStatus.ACCEPTED,
            Claim.accepted_at.is_not(None),
            Claim.accepted_at < cutoff,
            or_(Evidence.source_date.is_(None), Evidence.source_date < cutoff),
        )
    )
    return list(db.execute(stmt).scalars().all())


def parse_feature_json(raw: Any) -> tuple[dict[str, Any], bool]:
    if raw is None or raw == "":
        return {}, False
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}, False
    if not isinstance(parsed, dict) or not parsed:
        return {}, False
    return parsed, True


def audit_leakage(
    db: Session,
    row: dict[str, Any],
    features: dict[str, Any],
) -> list[LeakageIssue]:
    project_id = str(row["project_id"])
    phase_id = str(row["phase_id"])
    quarter = str(row["quarter"])
    cutoff_date = str(row["cutoff_date"])
    cutoff = parse_date(cutoff_date)
    accepted_types = accepted_claim_types_before_cutoff(db, project_id, phase_id, cutoff)
    accepted_type_values = sorted(claim_type.value for claim_type in accepted_types)
    accepted_type_set = set(accepted_types)
    issues: list[LeakageIssue] = []

    feature_claim_count = features.get("accepted_claim_count")
    if isinstance(feature_claim_count, int) and feature_claim_count != len(accepted_types):
        issues.append(
            LeakageIssue(
                project_id=project_id,
                phase_id=phase_id,
                quarter=quarter,
                cutoff_date=cutoff_date,
                issue=f"accepted_claim_count={feature_claim_count} but recomputed as-of count={len(accepted_types)}",
            )
        )

    feature_types = features.get("accepted_evidence_claim_types", [])
    if isinstance(feature_types, list):
        unexpected_types = sorted(set(str(value) for value in feature_types) - set(accepted_type_values))
        if unexpected_types:
            issues.append(
                LeakageIssue(
                    project_id=project_id,
                    phase_id=phase_id,
                    quarter=quarter,
                    cutoff_date=cutoff_date,
                    issue=f"accepted_evidence_claim_types includes non-as-of types: {', '.join(unexpected_types)}",
                )
            )

    for feature_name, required_claim_type in FEATURE_CLAIM_REQUIREMENTS.items():
        if feature_is_populated(features.get(feature_name)) and required_claim_type not in accepted_type_set:
            issues.append(
                LeakageIssue(
                    project_id=project_id,
                    phase_id=phase_id,
                    quarter=quarter,
                    cutoff_date=cutoff_date,
                    issue=f"{feature_name} is populated without accepted {required_claim_type.value} before cutoff",
                )
            )

    return issues


def run_audit(max_leakage_details: int) -> AuditResult:
    if not table_exists():
        return AuditResult(
            table_exists=False,
            row_count=0,
            target_E1_next_quarter_positive_count=0,
            target_E1_within_4q_positive_count=0,
            null_or_empty_feature_json_count=0,
            duplicate_project_phase_quarter_count=0,
            feature_version_counts={},
            top_missing_critical_fields={},
            leakage_issue_count=0,
            leakage_issues=[],
        )

    with SessionLocal() as db:
        rows = load_training_rows(db)
        feature_version_counts: Counter[str] = Counter()
        key_counts: Counter[tuple[str, str, str]] = Counter()
        missing_counts: Counter[str] = Counter()
        null_or_empty_count = 0
        leakage_issues: list[LeakageIssue] = []

        for row in rows:
            feature_version_counts[str(row["feature_version"])] += 1
            key_counts[(str(row["project_id"]), str(row["phase_id"]), str(row["quarter"]))] += 1
            features, has_features = parse_feature_json(row["features_as_of_prior_quarter"])
            if not has_features:
                null_or_empty_count += 1
                continue

            missing_fields = features.get("missing_critical_fields", [])
            if isinstance(missing_fields, list):
                for field in missing_fields:
                    if field in CRITICAL_FIELDS:
                        missing_counts[str(field)] += 1

            leakage_issues.extend(audit_leakage(db, row, features))

        duplicate_count = sum(count - 1 for count in key_counts.values() if count > 1)
        sorted_missing = {
            field: count
            for field, count in sorted(missing_counts.items(), key=lambda item: (-item[1], item[0]))
        }

        return AuditResult(
            table_exists=True,
            row_count=len(rows),
            target_E1_next_quarter_positive_count=sum(int(row["target_E1_next_quarter"] or 0) for row in rows),
            target_E1_within_4q_positive_count=sum(int(row["target_E1_within_4q"] or 0) for row in rows),
            null_or_empty_feature_json_count=null_or_empty_count,
            duplicate_project_phase_quarter_count=duplicate_count,
            feature_version_counts=dict(sorted(feature_version_counts.items())),
            top_missing_critical_fields=sorted_missing,
            leakage_issue_count=len(leakage_issues),
            leakage_issues=leakage_issues[:max_leakage_details],
        )


def print_human_summary(result: AuditResult) -> None:
    print("Training Table Audit")
    print("====================")
    print(f"Table exists: {'yes' if result.table_exists else 'no'}")
    if not result.table_exists:
        print(f"Missing table: {TABLE_NAME}")
        return

    print(f"Rows: {result.row_count}")
    print(f"E1 next-quarter positives: {result.target_E1_next_quarter_positive_count}")
    print(f"E1 within-4q positives: {result.target_E1_within_4q_positive_count}")
    print(f"Null/empty feature JSON rows: {result.null_or_empty_feature_json_count}")
    print(f"Duplicate project/phase/quarter rows: {result.duplicate_project_phase_quarter_count}")

    print("\nFeature versions:")
    if result.feature_version_counts:
        for version, count in result.feature_version_counts.items():
            print(f"  {version}: {count}")
    else:
        print("  none")

    print("\nTop missing critical fields:")
    if result.top_missing_critical_fields:
        for field, count in result.top_missing_critical_fields.items():
            print(f"  {field}: {count}")
    else:
        print("  none")

    print("\nLeakage sanity check:")
    print(f"  Issues: {result.leakage_issue_count}")
    for issue in result.leakage_issues:
        print(f"  - {issue.project_id} / {issue.phase_id} / {issue.quarter}: {issue.issue}")


def main() -> None:
    args = parse_args()
    result = run_audit(max_leakage_details=args.max_leakage_details)
    if args.json_output:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print_human_summary(result)


if __name__ == "__main__":
    main()
