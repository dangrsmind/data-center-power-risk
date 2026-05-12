from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.services.prediction_service import MODEL_VERSION, PredictionService  # noqa: E402


DEMO_DATASET_ID = "demo_projects_v0_1"


@dataclass
class PredictionError:
    project_id: str
    canonical_name: str
    reason: str


@dataclass
class PredictionSummary:
    projects_scored: int = 0
    predictions_created: int = 0
    predictions_updated: int = 0
    errors: list[PredictionError] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["errors"] = [asdict(error) for error in self.errors]
        return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Run {MODEL_VERSION} for demo projects.")
    parser.add_argument(
        "--all-projects",
        action="store_true",
        help="Score every project instead of preferring demo-marked projects.",
    )
    return parser.parse_args()


def is_demo_project(project: Project) -> bool:
    metadata = project.candidate_metadata_json
    return isinstance(metadata, dict) and metadata.get("demo_dataset_id") == DEMO_DATASET_ID


def load_projects(db, *, all_projects: bool) -> list[Project]:
    projects = list(db.scalars(select(Project).order_by(Project.canonical_name)).all())
    if all_projects:
        return projects
    demo_projects = [project for project in projects if is_demo_project(project)]
    return demo_projects or projects


def run_predictions(*, all_projects: bool = False) -> PredictionSummary:
    summary = PredictionSummary()
    with SessionLocal() as db:
        service = PredictionService(db)
        for project in load_projects(db, all_projects=all_projects):
            try:
                _, status = service.upsert_project_prediction(project)
                summary.projects_scored += 1
                if status == "created":
                    summary.predictions_created += 1
                elif status == "updated":
                    summary.predictions_updated += 1
            except Exception as exc:  # pragma: no cover - protects batch runner summary output
                summary.errors.append(
                    PredictionError(
                        project_id=str(project.id),
                        canonical_name=project.canonical_name,
                        reason=str(exc),
                    )
                )
        db.commit()
    return summary


def main() -> None:
    args = parse_args()
    summary = run_predictions(all_projects=args.all_projects)
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
