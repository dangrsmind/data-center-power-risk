from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.project_candidate import (
    ProjectCandidateListResponse,
    ProjectCandidatePromotionRequest,
    ProjectCandidatePromotionResponse,
)
from app.services.project_candidate_generator import ProjectCandidateGenerator
from app.services.project_candidate_promotion import ProjectCandidatePromotionService


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


@router.post("/{candidate_id}/promote", response_model=ProjectCandidatePromotionResponse)
def promote_project_candidate(
    candidate_id: uuid.UUID,
    request: ProjectCandidatePromotionRequest,
    db: Session = Depends(get_db),
) -> ProjectCandidatePromotionResponse:
    summary = ProjectCandidatePromotionService(db).promote(
        candidate_id,
        confirm=request.confirm,
        allow_unresolved_name=request.allow_unresolved_name,
        allow_incomplete=request.allow_incomplete,
    )
    if summary.errors:
        status_code = 404 if "candidate_not_found" in summary.errors else 400
        raise HTTPException(status_code=status_code, detail=summary.to_dict())
    if request.confirm:
        db.commit()
    return ProjectCandidatePromotionResponse(**summary.to_dict())
