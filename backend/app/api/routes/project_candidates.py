from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, object_session

from app.api.deps import get_db
from app.models.project_candidate import ProjectCandidate, ProjectCandidateSourceAttachment
from app.schemas.project_candidate import (
    ProjectCandidateCsvProvenance,
    ProjectCandidateListResponse,
    ProjectCandidateResponse,
    ProjectCandidateReviewDecisionRequest,
    ProjectCandidateSourceAttachmentListResponse,
    ProjectCandidateSourceAttachmentRequest,
    ProjectCandidateSourceAttachmentResponse,
    ProjectCandidatePromotionRequest,
    ProjectCandidatePromotionResponse,
    ProjectCandidateVerificationResponse,
)
from app.services.project_candidate_generator import ProjectCandidateGenerator
from app.services.project_candidate_promotion import ProjectCandidatePromotionService
from app.services.project_candidate_verifier import ProjectCandidateVerifier


router = APIRouter(prefix="/project-candidates", tags=["project-candidates"])
ALLOWED_REVIEW_DECISIONS = {
    "needs_source",
    "needs_location",
    "likely_duplicate",
    "ready_for_verification",
    "rejected_dataset_only",
    "rejected_not_data_center",
    "rejected_stale",
    "keep_under_review",
}


@router.get("", response_model=ProjectCandidateListResponse, response_model_exclude_none=True)
def list_project_candidates(
    status: str | None = None,
    state: str | None = None,
    triage_tier: str | None = None,
    recommended_action: str | None = None,
    review_decision: str | None = None,
    has_review_decision: bool | None = None,
    min_triage_score: float | None = Query(default=None, ge=0, le=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> ProjectCandidateListResponse:
    review_decision = clean_optional_text(review_decision)
    if review_decision and review_decision not in ALLOWED_REVIEW_DECISIONS:
        raise HTTPException(status_code=422, detail="invalid review_decision")
    candidates = ProjectCandidateGenerator(db).list_candidates(
        status=status,
        state=state,
        triage_tier=triage_tier,
        recommended_action=recommended_action,
        review_decision=review_decision,
        has_review_decision=has_review_decision,
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


@router.patch("/{candidate_id}/review-decision", response_model=ProjectCandidateResponse)
def update_project_candidate_review_decision(
    candidate_id: uuid.UUID,
    request: ProjectCandidateReviewDecisionRequest,
    db: Session = Depends(get_db),
) -> ProjectCandidateResponse:
    candidate = db.get(ProjectCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="project candidate not found")
    candidate.review_decision = request.review_decision
    candidate.review_notes = request.review_notes
    candidate.reviewed_by = request.reviewed_by
    candidate.reviewed_at = datetime.now(timezone.utc) if request.review_decision else None
    db.commit()
    db.refresh(candidate)
    return project_candidate_response(candidate)


@router.get(
    "/{candidate_id}/source-attachments",
    response_model=ProjectCandidateSourceAttachmentListResponse,
)
def list_project_candidate_source_attachments(
    candidate_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ProjectCandidateSourceAttachmentListResponse:
    candidate = db.get(ProjectCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="project candidate not found")
    attachments = db.scalars(
        select(ProjectCandidateSourceAttachment)
        .where(ProjectCandidateSourceAttachment.project_candidate_id == candidate_id)
        .order_by(desc(ProjectCandidateSourceAttachment.attached_at), desc(ProjectCandidateSourceAttachment.created_at))
    ).all()
    return ProjectCandidateSourceAttachmentListResponse(
        items=[ProjectCandidateSourceAttachmentResponse.model_validate(attachment) for attachment in attachments]
    )


@router.post(
    "/{candidate_id}/source-attachments",
    response_model=ProjectCandidateSourceAttachmentResponse,
)
def create_project_candidate_source_attachment(
    candidate_id: uuid.UUID,
    request: ProjectCandidateSourceAttachmentRequest,
    db: Session = Depends(get_db),
) -> ProjectCandidateSourceAttachmentResponse:
    candidate = db.get(ProjectCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="project candidate not found")
    source_url = str(request.source_url).strip()
    existing = db.scalar(
        select(ProjectCandidateSourceAttachment).where(
            ProjectCandidateSourceAttachment.project_candidate_id == candidate_id,
            ProjectCandidateSourceAttachment.source_url == source_url,
        )
    )
    if existing is not None:
        return ProjectCandidateSourceAttachmentResponse.model_validate(existing)
    attachment = ProjectCandidateSourceAttachment(
        project_candidate_id=candidate_id,
        source_url=source_url,
        source_title=request.source_title,
        source_type=request.source_type,
        source_excerpt=request.source_excerpt,
        analyst_notes=request.analyst_notes,
        attached_by=request.attached_by,
        attached_at=datetime.now(timezone.utc),
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return ProjectCandidateSourceAttachmentResponse.model_validate(attachment)


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


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def project_candidate_response(candidate) -> ProjectCandidateResponse:
    payload = ProjectCandidateResponse.model_validate(candidate)
    payload.csv_provenance = csv_provenance_from_metadata(candidate.raw_metadata_json)
    payload.raw_metadata_json = None
    apply_source_attachment_summary(candidate, payload)
    return payload


def apply_source_attachment_summary(candidate, payload: ProjectCandidateResponse) -> None:
    session = object_session(candidate)
    if session is None:
        return
    rows = session.execute(
        select(
            func.count(ProjectCandidateSourceAttachment.id),
            func.max(ProjectCandidateSourceAttachment.attached_at),
        ).where(ProjectCandidateSourceAttachment.project_candidate_id == candidate.id)
    ).one()
    payload.source_attachment_count = int(rows[0] or 0)
    payload.latest_source_attachment_at = rows[1]
    types = session.scalars(
        select(ProjectCandidateSourceAttachment.source_type)
        .where(
            ProjectCandidateSourceAttachment.project_candidate_id == candidate.id,
            ProjectCandidateSourceAttachment.source_type.is_not(None),
        )
        .distinct()
        .order_by(ProjectCandidateSourceAttachment.source_type)
    ).all()
    payload.source_attachment_types = [str(source_type) for source_type in types if source_type]


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
