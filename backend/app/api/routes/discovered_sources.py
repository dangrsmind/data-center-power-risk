from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.discovered_source import (
    DiscoveredSourceReviewBulkUpdate,
    DiscoveredSourceReviewBulkUpdateResponse,
    DiscoveredSourceReviewDetail,
    DiscoveredSourceReviewListResponse,
    DiscoveredSourceReviewSummaryResponse,
    DiscoveredSourceReviewUpdate,
)
from app.services.discovered_source_service import (
    DiscoveredSourceReviewFilters,
    DiscoveredSourceService,
    discovered_source_review_payload,
)


router = APIRouter(prefix="/discovered-sources", tags=["discovered-sources"])


def _review_filters(
    discovery_run_id: str | None = None,
    source_registry_id: str | None = None,
    adapter_id: str | None = None,
    source_type: str | None = None,
    geography: str | None = None,
    status: str | None = None,
    publisher: str | None = None,
    source_url_quality: str | None = None,
    has_weak_url_quality: bool | None = None,
    review_status: str | None = None,
    reviewed_by: str | None = None,
    has_review_notes: bool | None = None,
    q: str | None = None,
    priority_bucket: str | None = None,
    min_priority_score: int | None = None,
    sort: str | None = None,
) -> DiscoveredSourceReviewFilters:
    return DiscoveredSourceReviewFilters(
        discovery_run_id=discovery_run_id,
        source_registry_id=source_registry_id,
        adapter_id=adapter_id,
        source_type=source_type,
        geography=geography,
        status=status,
        publisher=publisher,
        source_url_quality=source_url_quality,
        has_weak_url_quality=has_weak_url_quality,
        review_status=review_status,
        reviewed_by=reviewed_by,
        has_review_notes=has_review_notes,
        q=q,
        priority_bucket=priority_bucket,
        min_priority_score=min_priority_score,
        sort=sort,
    )


@router.get("", response_model=DiscoveredSourceReviewListResponse)
def list_discovered_sources(
    discovery_run_id: str | None = None,
    source_registry_id: str | None = None,
    adapter_id: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    geography: str | None = None,
    publisher: str | None = None,
    source_url_quality: str | None = None,
    has_weak_url_quality: bool | None = None,
    review_status: str | None = None,
    reviewed_by: str | None = None,
    has_review_notes: bool | None = None,
    q: str | None = None,
    priority_bucket: str | None = None,
    min_priority_score: int | None = None,
    sort: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> DiscoveredSourceReviewListResponse:
    filters = _review_filters(
        discovery_run_id=discovery_run_id,
        source_registry_id=source_registry_id,
        adapter_id=adapter_id,
        status=status,
        source_type=source_type,
        geography=geography,
        publisher=publisher,
        source_url_quality=source_url_quality,
        has_weak_url_quality=has_weak_url_quality,
        review_status=review_status,
        reviewed_by=reviewed_by,
        has_review_notes=has_review_notes,
        q=q,
        priority_bucket=priority_bucket,
        min_priority_score=min_priority_score,
        sort=sort,
    )
    try:
        sources, total, applied_filters = DiscoveredSourceService(db).list_review_sources(
            filters=filters,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DiscoveredSourceReviewListResponse(
        items=[discovered_source_review_payload(source) for source in sources],
        total=total,
        limit=limit,
        offset=offset,
        next_offset=offset + limit if offset + limit < total else None,
        previous_offset=max(0, offset - limit) if offset > 0 else None,
        has_next=offset + limit < total,
        has_previous=offset > 0,
        applied_filters=applied_filters,
    )


@router.get("/summary", response_model=DiscoveredSourceReviewSummaryResponse, response_model_exclude_none=True)
def summarize_discovered_sources(
    discovery_run_id: str | None = None,
    source_registry_id: str | None = None,
    adapter_id: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    geography: str | None = None,
    publisher: str | None = None,
    source_url_quality: str | None = None,
    has_weak_url_quality: bool | None = None,
    review_status: str | None = None,
    reviewed_by: str | None = None,
    has_review_notes: bool | None = None,
    q: str | None = None,
    priority_bucket: str | None = None,
    min_priority_score: int | None = None,
    sort: str | None = None,
    db: Session = Depends(get_db),
) -> DiscoveredSourceReviewSummaryResponse:
    filters = _review_filters(
        discovery_run_id=discovery_run_id,
        source_registry_id=source_registry_id,
        adapter_id=adapter_id,
        status=status,
        source_type=source_type,
        geography=geography,
        publisher=publisher,
        source_url_quality=source_url_quality,
        has_weak_url_quality=has_weak_url_quality,
        review_status=review_status,
        reviewed_by=reviewed_by,
        has_review_notes=has_review_notes,
        q=q,
        priority_bucket=priority_bucket,
        min_priority_score=min_priority_score,
        sort=sort,
    )
    try:
        summary = DiscoveredSourceService(db).summarize_review_sources(filters=filters)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DiscoveredSourceReviewSummaryResponse(**summary)


@router.patch("/review/bulk", response_model=DiscoveredSourceReviewBulkUpdateResponse, response_model_exclude_none=True)
def bulk_update_discovered_source_review(
    request: DiscoveredSourceReviewBulkUpdate,
    db: Session = Depends(get_db),
) -> DiscoveredSourceReviewBulkUpdateResponse:
    fields_set = request.model_fields_set
    update_kwargs = {"note_mode": request.note_mode}
    if "review_status" in fields_set:
        update_kwargs["review_status"] = request.review_status
    if "review_notes" in fields_set:
        update_kwargs["review_notes"] = request.review_notes
    if "reviewed_by" in fields_set:
        update_kwargs["reviewed_by"] = request.reviewed_by
    try:
        response = DiscoveredSourceService(db).bulk_update_review(
            request.source_ids,
            **update_kwargs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return DiscoveredSourceReviewBulkUpdateResponse(**response)


@router.get("/{source_id}", response_model=DiscoveredSourceReviewDetail, response_model_exclude_none=True)
def get_discovered_source(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DiscoveredSourceReviewDetail:
    source = DiscoveredSourceService(db).get_review_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="discovered_source_not_found")
    return DiscoveredSourceReviewDetail(**discovered_source_review_payload(source, include_raw_metadata=True))


@router.patch("/{source_id}/review", response_model=DiscoveredSourceReviewDetail, response_model_exclude_none=True)
def update_discovered_source_review(
    source_id: uuid.UUID,
    request: DiscoveredSourceReviewUpdate,
    db: Session = Depends(get_db),
) -> DiscoveredSourceReviewDetail:
    try:
        source = DiscoveredSourceService(db).update_review(
            source_id,
            **request.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if source is None:
        raise HTTPException(status_code=404, detail="discovered_source_not_found")
    db.commit()
    db.refresh(source)
    return DiscoveredSourceReviewDetail(**discovered_source_review_payload(source, include_raw_metadata=True))
