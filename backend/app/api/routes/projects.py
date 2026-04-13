from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.phase import PhaseListItem
from app.schemas.project import ProjectDetail, ProjectListItem
from app.schemas.score import ProjectScoreResponse
from app.services import ProjectService


router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectListItem], response_model_exclude_none=True)
def list_projects(db: Session = Depends(get_db)) -> list[ProjectListItem]:
    return ProjectService(db).list_projects()


@router.get("/{project_id}", response_model=ProjectDetail, response_model_exclude_none=True)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectDetail:
    return ProjectService(db).get_project(project_id)


@router.get("/{project_id}/phases", response_model=list[PhaseListItem], response_model_exclude_none=True)
def list_project_phases(project_id: uuid.UUID, db: Session = Depends(get_db)) -> list[PhaseListItem]:
    return ProjectService(db).list_project_phases(project_id)


@router.get("/{project_id}/score", response_model=ProjectScoreResponse, response_model_exclude_none=True)
def get_project_score(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectScoreResponse:
    return ProjectService(db).get_project_score(project_id)
