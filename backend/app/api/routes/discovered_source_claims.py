from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.discovered_source import DiscoveredSourceClaimListResponse
from app.services.discovered_source_claim_extractor import DiscoveredSourceClaimService


router = APIRouter(prefix="/discovered-source-claims", tags=["discovered-source-claims"])


@router.get("", response_model=DiscoveredSourceClaimListResponse, response_model_exclude_none=True)
def list_discovered_source_claims(
    status: str | None = None,
    claim_type: str | None = None,
    discovered_source_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> DiscoveredSourceClaimListResponse:
    claims = DiscoveredSourceClaimService(db).list_claims(
        status=status,
        claim_type=claim_type,
        discovered_source_id=discovered_source_id,
        limit=limit,
    )
    return DiscoveredSourceClaimListResponse(items=claims)
