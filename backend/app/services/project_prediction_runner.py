from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.project import Project
from app.services.prediction_service import PredictionService


@dataclass
class ProjectPredictionRunResult:
    project_id: str
    prediction_created: bool = False
    prediction_updated: bool = False
    prediction_skipped: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    prediction_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_prediction_for_project(db: Session, project_id: uuid.UUID) -> ProjectPredictionRunResult:
    result = ProjectPredictionRunResult(project_id=str(project_id))
    project = db.get(Project, project_id)
    if project is None:
        result.errors.append("project_not_found")
        return result

    service = PredictionService(db)
    response = service.compute_project_prediction(project)
    result.warnings.extend(f"missing_input:{field_name}" for field_name in response.missing_inputs)

    prediction, status = service.upsert_project_prediction(project)
    result.prediction_id = str(prediction.id)
    if status == "created":
        result.prediction_created = True
    elif status == "updated":
        result.prediction_updated = True
    else:
        result.prediction_skipped = True
    return result
