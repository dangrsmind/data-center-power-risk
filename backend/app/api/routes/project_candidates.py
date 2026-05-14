from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.project_candidate import ProjectCandidateListResponse
from app.services.project_candidate_generator import ProjectCandidateGenerator


router = APIRouter(prefix="/project-candidates", tags=["project-candidates"])


@router.get("", response_model=ProjectCandidateListResponse, response_model_exclude_none=True)
def list_project_candidates(
    status: str | None = None,
    state: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> ProjectCandidateListResponse:
    candidates = ProjectCandidateGenerator(db).list_candidates(status=status, state=state, limit=limit)
    return ProjectCandidateListResponse(items=candidates)
