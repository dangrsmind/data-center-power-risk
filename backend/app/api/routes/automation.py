from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.automation import (
    ClaimSuggestRequest,
    ClaimSuggestResponse,
    IntakePacketRequest,
    IntakePacketResponse,
)
from app.services.automation_service import AutomationService


router = APIRouter(prefix="/automation", tags=["automation"])


@router.post("/claims/suggest", response_model=ClaimSuggestResponse, response_model_exclude_none=True)
def suggest_claims(request: ClaimSuggestRequest) -> ClaimSuggestResponse:
    return AutomationService().suggest_claims(request)


@router.post("/intake/packet", response_model=IntakePacketResponse, response_model_exclude_none=True)
def build_intake_packet(request: IntakePacketRequest, db: Session = Depends(get_db)) -> IntakePacketResponse:
    return AutomationService(db).build_intake_packet(request)
