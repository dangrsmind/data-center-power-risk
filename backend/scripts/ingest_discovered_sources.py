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


DEFAULT_CSV_PATH       = REPO_DIR / "data" / "starter_sources" / "discovered_sources_v0_1.csv"
DEFAULT_DECISIONS_PATH = REPO_DIR / "data" / "starter_sources" / "discovery_decisions_v0_1.json"
REQUIRED_COLUMNS = [
    "discovery_id",
    "candidate_project_name",
    "developer",
    "state",
    "county",
    "source_url",
    "source_type",
    "source_date",
    "title",
    "extracted_text",
    "detected_load_mw",
    "detected_region",
    "detected_utility",
    "confidence",
    "requires_review_reason",
    "discovery_method",
    "retrieved_at",
]
SAFE_AUTO_ACCEPT_TYPES = {
    ClaimType.DEVELOPER_NAMED,
    ClaimType.LOCATION_STATE,
    ClaimType.LOCATION_COUNTY,
}
REVIEWER = "discovered_sources_ingest"


@dataclass
class DiscoveredRow:
    row_number: int
    discovery_id: str
    candidate_project_name: str | None
    developer: str | None
    state: str | None
    county: str | None
    source_url: str | None
    source_type: SourceType
    source_date: date | None
    title: str | None
    extracted_text: str | None
    detected_load_mw: float | None
    detected_region: str | None
    detected_utility: str | None
    confidence: str | None
    requires_review_reason: str | None
    discovery_method: str | None
    retrieved_at: str | None

    @property
    def canonical_name_for_ingest(self) -> str:
        return self.candidate_project_name or f"Discovery Review {self.discovery_id}"


@dataclass
class RowIssue:
    row_number: int
    discovery_id: str | None
    candidate_project_name: str | None
    reason: str


@dataclass
class Summary:
    created_projects: int = 0
    updated_projects: int = 0
    evidence_created: int = 0
    claims_created: int = 0
    claims_auto_accepted: int = 0
    claims_left_for_review: int = 0
    skipped_rows: list[RowIssue] = field(default_factory=list)
    rejected_rows: list[RowIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest discovered starter source drafts into the local review workflow.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help=f"Discovered sources CSV path. Defaults to {DEFAULT_CSV_PATH}.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize without writing to the database.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of ingestable rows to process.")
    parser.add_argument("--allow-existing", action="store_true", help="Allow ingest into a database that already contains rows.")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Ingest rows missing project name or state as explicit review-only candidates.",
    )
    parser.add_argument(
        "--ignore-decisions",
        action="store_true",
        help=(
            "Skip the decisions file and ingest all qualifying rows. "
            "By default only rows with approved discovery_ids are ingested "
            "when a decisions file exists."
        ),
    )
    return parser.parse_args()


def resolve_repo_relative(path: Path) -> Path:
    if path.exists() or path.is_absolute():
        return path
    repo_relative = REPO_DIR / path
    return repo_relative if repo_relative.exists() else path


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
        return SourceType.OTHER
    try:
        return SourceType(text)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in SourceType)
        raise ValueError(f"source_type must be one of: {allowed}") from exc


def validate_header(fieldnames: list[str] | None) -> None:
    if not fieldnames:
        raise SystemExit("Discovered sources CSV is missing a header row.")
    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise SystemExit(f"Discovered sources CSV is missing required columns: {', '.join(missing)}")


def parse_row(row_number: int, raw: dict[str, Any]) -> DiscoveredRow:
    discovery_id = clean_string(raw.get("discovery_id"))
    if discovery_id is None:
        raise ValueError("discovery_id is required")
    return DiscoveredRow(
        row_number=row_number,
        discovery_id=discovery_id,
        candidate_project_name=clean_string(raw.get("candidate_project_name")),
        developer=clean_string(raw.get("developer")),
        state=(clean_string(raw.get("state")) or "").upper() or None,
        county=clean_string(raw.get("county")),
        source_url=clean_string(raw.get("source_url")),
        source_type=parse_source_type(raw.get("source_type")),
        source_date=parse_date(raw.get("source_date"), "source_date"),
        title=clean_string(raw.get("title")),
        extracted_text=clean_string(raw.get("extracted_text")),
        detected_load_mw=parse_float(raw.get("detected_load_mw"), "detected_load_mw"),
        detected_region=clean_string(raw.get("detected_region")),
        detected_utility=clean_string(raw.get("detected_utility")),
        confidence=clean_string(raw.get("confidence")),
        requires_review_reason=clean_string(raw.get("requires_review_reason")),
        discovery_method=clean_string(raw.get("discovery_method")),
        retrieved_at=clean_string(raw.get("retrieved_at")),
    )


def row_skip_reason(row: DiscoveredRow, allow_partial: bool) -> str | None:
    if allow_partial:
        return None
    missing = []
    if not row.candidate_project_name:
        missing.append("candidate_project_name")
    if not row.state:
        missing.append("state")
    if missing:
        return "missing " + ", ".join(missing)
    if not row.extracted_text:
        return "missing extracted_text"
    if not row.source_url:
        return "missing source_url"
    return None


def load_rows(path: Path, limit: int | None, allow_partial: bool, summary: Summary) -> list[DiscoveredRow]:
    if not path.exists():
        raise SystemExit(f"Discovered sources CSV not found: {path}")

    selected: list[DiscoveredRow] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        validate_header(reader.fieldnames)
        for row_number, raw in enumerate(reader, start=2):
            try:
                row = parse_row(row_number, raw)
            except ValueError as exc:
                summary.rejected_rows.append(
                    RowIssue(
                        row_number=row_number,
                        discovery_id=clean_string(raw.get("discovery_id")),
                        candidate_project_name=clean_string(raw.get("candidate_project_name")),
                        reason=str(exc),
                    )
                )
                continue
            skip_reason = row_skip_reason(row, allow_partial)
            if skip_reason:
                summary.skipped_rows.append(
                    RowIssue(
                        row_number=row.row_number,
                        discovery_id=row.discovery_id,
                        candidate_project_name=row.candidate_project_name,
                        reason=skip_reason,
                    )
                )
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


def metadata_for_row(row: DiscoveredRow) -> dict[str, Any]:
    return {
        "starter_dataset_version": "v0.1",
        "source": "discovered_sources_v0_1",
        "discovery_id": row.discovery_id,
        "developer": row.developer,
        "state": row.state,
        "county": row.county,
        "detected_load_mw": row.detected_load_mw,
        "detected_region": row.detected_region,
        "detected_utility": row.detected_utility,
        "confidence": row.confidence,
        "requires_review_reason": row.requires_review_reason,
        "discovery_method": row.discovery_method,
        "retrieved_at": row.retrieved_at,
        "source_url": row.source_url,
        "source_type": row.source_type.value,
        "source_date": row.source_date.isoformat() if row.source_date else None,
    }


def merge_metadata(existing: dict | list | None, incoming: dict[str, Any]) -> dict[str, Any] | None:
    base = existing.copy() if isinstance(existing, dict) else {}
    for key, value in incoming.items():
        if value is not None:
            base[key] = value
    return base or None


def find_project(db, canonical_name: str) -> Project | None:
    return db.scalar(select(Project).where(Project.canonical_name == canonical_name))


def create_or_update_project(db, row: DiscoveredRow) -> tuple[Project, str]:
    canonical_name = row.canonical_name_for_ingest
    project = find_project(db, canonical_name)
    incoming_metadata = metadata_for_row(row)
    if project is None:
        project = Project(
            canonical_name=canonical_name,
            developer=None,
            operator=None,
            state=None,
            county=None,
            latitude=None,
            longitude=None,
            lifecycle_state=LifecycleState.CANDIDATE_UNVERIFIED,
            candidate_metadata_json=incoming_metadata,
        )
        db.add(project)
        db.flush()
        return project, "created"

    merged_metadata = merge_metadata(project.candidate_metadata_json, incoming_metadata)
    if merged_metadata != (project.candidate_metadata_json or None):
        project.candidate_metadata_json = merged_metadata
        db.flush()
        return project, "updated"
    return project, "skipped"


def safe_structured_claims(row: DiscoveredRow) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    if row.candidate_project_name:
        claims.append(
            {
                "claim_type": ClaimType.PROJECT_NAME_MENTION,
                "claim_value": {"project_name": row.candidate_project_name},
                "confidence": row.confidence or "medium",
                "claim_date": row.source_date,
            }
        )
    if row.developer:
        claims.append(
            {
                "claim_type": ClaimType.DEVELOPER_NAMED,
                "claim_value": {"developer_name": row.developer},
                "confidence": row.confidence or "medium",
                "claim_date": row.source_date,
            }
        )
    if row.state:
        claims.append(
            {
                "claim_type": ClaimType.LOCATION_STATE,
                "claim_value": {"state": row.state},
                "confidence": row.confidence or "medium",
                "claim_date": row.source_date,
            }
        )
    if row.county:
        claims.append(
            {
                "claim_type": ClaimType.LOCATION_COUNTY,
                "claim_value": {"county": row.county},
                "confidence": row.confidence or "medium",
                "claim_date": row.source_date,
            }
        )
    return claims


def claim_key(claim: Any) -> tuple[str, str]:
    claim_type = claim.claim_type.value if isinstance(claim.claim_type, ClaimType) else str(claim.claim_type)
    return claim_type, json.dumps(claim.claim_value.model_dump(), sort_keys=True)


def build_claim_request(row: DiscoveredRow, project_id) -> EvidenceClaimsCreateRequest:
    packet = AutomationService().build_intake_packet(
        IntakePacketRequest(
            source_url=row.source_url,
            source_type=row.source_type,
            source_date=row.source_date,
            title=row.title,
            evidence_text=row.extracted_text or "",
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


def should_auto_accept_claim(row: DiscoveredRow, claim: Any) -> bool:
    claim_value = claim.claim_value if isinstance(claim.claim_value, dict) else claim.claim_value.model_dump()
    if claim.claim_type == ClaimType.DEVELOPER_NAMED:
        return bool(row.developer) and clean_string(claim_value.get("developer_name")) == row.developer
    if claim.claim_type == ClaimType.LOCATION_STATE:
        return bool(row.state) and clean_string(claim_value.get("state")) == row.state
    if claim.claim_type == ClaimType.LOCATION_COUNTY:
        return bool(row.county) and clean_string(claim_value.get("county")) == row.county
    return False


def create_evidence(service: IngestionService, row: DiscoveredRow):
    return service.create_evidence(
        EvidenceCreateRequest(
            source_type=row.source_type,
            source_date=row.source_date,
            source_url=row.source_url,
            source_rank=1,
            title=row.title,
            extracted_text=row.extracted_text,
            reviewer_status=ReviewerStatus.PENDING,
        )
    )


def auto_accept_safe_claims(service: IngestionService, project_id, row: DiscoveredRow, claims: list[Any]) -> int:
    accepted = 0
    for claim in claims:
        if claim.claim_type not in SAFE_AUTO_ACCEPT_TYPES or not should_auto_accept_claim(row, claim):
            continue
        service.link_claim(claim.claim_id, ClaimLinkRequest(project_id=project_id))
        service.review_claim(
            claim.claim_id,
            ClaimReviewRequest(
                review_status=ClaimReviewStatus.ACCEPTED_CANDIDATE,
                reviewer=REVIEWER,
                notes="Auto-accepted from discovered source; safe project-level claim only.",
                is_contradictory=False,
            ),
        )
        service.accept_claim(
            claim.claim_id,
            ClaimAcceptRequest(
                accepted_by=REVIEWER,
                notes="Accepted during discovered source ingest.",
            ),
        )
        accepted += 1
    return accepted


def dry_run_summary(rows: list[DiscoveredRow], summary: Summary) -> Summary:
    for row in rows:
        request = build_claim_request(row, project_id=None)
        safe_count = sum(1 for claim in request.claims if should_auto_accept_claim(row, claim))
        summary.created_projects += 1
        summary.evidence_created += 1
        summary.claims_created += len(request.claims)
        summary.claims_auto_accepted += safe_count
        summary.claims_left_for_review += len(request.claims) - safe_count
    return summary


def ingest_rows(rows: list[DiscoveredRow], summary: Summary) -> Summary:
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

            accepted_count = auto_accept_safe_claims(service, project.id, row, created_claims)
            summary.claims_auto_accepted += accepted_count
            summary.claims_left_for_review += len(created_claims) - accepted_count

            db.flush()
        db.commit()
    return summary


def load_decisions(path: Path) -> dict[str, set[str]]:
    """Load persisted discovery decisions. Returns sets of approved and rejected IDs."""
    if not path.exists():
        return {"approved": set(), "rejected": set()}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {
        "approved": set(data.get("approved", [])),
        "rejected": set(data.get("rejected", [])),
    }


def apply_decisions(
    rows: list[DiscoveredRow],
    decisions: dict[str, set[str]],
    summary: Summary,
) -> list[DiscoveredRow]:
    """Filter rows to only those explicitly approved. Unapproved rows are recorded as skipped."""
    approved = decisions["approved"]
    kept: list[DiscoveredRow] = []
    for row in rows:
        if row.discovery_id in approved:
            kept.append(row)
        else:
            summary.skipped_rows.append(
                RowIssue(
                    row_number=row.row_number,
                    discovery_id=row.discovery_id,
                    candidate_project_name=row.candidate_project_name,
                    reason="not in approved decisions — run /discover UI or use --ignore-decisions",
                )
            )
    return kept


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 0:
        raise SystemExit("--limit must be non-negative.")

    args.csv = resolve_repo_relative(args.csv)
    summary = Summary()
    rows = load_rows(args.csv, args.limit, args.allow_partial, summary)

    # Filter to approved rows only unless --ignore-decisions is set
    if not args.ignore_decisions:
        decisions = load_decisions(DEFAULT_DECISIONS_PATH)
        has_decisions = bool(decisions["approved"] or decisions["rejected"])
        if has_decisions:
            before = len(rows)
            rows = apply_decisions(rows, decisions, summary)
            print(
                f"[decisions] decisions file found: {len(rows)} approved, "
                f"{before - len(rows)} not approved (skipped).",
                file=sys.stderr,
            )
        else:
            print(
                "[decisions] No decisions file found or file is empty — "
                "ingesting all qualifying rows. Use the Discover UI to approve rows first.",
                file=sys.stderr,
            )
    else:
        print("[decisions] --ignore-decisions flag set — ingesting all qualifying rows.", file=sys.stderr)

    if args.dry_run:
        summary = dry_run_summary(rows, summary)
    else:
        assert_db_empty_unless_allowed(args.allow_existing)
        summary = ingest_rows(rows, summary)

    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
