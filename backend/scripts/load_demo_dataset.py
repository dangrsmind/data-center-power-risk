from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal  # noqa: E402
from app.core.enums import LifecycleState  # noqa: E402
from app.models.project import Project, ProjectCoordinateHistory  # noqa: E402


DEMO_DATASET_ID = "demo_projects_v0_1"
DEFAULT_CSV_PATH = REPO_DIR / "data" / "demo" / "demo_projects_v0_1.csv"
REQUIRED_COLUMNS = [
    "canonical_name",
    "developer",
    "project_type",
    "city",
    "county",
    "state",
    "utility",
    "iso_region",
    "load_mw",
    "load_bucket",
    "announced_date",
    "expected_online_date",
    "lifecycle_state",
    "source_url",
    "source_title",
    "source_type",
    "evidence_excerpt",
    "latitude",
    "longitude",
    "coordinate_status",
    "coordinate_precision",
    "coordinate_source",
    "coordinate_confidence",
    "coordinate_notes",
]


@dataclass
class DemoRow:
    row_number: int
    canonical_name: str
    developer: str | None
    project_type: str | None
    city: str | None
    county: str | None
    state: str
    utility: str | None
    iso_region: str | None
    load_mw: float | None
    load_bucket: str | None
    announced_date: date | None
    expected_online_date: date | None
    lifecycle_state: LifecycleState
    source_url: str | None
    source_title: str | None
    source_type: str | None
    evidence_excerpt: str | None
    latitude: float | None
    longitude: float | None
    coordinate_status: str | None
    coordinate_precision: str | None
    coordinate_source: str | None
    coordinate_confidence: float | None
    coordinate_notes: str | None

    @property
    def key(self) -> tuple[str, str]:
        return (self.canonical_name.casefold(), self.state.upper())


@dataclass
class ValidationError:
    row_number: int
    canonical_name: str | None
    reason: str


@dataclass
class LoadSummary:
    rows_read: int = 0
    projects_created: int = 0
    projects_updated: int = 0
    rows_skipped: int = 0
    validation_errors: list[ValidationError] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["validation_errors"] = [asdict(error) for error in self.validation_errors]
        return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load the reproducible real-data demo project dataset.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help=f"Demo CSV path. Defaults to {DEFAULT_CSV_PATH}.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete demo-owned project rows from this CSV before reloading.",
    )
    return parser.parse_args()


def clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


_COORDINATE_SOURCE_ALIASES: dict[str, str] = {
    "manual_capture": "manual_review",
    "starter_dataset": "imported_dataset",
}


def _normalize_coordinate_source(value: str | None) -> str | None:
    if value is None:
        return None
    return _COORDINATE_SOURCE_ALIASES.get(value, value)


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


def parse_lifecycle_state(value: Any) -> LifecycleState:
    text = clean_string(value)
    if text is None:
        return LifecycleState.CANDIDATE_UNVERIFIED
    try:
        return LifecycleState(text)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in LifecycleState)
        raise ValueError(f"lifecycle_state must be one of: {allowed}") from exc


def validate_header(fieldnames: list[str] | None) -> None:
    if not fieldnames:
        raise SystemExit("Demo CSV is missing a header row.")
    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise SystemExit(f"Demo CSV is missing required columns: {', '.join(missing)}")


def parse_row(row_number: int, raw: dict[str, Any]) -> DemoRow:
    canonical_name = clean_string(raw.get("canonical_name"))
    state = clean_string(raw.get("state"))
    if canonical_name is None:
        raise ValueError("canonical_name is required")
    if state is None:
        raise ValueError("state is required")

    latitude = parse_float(raw.get("latitude"), "latitude")
    longitude = parse_float(raw.get("longitude"), "longitude")
    if (latitude is None) != (longitude is None):
        raise ValueError("latitude and longitude must both be present or both blank")
    if latitude is not None and not -90 <= latitude <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if longitude is not None and not -180 <= longitude <= 180:
        raise ValueError("longitude must be between -180 and 180")

    coordinate_confidence = parse_float(raw.get("coordinate_confidence"), "coordinate_confidence")
    if coordinate_confidence is not None and not 0 <= coordinate_confidence <= 1:
        raise ValueError("coordinate_confidence must be between 0 and 1")

    return DemoRow(
        row_number=row_number,
        canonical_name=canonical_name,
        developer=clean_string(raw.get("developer")),
        project_type=clean_string(raw.get("project_type")),
        city=clean_string(raw.get("city")),
        county=clean_string(raw.get("county")),
        state=state.upper(),
        utility=clean_string(raw.get("utility")),
        iso_region=clean_string(raw.get("iso_region")),
        load_mw=parse_float(raw.get("load_mw"), "load_mw"),
        load_bucket=clean_string(raw.get("load_bucket")),
        announced_date=parse_date(raw.get("announced_date"), "announced_date"),
        expected_online_date=parse_date(raw.get("expected_online_date"), "expected_online_date"),
        lifecycle_state=parse_lifecycle_state(raw.get("lifecycle_state")),
        source_url=clean_string(raw.get("source_url")),
        source_title=clean_string(raw.get("source_title")),
        source_type=clean_string(raw.get("source_type")),
        evidence_excerpt=clean_string(raw.get("evidence_excerpt")),
        latitude=latitude,
        longitude=longitude,
        coordinate_status=clean_string(raw.get("coordinate_status")),
        coordinate_precision=clean_string(raw.get("coordinate_precision")),
        coordinate_source=_normalize_coordinate_source(clean_string(raw.get("coordinate_source"))),
        coordinate_confidence=coordinate_confidence,
        coordinate_notes=clean_string(raw.get("coordinate_notes")),
    )


def load_rows(path: Path, summary: LoadSummary) -> list[DemoRow]:
    if not path.exists():
        raise SystemExit(f"Demo CSV not found: {path}")

    rows: list[DemoRow] = []
    seen_keys: set[tuple[str, str]] = set()
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

            if row.key in seen_keys:
                summary.validation_errors.append(
                    ValidationError(
                        row_number=row_number,
                        canonical_name=row.canonical_name,
                        reason="duplicate canonical_name + state in demo CSV",
                    )
                )
                summary.rows_skipped += 1
                continue

            seen_keys.add(row.key)
            rows.append(row)
    return rows


def metadata_for_row(row: DemoRow) -> dict[str, Any]:
    return {
        "demo_dataset_id": DEMO_DATASET_ID,
        "project_type": row.project_type,
        "city": row.city,
        "utility": row.utility,
        "iso_region": row.iso_region,
        "load_mw": row.load_mw,
        "load_bucket": row.load_bucket,
        "expected_online_date": row.expected_online_date.isoformat() if row.expected_online_date else None,
        "source_url": row.source_url,
        "source_title": row.source_title,
        "source_type": row.source_type,
        "evidence_excerpt": row.evidence_excerpt,
    }


def merge_metadata(existing: dict | list | None, incoming: dict[str, Any]) -> dict[str, Any]:
    base = existing.copy() if isinstance(existing, dict) else {}
    for key, value in incoming.items():
        if value is not None:
            base[key] = value
    return base


def find_project(db: Session, row: DemoRow) -> Project | None:
    return db.scalar(
        select(Project).where(
            Project.canonical_name == row.canonical_name,
            Project.state == row.state,
        )
    )


def apply_if_changed(project: Project, attr: str, value: Any) -> bool:
    if value is None:
        return False
    if getattr(project, attr) == value:
        return False
    setattr(project, attr, value)
    return True


def create_or_update_project(db: Session, row: DemoRow) -> str:
    project = find_project(db, row)
    incoming_metadata = metadata_for_row(row)
    now = datetime.now(timezone.utc)

    if project is None:
        project = Project(
            canonical_name=row.canonical_name,
            developer=row.developer,
            state=row.state,
            county=row.county,
            latitude=row.latitude,
            longitude=row.longitude,
            coordinate_status=row.coordinate_status or ("unverified" if row.latitude is not None else "missing"),
            coordinate_precision=row.coordinate_precision,
            coordinate_source=row.coordinate_source,
            coordinate_notes=row.coordinate_notes,
            coordinate_confidence=row.coordinate_confidence,
            coordinate_updated_at=now if row.latitude is not None or row.coordinate_status else None,
            announcement_date=row.announced_date,
            lifecycle_state=row.lifecycle_state,
            candidate_metadata_json=incoming_metadata,
        )
        db.add(project)
        db.flush()
        return "created"

    changed = False
    for attr, value in [
        ("developer", row.developer),
        ("county", row.county),
        ("announcement_date", row.announced_date),
        ("lifecycle_state", row.lifecycle_state),
        ("latitude", row.latitude),
        ("longitude", row.longitude),
        ("coordinate_status", row.coordinate_status),
        ("coordinate_precision", row.coordinate_precision),
        ("coordinate_source", row.coordinate_source),
        ("coordinate_notes", row.coordinate_notes),
        ("coordinate_confidence", row.coordinate_confidence),
    ]:
        changed = apply_if_changed(project, attr, value) or changed

    if row.latitude is not None or row.coordinate_status:
        if project.coordinate_updated_at is None:
            project.coordinate_updated_at = now
            changed = True

    merged_metadata = merge_metadata(project.candidate_metadata_json, incoming_metadata)
    if merged_metadata != (project.candidate_metadata_json or {}):
        project.candidate_metadata_json = merged_metadata
        changed = True

    if changed:
        db.flush()
        return "updated"
    return "skipped"


def is_demo_owned(project: Project) -> bool:
    metadata = project.candidate_metadata_json
    return isinstance(metadata, dict) and metadata.get("demo_dataset_id") == DEMO_DATASET_ID


def reset_demo_rows(db: Session, rows: list[DemoRow]) -> None:
    keys = {row.key for row in rows}
    if not keys:
        return

    candidates = db.scalars(select(Project)).all()
    project_ids = [
        project.id
        for project in candidates
        if project.state
        and (project.canonical_name.casefold(), project.state.upper()) in keys
        and is_demo_owned(project)
    ]
    if not project_ids:
        return

    db.execute(delete(ProjectCoordinateHistory).where(ProjectCoordinateHistory.project_id.in_(project_ids)))
    db.execute(delete(Project).where(Project.id.in_(project_ids)))
    db.flush()


def load_demo_dataset(db: Session, rows: list[DemoRow], summary: LoadSummary, *, reset: bool = False) -> LoadSummary:
    if reset:
        reset_demo_rows(db, rows)

    for row in rows:
        status = create_or_update_project(db, row)
        if status == "created":
            summary.projects_created += 1
        elif status == "updated":
            summary.projects_updated += 1
        else:
            summary.rows_skipped += 1

    db.commit()
    return summary


def main() -> None:
    args = parse_args()
    summary = LoadSummary()
    rows = load_rows(args.csv, summary)

    with SessionLocal() as db:
        summary = load_demo_dataset(db, rows, summary, reset=args.reset)

    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
