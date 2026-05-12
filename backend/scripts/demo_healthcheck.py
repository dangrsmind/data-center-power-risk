from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select, text


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import DATABASE_URL, SessionLocal  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.services.prediction_service import PredictionService  # noqa: E402
from app.services.project_service import ProjectService  # noqa: E402


DEMO_DATASET_ID = "demo_projects_v0_1"
DEMO_CSV_PATH = REPO_DIR / "data" / "demo" / "demo_projects_v0_1.csv"
LEGACY_COORDINATE_SOURCES = {"manual_capture", "starter_dataset"}


@dataclass
class HealthcheckSummary:
    projects_checked: int = 0
    projects_with_coordinates: int = 0
    projects_with_evidence: int = 0
    evidence_checked: int = 0
    predictions_checked: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_demo_project(project: Project) -> bool:
    metadata = project.candidate_metadata_json
    return isinstance(metadata, dict) and metadata.get("demo_dataset_id") == DEMO_DATASET_ID


def load_expected_demo_projects(path: Path = DEMO_CSV_PATH) -> dict[tuple[str, str | None], dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = {}
        for row in csv.DictReader(handle):
            canonical_name = clean_text(row.get("canonical_name"))
            if not canonical_name:
                continue
            state = clean_text(row.get("state"))
            rows[(canonical_name, state)] = {
                "canonical_name": canonical_name,
                "state": state,
                "expects_coordinates": bool(clean_text(row.get("latitude")) or clean_text(row.get("longitude"))),
            }
        return rows


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def has_coordinate_pair(project: Project) -> bool:
    return project.latitude is not None and project.longitude is not None


def validate_coordinate_fields(project: Project) -> list[str]:
    label = project_label(project)
    errors: list[str] = []
    has_latitude = project.latitude is not None
    has_longitude = project.longitude is not None

    if has_latitude != has_longitude:
        errors.append(f"{label}: latitude and longitude must both be present or both be absent")
    if project.latitude is not None and not -90 <= project.latitude <= 90:
        errors.append(f"{label}: latitude {project.latitude} is outside [-90, 90]")
    if project.longitude is not None and not -180 <= project.longitude <= 180:
        errors.append(f"{label}: longitude {project.longitude} is outside [-180, 180]")
    if project.coordinate_confidence is not None and not 0 <= project.coordinate_confidence <= 1:
        errors.append(f"{label}: coordinate_confidence {project.coordinate_confidence} is outside [0, 1]")
    if project.coordinate_source in LEGACY_COORDINATE_SOURCES:
        errors.append(f"{label}: legacy coordinate_source {project.coordinate_source!r} is still present")
    return errors


def validate_prediction_payload(prediction: Any, *, label: str) -> list[str]:
    errors: list[str] = []
    payload = prediction.model_dump() if hasattr(prediction, "model_dump") else prediction
    if not isinstance(payload, dict):
        return [f"{label}: prediction response is not an object"]

    if not (payload.get("model") or payload.get("model_name")):
        errors.append(f"{label}: prediction is missing model/model_name")

    probabilities: list[float] = []
    for field_name in ["p_delay_6mo", "p_delay_12mo", "p_delay_18mo"]:
        value = payload.get(field_name)
        if not isinstance(value, (int, float)):
            errors.append(f"{label}: prediction is missing numeric {field_name}")
            continue
        if not 0 <= float(value) <= 1:
            errors.append(f"{label}: {field_name}={value} is outside [0, 1]")
        probabilities.append(float(value))

    if len(probabilities) == 3 and not (probabilities[0] <= probabilities[1] <= probabilities[2]):
        errors.append(f"{label}: prediction probabilities are not monotonic")

    for field_name in ["risk_tier", "confidence"]:
        if clean_text(payload.get(field_name)) is None:
            errors.append(f"{label}: prediction is missing {field_name}")

    drivers = payload.get("drivers")
    if not isinstance(drivers, list) or not drivers:
        errors.append(f"{label}: prediction drivers is empty or missing")

    return errors


def project_label(project: Project) -> str:
    return f"{project.canonical_name} ({project.id})"


def validate_demo_project(
    project: Project,
    expected: dict[tuple[str, str | None], dict[str, Any]],
    prediction_service: PredictionService,
) -> tuple[list[str], list[str]]:
    label = project_label(project)
    errors: list[str] = []
    warnings: list[str] = []

    if project.id is None:
        errors.append(f"{label}: missing id")
    if clean_text(project.canonical_name) is None:
        errors.append(f"{label}: missing canonical_name")
    if clean_text(project.state) is None:
        errors.append(f"{label}: missing state")

    expected_row = expected.get((project.canonical_name, project.state))
    if expected_row and expected_row["expects_coordinates"] and not has_coordinate_pair(project):
        errors.append(f"{label}: expected coordinates from demo CSV but latitude/longitude are missing")

    try:
        prediction = prediction_service.get_project_prediction(project.id)
        if clean_text(getattr(prediction, "risk_tier", None)) is None:
            warnings.append(f"{label}: risk_tier is not available from prediction")
    except Exception as exc:
        warnings.append(f"{label}: risk_tier availability check could not run: {exc}")

    return errors, warnings


def collect_projects_from_api(db, summary: HealthcheckSummary) -> list[Any]:
    try:
        return ProjectService(db).list_projects()
    except Exception as exc:
        summary.errors.append(f"/projects service check failed: {exc}")
        return []


def run_healthcheck() -> HealthcheckSummary:
    summary = HealthcheckSummary()
    expected_demo_projects = load_expected_demo_projects()

    try:
        with SessionLocal() as db:
            db.execute(text("select 1"))
            projects = list(db.scalars(select(Project).order_by(Project.canonical_name)).all())
            api_projects = collect_projects_from_api(db, summary)

            if not projects:
                summary.errors.append("projects table has no records")
                return summary

            summary.projects_checked = len(projects)
            summary.projects_with_coordinates = sum(1 for project in projects if has_coordinate_pair(project))
            if summary.projects_with_coordinates == 0:
                summary.errors.append("no projects have latitude and longitude")

            project_ids_from_api = {item.id for item in api_projects if getattr(item, "id", None) is not None}
            missing_from_api = [project for project in projects if project.id not in project_ids_from_api]
            if api_projects and missing_from_api:
                names = ", ".join(project.canonical_name for project in missing_from_api[:5])
                summary.warnings.append(f"{len(missing_from_api)} DB project(s) were not returned by /projects: {names}")

            for project in projects:
                summary.errors.extend(validate_coordinate_fields(project))

            prediction_service = PredictionService(db)

            demo_projects = [project for project in projects if is_demo_project(project)]
            if not demo_projects:
                summary.errors.append(f"no demo projects loaded with demo_dataset_id={DEMO_DATASET_ID!r}")
            else:
                loaded_demo_keys = {(project.canonical_name, project.state) for project in demo_projects}
                for key, expected_row in expected_demo_projects.items():
                    if key not in loaded_demo_keys:
                        summary.errors.append(
                            f"expected demo project {expected_row['canonical_name']} ({expected_row['state']}) is not loaded"
                        )
                for project in demo_projects:
                    errors, warnings = validate_demo_project(project, expected_demo_projects, prediction_service)
                    summary.errors.extend(errors)
                    summary.warnings.extend(warnings)

            for project in projects:
                label = project_label(project)
                try:
                    prediction = prediction_service.get_project_prediction(project.id)
                except Exception as exc:
                    summary.errors.append(f"{label}: prediction endpoint failed: {exc}")
                    continue
                summary.predictions_checked += 1
                summary.errors.extend(validate_prediction_payload(prediction, label=label))

            project_service = ProjectService(db)
            demo_project_ids = {project.id for project in demo_projects}
            for project in projects:
                label = project_label(project)
                try:
                    evidence_response = project_service.get_project_evidence(project.id)
                    if not isinstance(evidence_response.evidence, list):
                        summary.errors.append(f"{label}: evidence endpoint did not return a list payload")
                        continue
                    if project.id in demo_project_ids and evidence_response.evidence:
                        summary.projects_with_evidence += 1
                    for evidence in evidence_response.evidence:
                        summary.evidence_checked += 1
                        has_source_url = clean_text(getattr(evidence, "source_url", None)) is not None
                        has_excerpt = clean_text(getattr(evidence, "excerpt", None)) is not None
                        if not has_source_url and not has_excerpt:
                            summary.errors.append(
                                f"{label}: evidence {evidence.evidence_id} is missing both source_url and excerpt"
                            )
                except Exception as exc:
                    summary.errors.append(f"{label}: evidence endpoint failed: {exc}")

            if demo_projects and summary.projects_with_evidence == 0:
                summary.warnings.append("no demo projects have linked evidence records")
            elif demo_projects and summary.projects_with_evidence < len(demo_projects):
                summary.warnings.append(
                    f"{len(demo_projects) - summary.projects_with_evidence} demo project(s) have no linked evidence records"
                )
    except Exception as exc:
        summary.errors.append(f"database connection failed for {DATABASE_URL!r}: {exc}")

    return summary


def main() -> None:
    summary = run_healthcheck()
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    raise SystemExit(1 if summary.errors else 0)


if __name__ == "__main__":
    main()
