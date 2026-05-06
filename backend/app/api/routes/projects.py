from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.project import Project
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
from app.schemas.project import ProjectCoordinatesRequest, ProjectDetail, ProjectListItem
from app.schemas.score import ProjectScoreResponse
from app.services import EnrichmentService, PredictionService, ProjectService


router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectListItem], response_model_exclude_none=True)
def list_projects(db: Session = Depends(get_db)) -> list[ProjectListItem]:
    return ProjectService(db).list_projects()


@router.get("/{project_id}", response_model=ProjectDetail, response_model_exclude_none=True)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectDetail:
    return ProjectService(db).get_project(project_id)


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
    if not (-90 <= body.latitude <= 90):
        raise HTTPException(status_code=422, detail="latitude must be between -90 and 90.")
    if not (-180 <= body.longitude <= 180):
        raise HTTPException(status_code=422, detail="longitude must be between -180 and 180.")

    project.latitude = body.latitude
    project.longitude = body.longitude

    meta = dict(project.candidate_metadata_json) if isinstance(project.candidate_metadata_json, dict) else {}
    meta["coordinate_source"] = body.coordinate_source or "analyst_manual_entry"
    meta["coordinate_confidence"] = body.coordinate_confidence or "unknown"
    project.candidate_metadata_json = meta

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
