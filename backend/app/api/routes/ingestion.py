from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.ingestion import (
    ClaimAcceptRequest,
    ClaimAcceptResponse,
    ClaimLinkRequest,
    ClaimQueueResponse,
    ClaimReviewRequest,
    ClaimResponse,
    EvidenceDetailResponse,
    EvidenceClaimsCreateRequest,
    EvidenceClaimsCreateResponse,
    EvidenceCreateRequest,
    EvidenceQueueResponse,
    EvidenceResponse,
)
from app.services.ingestion_service import IngestionService


evidence_router = APIRouter(prefix="/evidence", tags=["evidence"])
claims_router = APIRouter(prefix="/claims", tags=["claims"])
queue_router = APIRouter(prefix="/queue", tags=["queue"])


@evidence_router.post("", response_model=EvidenceResponse, response_model_exclude_none=True)
def create_evidence(request: EvidenceCreateRequest, db: Session = Depends(get_db)) -> EvidenceResponse:
    return IngestionService(db).create_evidence(request)


@evidence_router.get("/{evidence_id}", response_model=EvidenceDetailResponse, response_model_exclude_none=True)
def get_evidence_detail(evidence_id: uuid.UUID, db: Session = Depends(get_db)) -> EvidenceDetailResponse:
    return IngestionService(db).get_evidence_detail(evidence_id)


@evidence_router.post(
    "/{evidence_id}/claims",
    response_model=EvidenceClaimsCreateResponse,
    response_model_exclude_none=True,
)
def create_evidence_claims(
    evidence_id: uuid.UUID,
    request: EvidenceClaimsCreateRequest,
    db: Session = Depends(get_db),
) -> EvidenceClaimsCreateResponse:
    return IngestionService(db).create_claims(evidence_id, request)


@queue_router.get("/evidence", response_model=EvidenceQueueResponse, response_model_exclude_none=True)
def get_evidence_queue(db: Session = Depends(get_db)) -> EvidenceQueueResponse:
    return IngestionService(db).get_evidence_queue()


@queue_router.get("/claims", response_model=ClaimQueueResponse, response_model_exclude_none=True)
def get_claim_queue(db: Session = Depends(get_db)) -> ClaimQueueResponse:
    return IngestionService(db).get_claim_queue()


@claims_router.post("/{claim_id}/link", response_model=ClaimResponse, response_model_exclude_none=True)
def link_claim(
    claim_id: uuid.UUID,
    request: ClaimLinkRequest,
    db: Session = Depends(get_db),
) -> ClaimResponse:
    return IngestionService(db).link_claim(claim_id, request)


@claims_router.post("/{claim_id}/review", response_model=ClaimResponse, response_model_exclude_none=True)
def review_claim(
    claim_id: uuid.UUID,
    request: ClaimReviewRequest,
    db: Session = Depends(get_db),
) -> ClaimResponse:
    return IngestionService(db).review_claim(claim_id, request)


@claims_router.post("/{claim_id}/accept", response_model=ClaimAcceptResponse, response_model_exclude_none=True)
def accept_claim(
    claim_id: uuid.UUID,
    request: ClaimAcceptRequest,
    db: Session = Depends(get_db),
) -> ClaimAcceptResponse:
    return IngestionService(db).accept_claim(claim_id, request)
