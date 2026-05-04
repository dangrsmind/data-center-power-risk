from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import func, select


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal, create_db_and_tables
from app.core.enums import ClaimReviewStatus, ClaimType, LifecycleState, ReviewerStatus, SourceType
from app.models import Base
from app.models.project import Project
from app.schemas.automation import IntakePacketRequest
from app.schemas.ingestion import (
    ClaimAcceptRequest,
    ClaimLinkRequest,
    ClaimReviewRequest,
    EvidenceClaimsCreateRequest,
    EvidenceCreateRequest,
)
from app.services.automation_service import AutomationService
from app.services.ingestion_service import IngestionService


DEFAULT_CSV_PATH = REPO_DIR / "data" / "starter_sources" / "projects_v0_1.csv"
REQUIRED_COLUMNS = [
    "candidate_id",
    "canonical_name",
    "developer",
    "operator",
    "state",
    "county",
    "latitude",
    "longitude",
    "source_url",
    "source_type",
    "source_date",
    "title",
    "evidence_text",
    "known_load_mw",
    "load_note",
    "region_hint",
    "utility_hint",
    "priority_tier",
    "notes",
]
SAFE_AUTO_ACCEPT_TYPES = {
    ClaimType.DEVELOPER_NAMED,
    ClaimType.LOCATION_STATE,
    ClaimType.LOCATION_COUNTY,
}
REVIEWER = "starter_dataset_ingest"


@dataclass
class StarterRow:
    row_number: int
    candidate_id: str | None
    canonical_name: str
    developer: str | None
    operator: str | None
    state: str | None
    county: str | None
    latitude: float | None
    longitude: float | None
    source_url: str
    source_type: SourceType
    source_date: date | None
    title: str
    evidence_text: str
    known_load_mw: float | None
    load_note: str | None
    region_hint: str | None
    utility_hint: str | None
    priority_tier: str | None
    notes: str | None


@dataclass
class RejectedRow:
    row_number: int
    candidate_id: str | None
    canonical_name: str | None
    reason: str


@dataclass
class Summary:
    created_projects: int = 0
    updated_projects: int = 0
    evidence_created: int = 0
    claims_created: int = 0
    claims_auto_accepted: int = 0
    claims_left_for_review: int = 0
    rejected_rows: list[RejectedRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rejected_rows"] = [asdict(row) for row in self.rejected_rows]
        return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest the real-world starter dataset CSV.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help=f"Starter CSV path. Defaults to {DEFAULT_CSV_PATH}.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize without writing to the database.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of accepted CSV rows to process.")
    parser.add_argument("--project-name", help="Only process rows matching this canonical_name, case-insensitive.")
    parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="Allow ingest into a database that already contains rows.",
    )
    return parser.parse_args()


def clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_float(value: Any, field_name: str) -> float | None:
    text = clean_string(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be numeric") from exc


def parse_date(value: Any, field_name: str) -> date | None:
    text = clean_string(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD") from exc


def parse_source_type(value: Any) -> SourceType:
    text = clean_string(value)
    if text is None:
        raise ValueError("source_type is required")
    try:
        return SourceType(text)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in SourceType)
        raise ValueError(f"source_type must be one of: {allowed}") from exc


def validate_header(fieldnames: list[str] | None) -> None:
    if not fieldnames:
        raise SystemExit("Starter CSV is missing a header row.")
    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise SystemExit(f"Starter CSV is missing required columns: {', '.join(missing)}")


def parse_row(row_number: int, raw: dict[str, Any]) -> StarterRow:
    canonical_name = clean_string(raw.get("canonical_name"))
    source_url = clean_string(raw.get("source_url"))
    title = clean_string(raw.get("title"))
    evidence_text = clean_string(raw.get("evidence_text"))
    if canonical_name is None:
        raise ValueError("canonical_name is required")
    if source_url is None:
        raise ValueError("source_url is required")
    if title is None:
        raise ValueError("title is required")
    if evidence_text is None:
        raise ValueError("evidence_text is required")

    state = clean_string(raw.get("state"))
    return StarterRow(
        row_number=row_number,
        candidate_id=clean_string(raw.get("candidate_id")),
        canonical_name=canonical_name,
        developer=clean_string(raw.get("developer")),
        operator=clean_string(raw.get("operator")),
        state=state.upper() if state else None,
        county=clean_string(raw.get("county")),
        latitude=parse_float(raw.get("latitude"), "latitude"),
        longitude=parse_float(raw.get("longitude"), "longitude"),
        source_url=source_url,
        source_type=parse_source_type(raw.get("source_type")),
        source_date=parse_date(raw.get("source_date"), "source_date"),
        title=title,
        evidence_text=evidence_text,
        known_load_mw=parse_float(raw.get("known_load_mw"), "known_load_mw"),
        load_note=clean_string(raw.get("load_note")),
        region_hint=clean_string(raw.get("region_hint")),
        utility_hint=clean_string(raw.get("utility_hint")),
        priority_tier=clean_string(raw.get("priority_tier")),
        notes=clean_string(raw.get("notes")),
    )


def load_rows(path: Path, project_name: str | None, limit: int | None, summary: Summary) -> list[StarterRow]:
    if not path.exists():
        raise SystemExit(f"Starter CSV not found: {path}")

    selected: list[StarterRow] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        validate_header(reader.fieldnames)
        for row_number, raw in enumerate(reader, start=2):
            try:
                row = parse_row(row_number, raw)
            except ValueError as exc:
                summary.rejected_rows.append(
                    RejectedRow(
                        row_number=row_number,
                        candidate_id=clean_string(raw.get("candidate_id")),
                        canonical_name=clean_string(raw.get("canonical_name")),
                        reason=str(exc),
                    )
                )
                continue

            if project_name and row.canonical_name.casefold() != project_name.casefold():
                continue
            selected.append(row)
            if limit is not None and len(selected) >= limit:
                break
    return selected


def assert_db_empty_unless_allowed(allow_existing: bool) -> None:
    if allow_existing:
        return
    create_db_and_tables()
    non_empty: list[str] = []
    with SessionLocal() as db:
        for table in Base.metadata.sorted_tables:
            count = db.scalar(select(func.count()).select_from(table)) or 0
            if count:
                non_empty.append(f"{table.name}={count}")
    if non_empty:
        raise SystemExit(
            "Refusing to ingest into a non-empty database. "
            f"Use --allow-existing to override. Non-empty tables: {', '.join(non_empty)}"
        )


def metadata_for_row(row: StarterRow) -> dict[str, Any]:
    return {
        "starter_dataset_version": "v0.1",
        "candidate_id": row.candidate_id,
        "developer": row.developer,
        "operator": row.operator,
        "state": row.state,
        "county": row.county,
        "known_load_mw": row.known_load_mw,
        "load_note": row.load_note,
        "region_hint": row.region_hint,
        "utility_hint": row.utility_hint,
        "priority_tier": row.priority_tier,
        "source_url": row.source_url,
        "source_type": row.source_type.value,
        "source_date": row.source_date.isoformat() if row.source_date else None,
        "notes": row.notes,
    }


def merge_metadata(existing: dict | list | None, incoming: dict[str, Any]) -> dict[str, Any] | None:
    base = existing.copy() if isinstance(existing, dict) else {}
    for key, value in incoming.items():
        if value is not None:
            base[key] = value
    return base or None


def find_project(db, canonical_name: str) -> Project | None:
    return db.scalar(select(Project).where(Project.canonical_name == canonical_name))


def create_or_update_project(db, row: StarterRow) -> tuple[Project, str]:
    project = find_project(db, row.canonical_name)
    incoming_metadata = metadata_for_row(row)
    if project is None:
        project = Project(
            canonical_name=row.canonical_name,
            developer=None,
            operator=None,
            state=None,
            county=None,
            latitude=row.latitude,
            longitude=row.longitude,
            lifecycle_state=LifecycleState.CANDIDATE_UNVERIFIED,
            candidate_metadata_json=incoming_metadata,
        )
        db.add(project)
        db.flush()
        return project, "created"

    changed = False
    for attr in ["latitude", "longitude"]:
        value = getattr(row, attr)
        if value is not None and getattr(project, attr) != value:
            setattr(project, attr, value)
            changed = True

    merged_metadata = merge_metadata(project.candidate_metadata_json, incoming_metadata)
    if merged_metadata != (project.candidate_metadata_json or None):
        project.candidate_metadata_json = merged_metadata
        changed = True

    if changed:
        db.flush()
        return project, "updated"
    return project, "skipped"


def safe_structured_claims(row: StarterRow) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = [
        {
            "claim_type": ClaimType.PROJECT_NAME_MENTION,
            "claim_value": {"project_name": row.canonical_name},
            "confidence": "high",
            "claim_date": row.source_date,
        }
    ]
    if row.developer:
        claims.append(
            {
                "claim_type": ClaimType.DEVELOPER_NAMED,
                "claim_value": {"developer_name": row.developer},
                "confidence": "high",
                "claim_date": row.source_date,
            }
        )
    if row.state:
        claims.append(
            {
                "claim_type": ClaimType.LOCATION_STATE,
                "claim_value": {"state": row.state},
                "confidence": "high",
                "claim_date": row.source_date,
            }
        )
    if row.county:
        claims.append(
            {
                "claim_type": ClaimType.LOCATION_COUNTY,
                "claim_value": {"county": row.county},
                "confidence": "high",
                "claim_date": row.source_date,
            }
        )
    return claims


def claim_key(claim: Any) -> tuple[str, str]:
    claim_type = claim.claim_type.value if isinstance(claim.claim_type, ClaimType) else str(claim.claim_type)
    return claim_type, json.dumps(claim.claim_value.model_dump(), sort_keys=True)


def build_claim_request(row: StarterRow, project_id) -> EvidenceClaimsCreateRequest:
    packet = AutomationService().build_intake_packet(
        IntakePacketRequest(
            source_url=row.source_url,
            source_type=row.source_type,
            source_date=row.source_date,
            title=row.title,
            evidence_text=row.evidence_text,
            project_id=project_id,
        )
    )

    claims = list(packet.claims_payload.claims)
    existing_keys = {claim_key(claim) for claim in claims}
    for raw_claim in safe_structured_claims(row):
        candidate = EvidenceClaimsCreateRequest(claims=[raw_claim]).claims[0]
        key = claim_key(candidate)
        if key not in existing_keys:
            claims.append(candidate)
            existing_keys.add(key)
    return EvidenceClaimsCreateRequest(claims=claims)


def create_evidence(service: IngestionService, row: StarterRow):
    return service.create_evidence(
        EvidenceCreateRequest(
            source_type=row.source_type,
            source_date=row.source_date,
            source_url=row.source_url,
            source_rank=1,
            title=row.title,
            extracted_text=row.evidence_text,
            reviewer_status=ReviewerStatus.PENDING,
        )
    )


def auto_accept_safe_claims(service: IngestionService, project_id, claims: list[Any]) -> int:
    accepted = 0
    for claim in claims:
        if claim.claim_type not in SAFE_AUTO_ACCEPT_TYPES:
            continue
        service.link_claim(claim.claim_id, ClaimLinkRequest(project_id=project_id))
        service.review_claim(
            claim.claim_id,
            ClaimReviewRequest(
                review_status=ClaimReviewStatus.ACCEPTED_CANDIDATE,
                reviewer=REVIEWER,
                notes="Auto-accepted by starter dataset ingest; safe project-level claim only.",
                is_contradictory=False,
            ),
        )
        service.accept_claim(
            claim.claim_id,
            ClaimAcceptRequest(
                accepted_by=REVIEWER,
                notes="Accepted during starter dataset v0.1 ingest.",
            ),
        )
        accepted += 1
    return accepted


def dry_run_summary(rows: list[StarterRow], summary: Summary) -> Summary:
    for row in rows:
        request = build_claim_request(row, project_id=None)
        safe_count = sum(1 for claim in request.claims if claim.claim_type in SAFE_AUTO_ACCEPT_TYPES)
        summary.created_projects += 1
        summary.evidence_created += 1
        summary.claims_created += len(request.claims)
        summary.claims_auto_accepted += safe_count
        summary.claims_left_for_review += len(request.claims) - safe_count
    return summary


def ingest_rows(rows: list[StarterRow], summary: Summary) -> Summary:
    create_db_and_tables()
    with SessionLocal() as db:
        for row in rows:
            project, status = create_or_update_project(db, row)
            if status == "created":
                summary.created_projects += 1
            elif status == "updated":
                summary.updated_projects += 1

            service = IngestionService(db)
            evidence = create_evidence(service, row)
            summary.evidence_created += 1

            claim_request = build_claim_request(row, project.id)
            created_claims = service.create_claims(evidence.evidence_id, claim_request).created_claims
            summary.claims_created += len(created_claims)

            accepted_count = auto_accept_safe_claims(service, project.id, created_claims)
            summary.claims_auto_accepted += accepted_count
            summary.claims_left_for_review += len(created_claims) - accepted_count

            db.flush()
        db.commit()
    return summary


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 0:
        raise SystemExit("--limit must be non-negative.")

    summary = Summary()
    rows = load_rows(args.csv, args.project_name, args.limit, summary)
    assert_db_empty_unless_allowed(args.allow_existing)

    if args.dry_run:
        summary = dry_run_summary(rows, summary)
    else:
        summary = ingest_rows(rows, summary)

    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
