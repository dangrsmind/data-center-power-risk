from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.project_candidate import ProjectCandidate
from app.schemas.project_candidate import (
    ProjectCandidateConstraintSummaryCsvProvenance,
    ProjectCandidateConstraintSummaryItem,
    ProjectCandidateConstraintSummaryResponse,
    ProjectCandidateCsvProvenance,
    ProjectCandidateListResponse,
    ProjectCandidateResponse,
    ProjectCandidateReviewDecisionRequest,
    ProjectCandidatePromotionRequest,
    ProjectCandidatePromotionResponse,
    ProjectCandidateVerificationResponse,
)
from app.services.project_candidate_generator import ProjectCandidateGenerator
from app.services.project_candidate_energy_strategy import (
    ENERGY_STRATEGIES,
    classify_project_candidate_energy_strategy,
    energy_strategy_from_metadata,
)
from app.services.project_candidate_siting_friction import (
    SITING_FRICTION_CATEGORIES,
    classify_project_candidate_siting_friction,
    siting_friction_from_metadata,
)
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


@router.get("/constraint-summary", response_model=ProjectCandidateConstraintSummaryResponse, response_model_exclude_none=True)
def get_project_candidate_constraint_summary(
    status: str | None = None,
    verification_status: str | None = None,
    triage_tier: str | None = None,
    review_decision: str | None = None,
    energy_strategy: str | None = None,
    siting_friction_category: str | None = None,
    has_csv_provenance: bool | None = None,
    limit_top_candidates: int = Query(default=10, ge=0, le=50),
    db: Session = Depends(get_db),
) -> ProjectCandidateConstraintSummaryResponse:
    review_decision = clean_optional_text(review_decision)
    energy_strategy = clean_optional_text(energy_strategy)
    siting_friction_category = clean_optional_text(siting_friction_category)
    if review_decision and review_decision not in ALLOWED_REVIEW_DECISIONS:
        raise HTTPException(status_code=422, detail="invalid review_decision")
    if energy_strategy and energy_strategy not in ENERGY_STRATEGIES:
        raise HTTPException(status_code=422, detail="invalid energy_strategy")
    if siting_friction_category and siting_friction_category not in SITING_FRICTION_CATEGORIES:
        raise HTTPException(status_code=422, detail="invalid siting_friction_category")
    limit_top_candidates = normalize_top_candidate_limit(limit_top_candidates)

    candidates = list(db.scalars(select(ProjectCandidate)))
    summary_records = [constraint_summary_record(candidate) for candidate in candidates]
    summary_records = filter_constraint_summary_records(
        summary_records,
        status=status,
        verification_status=verification_status,
        triage_tier=triage_tier,
        review_decision=review_decision,
        energy_strategy=energy_strategy,
        siting_friction_category=siting_friction_category,
        has_csv_provenance=has_csv_provenance,
    )
    return build_constraint_summary(summary_records, limit_top_candidates=limit_top_candidates)


@router.get("", response_model=ProjectCandidateListResponse, response_model_exclude_none=True)
def list_project_candidates(
    status: str | None = None,
    state: str | None = None,
    triage_tier: str | None = None,
    recommended_action: str | None = None,
    review_decision: str | None = None,
    has_review_decision: bool | None = None,
    energy_strategy: str | None = None,
    siting_friction_category: str | None = None,
    min_triage_score: float | None = Query(default=None, ge=0, le=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> ProjectCandidateListResponse:
    review_decision = clean_optional_text(review_decision)
    energy_strategy = clean_optional_text(energy_strategy)
    siting_friction_category = clean_optional_text(siting_friction_category)
    if review_decision and review_decision not in ALLOWED_REVIEW_DECISIONS:
        raise HTTPException(status_code=422, detail="invalid review_decision")
    if energy_strategy and energy_strategy not in ENERGY_STRATEGIES:
        raise HTTPException(status_code=422, detail="invalid energy_strategy")
    if siting_friction_category and siting_friction_category not in SITING_FRICTION_CATEGORIES:
        raise HTTPException(status_code=422, detail="invalid siting_friction_category")
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
    items = [project_candidate_response(candidate) for candidate in candidates]
    if energy_strategy:
        items = [item for item in items if item.energy_strategy == energy_strategy]
    if siting_friction_category:
        items = [item for item in items if siting_friction_category in item.siting_friction_categories]
    return ProjectCandidateListResponse(items=items)


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


def normalize_top_candidate_limit(value: object) -> int:
    if isinstance(value, int):
        return max(0, min(value, 50))
    return 10


def project_candidate_response(candidate) -> ProjectCandidateResponse:
    payload = ProjectCandidateResponse.model_validate(candidate)
    payload.csv_provenance = csv_provenance_from_metadata(candidate.raw_metadata_json)
    classification = energy_strategy_from_metadata(candidate.raw_metadata_json)
    if classification is None:
        classification = classify_project_candidate_energy_strategy(candidate)
    payload.energy_strategy = classification.energy_strategy
    payload.energy_strategy_confidence = classification.energy_strategy_confidence
    payload.energy_strategy_reasons = classification.energy_strategy_reasons
    payload.energy_risk_tags = classification.energy_risk_tags
    siting = siting_friction_from_metadata(candidate.raw_metadata_json)
    if siting is None:
        siting = classify_project_candidate_siting_friction(candidate)
    payload.siting_friction_categories = siting.siting_friction_categories
    payload.siting_friction_confidence = siting.siting_friction_confidence
    payload.siting_friction_reasons = siting.siting_friction_reasons
    payload.siting_friction_warnings = siting.siting_friction_warnings
    payload.raw_metadata_json = None
    return payload


def constraint_summary_record(candidate: ProjectCandidate) -> dict[str, Any]:
    csv_provenance = csv_provenance_from_metadata(candidate.raw_metadata_json)
    energy = energy_strategy_from_metadata(candidate.raw_metadata_json)
    if energy is None:
        energy = classify_project_candidate_energy_strategy(candidate)
    siting = siting_friction_from_metadata(candidate.raw_metadata_json)
    if siting is None:
        siting = classify_project_candidate_siting_friction(candidate)
    return {
        "candidate": candidate,
        "csv_provenance": csv_provenance,
        "csv_backed": csv_backed_candidate(candidate, csv_provenance),
        "web_discovered": web_discovered_candidate(candidate),
        "energy_strategy": energy.energy_strategy,
        "energy_risk_tags": energy.energy_risk_tags,
        "siting_categories": siting.siting_friction_categories,
        "siting_warnings": siting.siting_friction_warnings,
    }


def filter_constraint_summary_records(
    records: list[dict[str, Any]],
    *,
    status: str | None,
    verification_status: str | None,
    triage_tier: str | None,
    review_decision: str | None,
    energy_strategy: str | None,
    siting_friction_category: str | None,
    has_csv_provenance: bool | None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for record in records:
        candidate = record["candidate"]
        if status and candidate.status != status:
            continue
        if verification_status and candidate.verification_status != verification_status:
            continue
        if triage_tier and candidate.triage_tier != triage_tier:
            continue
        if review_decision and candidate.review_decision != review_decision:
            continue
        if energy_strategy and record["energy_strategy"] != energy_strategy:
            continue
        if siting_friction_category and siting_friction_category not in record["siting_categories"]:
            continue
        if has_csv_provenance is not None and record["csv_backed"] is not has_csv_provenance:
            continue
        filtered.append(record)
    return filtered


def build_constraint_summary(
    records: list[dict[str, Any]],
    *,
    limit_top_candidates: int,
) -> ProjectCandidateConstraintSummaryResponse:
    by_status: Counter[str] = Counter()
    by_verification_status: Counter[str] = Counter()
    by_triage_tier: Counter[str] = Counter()
    by_review_decision: Counter[str] = Counter()
    by_energy_strategy: Counter[str] = Counter()
    by_energy_risk_tag: Counter[str] = Counter()
    by_siting_friction_category: Counter[str] = Counter()
    by_siting_friction_warning: Counter[str] = Counter()
    csv_backed_count = 0
    web_discovered_count = 0
    with_energy_strategy_count = 0
    with_siting_friction_count = 0
    high_priority_review_count = 0
    needs_source_count = 0
    ready_for_verification_count = 0
    likely_duplicate_count = 0
    dataset_only_rejected_count = 0

    for record in records:
        candidate: ProjectCandidate = record["candidate"]
        by_status[candidate.status or "unknown"] += 1
        by_verification_status[candidate.verification_status or "unverified"] += 1
        by_triage_tier[candidate.triage_tier or "untriaged"] += 1
        by_review_decision[candidate.review_decision or "unreviewed"] += 1
        if record["csv_backed"]:
            csv_backed_count += 1
        if record["web_discovered"]:
            web_discovered_count += 1

        energy_strategy = record["energy_strategy"]
        if energy_strategy:
            with_energy_strategy_count += 1
            by_energy_strategy[energy_strategy] += 1
        for tag in record["energy_risk_tags"]:
            by_energy_risk_tag[tag] += 1

        categories = record["siting_categories"]
        if categories:
            if any(category != "unknown" for category in categories):
                with_siting_friction_count += 1
            for category in categories:
                by_siting_friction_category[category] += 1
        for warning in record["siting_warnings"]:
            by_siting_friction_warning[warning] += 1

        if high_priority_review_candidate(candidate):
            high_priority_review_count += 1
        if needs_source_candidate(candidate):
            needs_source_count += 1
        if ready_for_verification_candidate(candidate):
            ready_for_verification_count += 1
        if likely_duplicate_candidate(candidate, record["csv_provenance"]):
            likely_duplicate_count += 1
        if candidate.review_decision == "rejected_dataset_only":
            dataset_only_rejected_count += 1

    ordered_records = sorted(records, key=review_priority_sort_key)
    return ProjectCandidateConstraintSummaryResponse(
        total_candidates=len(records),
        by_status=dict(sorted(by_status.items())),
        by_verification_status=dict(sorted(by_verification_status.items())),
        by_triage_tier=dict(sorted(by_triage_tier.items())),
        by_review_decision=dict(sorted(by_review_decision.items())),
        csv_backed_count=csv_backed_count,
        web_discovered_count=web_discovered_count,
        with_energy_strategy_count=with_energy_strategy_count,
        by_energy_strategy=dict(sorted(by_energy_strategy.items())),
        by_energy_risk_tag=dict(sorted(by_energy_risk_tag.items())),
        with_siting_friction_count=with_siting_friction_count,
        by_siting_friction_category=dict(sorted(by_siting_friction_category.items())),
        by_siting_friction_warning=dict(sorted(by_siting_friction_warning.items())),
        high_priority_review_count=high_priority_review_count,
        needs_source_count=needs_source_count,
        ready_for_verification_count=ready_for_verification_count,
        likely_duplicate_count=likely_duplicate_count,
        dataset_only_rejected_count=dataset_only_rejected_count,
        top_review_priority_candidates=[
            constraint_summary_item(record)
            for record in ordered_records[:limit_top_candidates]
        ],
    )


def constraint_summary_item(record: dict[str, Any]) -> ProjectCandidateConstraintSummaryItem:
    candidate: ProjectCandidate = record["candidate"]
    return ProjectCandidateConstraintSummaryItem(
        candidate_id=candidate.id,
        candidate_name=candidate.candidate_name,
        state=candidate.state,
        triage_tier=candidate.triage_tier,
        triage_score=candidate.triage_score,
        recommended_action=candidate.recommended_action,
        review_decision=candidate.review_decision,
        verification_status=candidate.verification_status,
        status=candidate.status,
        energy_strategy=record["energy_strategy"],
        siting_friction_categories=record["siting_categories"],
        csv_provenance=constraint_summary_csv_provenance(record["csv_provenance"]),
        primary_source_url=candidate.primary_source_url,
    )


def constraint_summary_csv_provenance(
    provenance: ProjectCandidateCsvProvenance | None,
) -> ProjectCandidateConstraintSummaryCsvProvenance | None:
    if provenance is None:
        return None
    return ProjectCandidateConstraintSummaryCsvProvenance(
        provenance=provenance.provenance,
        dataset_name=provenance.dataset_name,
        duplicate_status=provenance.duplicate_status,
        imported_row_count=provenance.imported_row_count,
    )


def csv_backed_candidate(candidate: ProjectCandidate, csv_provenance: ProjectCandidateCsvProvenance | None) -> bool:
    metadata = candidate.raw_metadata_json if isinstance(candidate.raw_metadata_json, dict) else {}
    return bool(
        csv_provenance
        or metadata.get("provenance") == "dataset_import"
        or metadata.get("imported_rows")
        or metadata.get("latest_dataset_import")
    )


def web_discovered_candidate(candidate: ProjectCandidate) -> bool:
    return bool(candidate.primary_source_url or candidate.discovered_source_ids_json or candidate.discovered_source_claim_ids_json)


def high_priority_review_candidate(candidate: ProjectCandidate) -> bool:
    # Transparent review-priority heuristic: high triage, explicit ready decision,
    # or current promotion-review action. This is not verification or admission.
    return bool(
        candidate.triage_tier == "high"
        or candidate.review_decision == "ready_for_verification"
        or candidate.recommended_action in {"ready_for_verification", "review_for_promotion"}
    )


def needs_source_candidate(candidate: ProjectCandidate) -> bool:
    return candidate.review_decision == "needs_source" or candidate.recommended_action == "needs_source_detail"


def ready_for_verification_candidate(candidate: ProjectCandidate) -> bool:
    return candidate.review_decision == "ready_for_verification" or candidate.recommended_action == "ready_for_verification"


def likely_duplicate_candidate(candidate: ProjectCandidate, csv_provenance: ProjectCandidateCsvProvenance | None) -> bool:
    duplicate_status = csv_provenance.duplicate_status if csv_provenance else None
    return bool(
        candidate.review_decision == "likely_duplicate"
        or duplicate_status in {"likely_same_project", "possible_duplicate"}
    )


def review_priority_sort_key(record: dict[str, Any]) -> tuple[int, float, str]:
    candidate: ProjectCandidate = record["candidate"]
    tier_rank = {"high": 0, "medium": 1, "low": 2}.get(candidate.triage_tier or "", 3)
    action_rank = 0 if high_priority_review_candidate(candidate) else 1
    score = candidate.triage_score if candidate.triage_score is not None else -1.0
    return (action_rank, tier_rank, -score, candidate.candidate_name.lower())


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
