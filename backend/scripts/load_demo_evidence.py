from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal  # noqa: E402
from app.core.enums import ClaimEntityType, ClaimReviewStatus, ClaimType, ReviewerStatus, SourceType  # noqa: E402
from app.models.evidence import Claim, Evidence, FieldProvenance  # noqa: E402
from app.models.project import Project  # noqa: E402


DEFAULT_CSV_PATH = REPO_DIR / "data" / "demo" / "demo_evidence_v0_1.csv"
REQUIRED_COLUMNS = [
    "canonical_name",
    "state",
    "evidence_type",
    "source_url",
    "source_title",
    "source_publisher",
    "published_date",
    "evidence_excerpt",
    "claim_type",
    "claim_value",
    "confidence",
    "notes",
]
INTERNAL_NOTE_TYPES = {"internal_note", "other"}

CLAIM_VALUE_KEYS = {
    ClaimType.PROJECT_NAME_MENTION: "project_name",
    ClaimType.DEVELOPER_NAMED: "developer_name",
    ClaimType.OPERATOR_NAMED: "operator_name",
    ClaimType.LOCATION_STATE: "state",
    ClaimType.LOCATION_COUNTY: "county",
    ClaimType.UTILITY_NAMED: "utility_name",
    ClaimType.REGION_OR_RTO_NAMED: "region_name",
    ClaimType.MODELED_LOAD_MW: "modeled_primary_load_mw",
    ClaimType.OPTIONAL_EXPANSION_MW: "optional_expansion_mw",
    ClaimType.ANNOUNCEMENT_DATE: "announcement_date",
    ClaimType.TARGET_ENERGIZATION_DATE: "target_energization_date",
    ClaimType.LATEST_UPDATE_DATE: "latest_update_date",
}
FIELD_NAMES = {
    ClaimType.PROJECT_NAME_MENTION: "canonical_name",
    ClaimType.DEVELOPER_NAMED: "developer",
    ClaimType.OPERATOR_NAMED: "operator",
    ClaimType.LOCATION_STATE: "state",
    ClaimType.LOCATION_COUNTY: "county",
    ClaimType.UTILITY_NAMED: "utility_id",
    ClaimType.REGION_OR_RTO_NAMED: "region_id",
    ClaimType.MODELED_LOAD_MW: "modeled_primary_load_mw",
    ClaimType.OPTIONAL_EXPANSION_MW: "optional_expansion_mw",
    ClaimType.ANNOUNCEMENT_DATE: "announcement_date",
    ClaimType.TARGET_ENERGIZATION_DATE: "target_energization_date",
    ClaimType.LATEST_UPDATE_DATE: "latest_update_date",
}


@dataclass
class DemoEvidenceRow:
    row_number: int
    canonical_name: str
    state: str
    evidence_type: SourceType
    source_url: str | None
    source_title: str | None
    source_publisher: str | None
    published_date: date | None
    evidence_excerpt: str | None
    claim_type: ClaimType
    claim_value: dict[str, Any]
    confidence: float | None
    notes: str | None


@dataclass
class ValidationError:
    row_number: int
    canonical_name: str | None
    reason: str


@dataclass
class LoadSummary:
    rows_read: int = 0
    evidence_created: int = 0
    evidence_updated: int = 0
    rows_skipped: int = 0
    validation_errors: list[ValidationError] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["validation_errors"] = [asdict(error) for error in self.validation_errors]
        return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load curated source-backed evidence for demo projects.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help=f"Demo evidence CSV path. Defaults to {DEFAULT_CSV_PATH}.",
    )
    return parser.parse_args()


def clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_date(value: Any, field_name: str) -> date | None:
    text_value = clean_string(value)
    if text_value is None:
        return None
    try:
        return date.fromisoformat(text_value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD") from exc


def parse_confidence(value: Any) -> float | None:
    text_value = clean_string(value)
    if text_value is None:
        return None
    try:
        confidence = float(text_value)
    except ValueError as exc:
        raise ValueError("confidence must be numeric") from exc
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    return confidence


def parse_source_type(value: Any) -> SourceType:
    text_value = clean_string(value)
    if text_value is None:
        raise ValueError("evidence_type is required")
    try:
        return SourceType(text_value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in SourceType)
        raise ValueError(f"evidence_type must be one of: {allowed}") from exc


def parse_claim_type(value: Any) -> ClaimType:
    text_value = clean_string(value)
    if text_value is None:
        raise ValueError("claim_type is required")
    try:
        claim_type = ClaimType(text_value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ClaimType)
        raise ValueError(f"claim_type must be one of: {allowed}") from exc
    if claim_type not in CLAIM_VALUE_KEYS:
        raise ValueError(f"claim_type {claim_type.value!r} is not supported by the demo evidence loader")
    return claim_type


def parse_claim_value(claim_type: ClaimType, raw_value: Any) -> dict[str, Any]:
    text_value = clean_string(raw_value)
    if text_value is None:
        raise ValueError("claim_value is required")
    key = CLAIM_VALUE_KEYS[claim_type]
    if claim_type in {ClaimType.MODELED_LOAD_MW, ClaimType.OPTIONAL_EXPANSION_MW}:
        try:
            return {key: float(text_value)}
        except ValueError as exc:
            raise ValueError("claim_value must be numeric for load claims") from exc
    if claim_type in {
        ClaimType.ANNOUNCEMENT_DATE,
        ClaimType.TARGET_ENERGIZATION_DATE,
        ClaimType.LATEST_UPDATE_DATE,
    }:
        return {key: parse_date(text_value, "claim_value").isoformat()}
    return {key: text_value}


def validate_header(fieldnames: list[str] | None) -> None:
    if not fieldnames:
        raise SystemExit("Demo evidence CSV is missing a header row.")
    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise SystemExit(f"Demo evidence CSV is missing required columns: {', '.join(missing)}")


def parse_row(row_number: int, raw: dict[str, Any]) -> DemoEvidenceRow:
    canonical_name = clean_string(raw.get("canonical_name"))
    state = clean_string(raw.get("state"))
    if canonical_name is None:
        raise ValueError("canonical_name is required")
    if state is None:
        raise ValueError("state is required")

    source_type = parse_source_type(raw.get("evidence_type"))
    source_url = clean_string(raw.get("source_url"))
    if source_url is None and source_type.value not in INTERNAL_NOTE_TYPES:
        raise ValueError("source_url is required unless evidence_type allows internal notes")

    claim_type = parse_claim_type(raw.get("claim_type"))
    return DemoEvidenceRow(
        row_number=row_number,
        canonical_name=canonical_name,
        state=state.upper(),
        evidence_type=source_type,
        source_url=source_url,
        source_title=clean_string(raw.get("source_title")),
        source_publisher=clean_string(raw.get("source_publisher")),
        published_date=parse_date(raw.get("published_date"), "published_date"),
        evidence_excerpt=clean_string(raw.get("evidence_excerpt")),
        claim_type=claim_type,
        claim_value=parse_claim_value(claim_type, raw.get("claim_value")),
        confidence=parse_confidence(raw.get("confidence")),
        notes=clean_string(raw.get("notes")),
    )


def load_rows(path: Path, summary: LoadSummary) -> list[DemoEvidenceRow]:
    if not path.exists():
        raise SystemExit(f"Demo evidence CSV not found: {path}")

    rows: list[DemoEvidenceRow] = []
    seen_keys: set[tuple[str, str, str | None, str]] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        validate_header(reader.fieldnames)
        for row_number, raw in enumerate(reader, start=2):
            summary.rows_read += 1
            try:
                row = parse_row(row_number, raw)
            except ValueError as exc:
                summary.validation_errors.append(
                    ValidationError(
                        row_number=row_number,
                        canonical_name=clean_string(raw.get("canonical_name")),
                        reason=str(exc),
                    )
                )
                summary.rows_skipped += 1
                continue

            key = (row.canonical_name.casefold(), row.state, row.source_url, row.claim_type.value)
            if key in seen_keys:
                summary.validation_errors.append(
                    ValidationError(
                        row_number=row.row_number,
                        canonical_name=row.canonical_name,
                        reason="duplicate canonical_name + state + source_url + claim_type in demo evidence CSV",
                    )
                )
                summary.rows_skipped += 1
                continue
            seen_keys.add(key)
            rows.append(row)
    return rows


def find_project(db: Session, row: DemoEvidenceRow) -> Project | None:
    return db.scalar(
        select(Project).where(
            Project.canonical_name == row.canonical_name,
            Project.state == row.state,
        )
    )


def find_claim(db: Session, project: Project, row: DemoEvidenceRow) -> Claim | None:
    return db.scalar(
        select(Claim)
        .join(Evidence, Claim.evidence_id == Evidence.id)
        .where(
            Claim.entity_type == ClaimEntityType.PROJECT,
            Claim.entity_id == project.id,
            Claim.claim_type == row.claim_type,
            Evidence.source_url == row.source_url,
        )
        .order_by(Claim.created_at.desc())
    )


def build_extracted_text(row: DemoEvidenceRow) -> str | None:
    return row.evidence_excerpt


def ensure_field_provenance(db: Session, claim: Claim, field_name: str) -> bool:
    existing = db.scalar(
        select(FieldProvenance).where(
            FieldProvenance.entity_type == ClaimEntityType.PROJECT,
            FieldProvenance.entity_id == claim.entity_id,
            FieldProvenance.field_name == field_name,
            FieldProvenance.evidence_id == claim.evidence_id,
            FieldProvenance.claim_id == claim.id,
        )
    )
    if existing is not None:
        return False
    db.add(
        FieldProvenance(
            entity_type=ClaimEntityType.PROJECT,
            entity_id=claim.entity_id,
            field_name=field_name,
            evidence_id=claim.evidence_id,
            claim_id=claim.id,
        )
    )
    return True


def apply_if_changed(target: Any, attr: str, value: Any) -> bool:
    if getattr(target, attr) == value:
        return False
    setattr(target, attr, value)
    return True


def create_or_update_evidence(db: Session, row: DemoEvidenceRow, summary: LoadSummary) -> None:
    project = find_project(db, row)
    if project is None:
        summary.validation_errors.append(
            ValidationError(
                row_number=row.row_number,
                canonical_name=row.canonical_name,
                reason=f"no matching project found for canonical_name={row.canonical_name!r}, state={row.state!r}",
            )
        )
        summary.rows_skipped += 1
        return

    now = datetime.now(timezone.utc)
    confidence_text = str(row.confidence) if row.confidence is not None else None
    extracted_text = build_extracted_text(row)
    claim = find_claim(db, project, row)

    if claim is None:
        evidence = Evidence(
            source_type=row.evidence_type,
            source_date=row.published_date,
            source_url=row.source_url,
            source_rank=None,
            title=row.source_title,
            extracted_text=extracted_text,
            reviewer_status=ReviewerStatus.REVIEWED,
            reviewed_at=now,
            reviewed_by="demo_evidence_loader",
            review_notes=row.notes,
        )
        db.add(evidence)
        db.flush()
        claim = Claim(
            evidence_id=evidence.id,
            entity_type=ClaimEntityType.PROJECT,
            entity_id=project.id,
            claim_type=row.claim_type,
            claim_value_json=row.claim_value,
            claim_date=row.published_date,
            confidence=confidence_text,
            is_contradictory=False,
            review_status=ClaimReviewStatus.ACCEPTED,
            reviewed_at=now,
            reviewed_by="demo_evidence_loader",
            review_notes=row.notes,
            accepted_at=now,
            accepted_by="demo_evidence_loader",
        )
        db.add(claim)
        db.flush()
        ensure_field_provenance(db, claim, FIELD_NAMES[row.claim_type])
        summary.evidence_created += 1
        return

    evidence = db.get(Evidence, claim.evidence_id)
    if evidence is None:
        summary.validation_errors.append(
            ValidationError(
                row_number=row.row_number,
                canonical_name=row.canonical_name,
                reason=f"claim {claim.id} references missing evidence {claim.evidence_id}",
            )
        )
        summary.rows_skipped += 1
        return

    changed = False
    for attr, value in [
        ("source_type", row.evidence_type),
        ("source_date", row.published_date),
        ("source_url", row.source_url),
        ("title", row.source_title),
        ("extracted_text", extracted_text),
        ("reviewer_status", ReviewerStatus.REVIEWED),
        ("reviewed_by", "demo_evidence_loader"),
        ("review_notes", row.notes),
    ]:
        changed = apply_if_changed(evidence, attr, value) or changed
    if evidence.reviewed_at is None:
        evidence.reviewed_at = now
        changed = True

    for attr, value in [
        ("entity_type", ClaimEntityType.PROJECT),
        ("entity_id", project.id),
        ("claim_value_json", row.claim_value),
        ("claim_date", row.published_date),
        ("confidence", confidence_text),
        ("review_status", ClaimReviewStatus.ACCEPTED),
        ("reviewed_by", "demo_evidence_loader"),
        ("review_notes", row.notes),
        ("accepted_by", "demo_evidence_loader"),
    ]:
        changed = apply_if_changed(claim, attr, value) or changed
    if claim.reviewed_at is None:
        claim.reviewed_at = now
        changed = True
    if claim.accepted_at is None:
        claim.accepted_at = now
        changed = True

    changed = ensure_field_provenance(db, claim, FIELD_NAMES[row.claim_type]) or changed
    if changed:
        summary.evidence_updated += 1
    else:
        summary.rows_skipped += 1


def load_demo_evidence(db: Session, rows: list[DemoEvidenceRow], summary: LoadSummary) -> LoadSummary:
    for row in rows:
        create_or_update_evidence(db, row, summary)
    db.commit()
    return summary


def main() -> None:
    args = parse_args()
    summary = LoadSummary()
    rows = load_rows(args.csv, summary)

    with SessionLocal() as db:
        summary = load_demo_evidence(db, rows, summary)

    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
