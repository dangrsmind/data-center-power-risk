from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.project import Project, ProjectCoordinateHistory
from app.models.reference import Utility
from app.schemas.analyst import (
    ProjectEvidenceResponse,
    ProjectEventsResponse,
    ProjectHistoryResponse,
    ProjectPredictionResponse,
    ProjectRiskSignalResponse,
    ProjectStressResponse,
)
from app.schemas.enrichment import ProjectEnrichmentResponse
from app.schemas.phase import PhaseListItem
from app.schemas.project import (
    ProjectCoordinateHistoryItem,
    ProjectCoordinatesRequest,
    ProjectDetail,
    ProjectListItem,
    ProjectMissingCoordinatesItem,
)
from app.schemas.score import ProjectScoreResponse
from app.services import EnrichmentService, PredictionService, ProjectService


router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectListItem], response_model_exclude_none=True)
def list_projects(db: Session = Depends(get_db)) -> list[ProjectListItem]:
    return ProjectService(db).list_projects()


@router.get("/missing-coordinates", response_model=list[ProjectMissingCoordinatesItem])
def list_missing_coordinates(db: Session = Depends(get_db)) -> list[ProjectMissingCoordinatesItem]:
    projects = db.scalars(
        select(Project)
        .where(
            or_(
                Project.latitude.is_(None),
                Project.longitude.is_(None),
                Project.coordinate_status.in_(["missing", "needs_review"]),
            )
        )
        .order_by(Project.state, Project.canonical_name)
    ).all()
    items: list[ProjectMissingCoordinatesItem] = []
    for project in projects:
        utility = db.get(Utility, project.utility_id) if project.utility_id else None
        items.append(
            ProjectMissingCoordinatesItem(
                id=project.id,
                name=project.canonical_name,
                developer=project.developer,
                utility=utility.name if utility else None,
                state=project.state,
                county=project.county,
                latitude=project.latitude,
                longitude=project.longitude,
                coordinate_status=project.coordinate_status or (
                    "missing" if project.latitude is None or project.longitude is None else "unverified"
                ),
                coordinate_precision=project.coordinate_precision,
                coordinate_source=project.coordinate_source,
                coordinate_confidence=project.coordinate_confidence,
            )
        )
    return items


@router.get("/{project_id}", response_model=ProjectDetail, response_model_exclude_none=True)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectDetail:
    return ProjectService(db).get_project(project_id)


def _create_coordinate_history(
    db: Session,
    project: Project,
    *,
    new_latitude: float | None,
    new_longitude: float | None,
    new_coordinate_precision: str | None,
    new_coordinate_status: str | None,
    source: str | None,
    source_url: str | None,
    notes: str | None,
    changed_by: str | None,
) -> None:
    db.add(
        ProjectCoordinateHistory(
            project_id=project.id,
            old_latitude=project.latitude,
            old_longitude=project.longitude,
            new_latitude=new_latitude,
            new_longitude=new_longitude,
            old_coordinate_precision=project.coordinate_precision,
            new_coordinate_precision=new_coordinate_precision,
            old_coordinate_status=project.coordinate_status,
            new_coordinate_status=new_coordinate_status,
            source=source,
            source_url=source_url,
            notes=notes,
            changed_by=changed_by or "manual",
        )
    )


@router.patch("/{project_id}/coordinates", response_model=ProjectDetail, response_model_exclude_none=True)
def patch_project_coordinates(
    project_id: uuid.UUID,
    body: ProjectCoordinatesRequest,
    db: Session = Depends(get_db),
) -> ProjectDetail:
    """Manually set latitude/longitude on a project. Does not geocode automatically."""
    project = db.scalar(select(Project).where(Project.id == project_id))
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found.")

    now = datetime.now(timezone.utc)
    _create_coordinate_history(
        db,
        project,
        new_latitude=body.latitude,
        new_longitude=body.longitude,
        new_coordinate_precision=body.coordinate_precision,
        new_coordinate_status=body.coordinate_status,
        source=body.coordinate_source,
        source_url=body.coordinate_source_url,
        notes=body.coordinate_notes,
        changed_by=body.changed_by,
    )
    project.latitude = body.latitude
    project.longitude = body.longitude
    project.coordinate_status = body.coordinate_status
    project.coordinate_precision = body.coordinate_precision
    project.coordinate_source = body.coordinate_source
    project.coordinate_source_url = body.coordinate_source_url
    project.coordinate_notes = body.coordinate_notes
    project.coordinate_confidence = body.coordinate_confidence
    project.coordinate_updated_at = now
    if body.coordinate_status == "verified":
        project.coordinate_verified_at = now

    db.commit()
    db.refresh(project)
    return ProjectService(db).get_project(project_id)


@router.get(
    "/{project_id}/coordinates/history",
    response_model=list[ProjectCoordinateHistoryItem],
)
def get_project_coordinate_history(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[ProjectCoordinateHistoryItem]:
    if db.scalar(select(Project.id).where(Project.id == project_id)) is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found.")
    return list(
        db.scalars(
            select(ProjectCoordinateHistory)
            .where(ProjectCoordinateHistory.project_id == project_id)
            .order_by(ProjectCoordinateHistory.created_at.desc(), ProjectCoordinateHistory.id.desc())
        ).all()
    )


@router.delete("/{project_id}/coordinates", response_model=ProjectDetail, response_model_exclude_none=True)
def clear_project_coordinates(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ProjectDetail:
    project = db.scalar(select(Project).where(Project.id == project_id))
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found.")
    now = datetime.now(timezone.utc)
    _create_coordinate_history(
        db,
        project,
        new_latitude=None,
        new_longitude=None,
        new_coordinate_precision="unknown",
        new_coordinate_status="missing",
        source=project.coordinate_source,
        source_url=project.coordinate_source_url,
        notes="Coordinates cleared.",
        changed_by="manual",
    )
    project.latitude = None
    project.longitude = None
    project.coordinate_status = "missing"
    project.coordinate_precision = "unknown"
    project.coordinate_updated_at = now

    db.commit()
    db.refresh(project)
    return ProjectService(db).get_project(project_id)


@router.get("/{project_id}/phases", response_model=list[PhaseListItem], response_model_exclude_none=True)
def list_project_phases(project_id: uuid.UUID, db: Session = Depends(get_db)) -> list[PhaseListItem]:
    return ProjectService(db).list_project_phases(project_id)


@router.get("/{project_id}/score", response_model=ProjectScoreResponse, response_model_exclude_none=True)
def get_project_score(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectScoreResponse:
    return ProjectService(db).get_project_score(project_id)


@router.get("/{project_id}/events", response_model=ProjectEventsResponse, response_model_exclude_none=True)
def get_project_events(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectEventsResponse:
    return ProjectService(db).get_project_events(project_id)


@router.get("/{project_id}/stress", response_model=ProjectStressResponse, response_model_exclude_none=True)
def get_project_stress(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectStressResponse:
    return ProjectService(db).get_project_stress(project_id)


@router.get("/{project_id}/history", response_model=ProjectHistoryResponse, response_model_exclude_none=True)
def get_project_history(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectHistoryResponse:
    return ProjectService(db).get_project_history(project_id)


@router.get("/{project_id}/evidence", response_model=ProjectEvidenceResponse, response_model_exclude_none=True)
def get_project_evidence(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectEvidenceResponse:
    return ProjectService(db).get_project_evidence(project_id)


@router.get("/{project_id}/risk-signal", response_model=ProjectRiskSignalResponse, response_model_exclude_none=True)
def get_project_risk_signal(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectRiskSignalResponse:
    return ProjectService(db).get_project_risk_signal(project_id)


@router.get("/{project_id}/prediction", response_model=ProjectPredictionResponse, response_model_exclude_none=True)
def get_project_prediction(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectPredictionResponse:
    return PredictionService(db).get_project_prediction(project_id)


@router.get("/{project_id}/enrichment", response_model=ProjectEnrichmentResponse, response_model_exclude_none=True)
def get_project_enrichment(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectEnrichmentResponse:
    return EnrichmentService(db).enrich_project(project_id)
