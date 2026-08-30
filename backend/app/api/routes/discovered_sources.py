from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.discovered_source import (
    DiscoveredSourceReviewDetail,
    DiscoveredSourceReviewListResponse,
    DiscoveredSourceReviewSummaryResponse,
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
    q: str | None = None,
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
        q=q,
    )


@router.get("", response_model=DiscoveredSourceReviewListResponse, response_model_exclude_none=True)
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
    q: str | None = None,
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
        q=q,
    )
    sources, total, applied_filters = DiscoveredSourceService(db).list_review_sources(
        filters=filters,
        limit=limit,
        offset=offset,
    )
    return DiscoveredSourceReviewListResponse(
        items=[discovered_source_review_payload(source) for source in sources],
        total=total,
        limit=limit,
        offset=offset,
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
    q: str | None = None,
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
        q=q,
    )
    return DiscoveredSourceReviewSummaryResponse(**DiscoveredSourceService(db).summarize_review_sources(filters=filters))


@router.get("/{source_id}", response_model=DiscoveredSourceReviewDetail, response_model_exclude_none=True)
def get_discovered_source(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DiscoveredSourceReviewDetail:
    source = DiscoveredSourceService(db).get_review_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="discovered_source_not_found")
    return DiscoveredSourceReviewDetail(**discovered_source_review_payload(source, include_raw_metadata=True))
