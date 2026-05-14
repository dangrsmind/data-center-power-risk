from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.discovered_source import DiscoveredSourceListResponse
from app.services.discovered_source_service import DiscoveredSourceService


router = APIRouter(prefix="/discovered-sources", tags=["discovered-sources"])


@router.get("", response_model=DiscoveredSourceListResponse, response_model_exclude_none=True)
def list_discovered_sources(
    status: str | None = None,
    source_type: str | None = None,
    publisher: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> DiscoveredSourceListResponse:
    sources = DiscoveredSourceService(db).list_sources(
        status=status,
        source_type=source_type,
        publisher=publisher,
        limit=limit,
    )
    return DiscoveredSourceListResponse(items=sources)
