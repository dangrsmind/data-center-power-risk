from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.project_candidate import (
    ProjectCandidateCsvProvenance,
    ProjectCandidateListResponse,
    ProjectCandidateResponse,
    ProjectCandidatePromotionRequest,
    ProjectCandidatePromotionResponse,
    ProjectCandidateVerificationResponse,
)
from app.services.project_candidate_generator import ProjectCandidateGenerator
from app.services.project_candidate_promotion import ProjectCandidatePromotionService
from app.services.project_candidate_verifier import ProjectCandidateVerifier


router = APIRouter(prefix="/project-candidates", tags=["project-candidates"])


@router.get("", response_model=ProjectCandidateListResponse, response_model_exclude_none=True)
def list_project_candidates(
    status: str | None = None,
    state: str | None = None,
    triage_tier: str | None = None,
    recommended_action: str | None = None,
    min_triage_score: float | None = Query(default=None, ge=0, le=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> ProjectCandidateListResponse:
    candidates = ProjectCandidateGenerator(db).list_candidates(
        status=status,
        state=state,
        triage_tier=triage_tier,
        recommended_action=recommended_action,
        min_triage_score=min_triage_score,
        limit=limit,
    )
    return ProjectCandidateListResponse(items=[project_candidate_response(candidate) for candidate in candidates])


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


@router.get("/{candidate_id}/verification", response_model=ProjectCandidateVerificationResponse)
def get_project_candidate_verification(
    candidate_id: uuid.UUID,
    threshold: float = Query(default=0.80, ge=0, le=1),
    db: Session = Depends(get_db),
) -> ProjectCandidateVerificationResponse:
    verifier = ProjectCandidateVerifier(db)
    candidate = verifier.get_candidate(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="project candidate not found")
    return ProjectCandidateVerificationResponse(**verifier.verify(candidate, threshold=threshold).to_dict())


def project_candidate_response(candidate) -> ProjectCandidateResponse:
    payload = ProjectCandidateResponse.model_validate(candidate)
    payload.csv_provenance = csv_provenance_from_metadata(candidate.raw_metadata_json)
    payload.raw_metadata_json = None
    return payload


def csv_provenance_from_metadata(metadata: dict | list | None) -> ProjectCandidateCsvProvenance | None:
    if not isinstance(metadata, dict) or metadata.get("provenance") != "dataset_import":
        return None
    imported_rows = metadata.get("imported_rows") if isinstance(metadata.get("imported_rows"), list) else []
    imported_row_ids = [
        str(row.get("imported_row_id"))
        for row in imported_rows
        if isinstance(row, dict) and row.get("imported_row_id")
    ]
    warnings = metadata.get("warnings") if isinstance(metadata.get("warnings"), list) else []
    source_urls = metadata.get("source_urls") if isinstance(metadata.get("source_urls"), list) else []
    return ProjectCandidateCsvProvenance(
        provenance="dataset_import",
        dataset_name=metadata.get("dataset_name"),
        dataset_source=metadata.get("dataset_source"),
        source_file=metadata.get("source_file"),
        row_number=metadata.get("row_number"),
        imported_row_ids=imported_row_ids,
        imported_row_count=len(imported_rows) or (1 if metadata.get("row_number") else 0),
        source_urls=[str(url) for url in source_urls if url],
        citation=metadata.get("citation"),
        license_note=metadata.get("license_note"),
        duplicate_status=metadata.get("duplicate_status"),
        duplicate_cluster_key=metadata.get("duplicate_cluster_key"),
        warnings=[str(warning) for warning in warnings],
    )
