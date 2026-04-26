from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel

from app.core.enums import ClaimType, SourceType
from app.schemas.ingestion import EvidenceClaimsCreateRequest, EvidenceCreateRequest


class ClaimSuggestRequest(BaseModel):
    evidence_text: str
    source_type: SourceType | None = None


class ClaimSuggestResponse(BaseModel):
    claims_payload: EvidenceClaimsCreateRequest
    uncertainties: list[str]
    warnings: list[str]
    generator_version: str


class IntakePacketRequest(BaseModel):
    source_url: str | None = None
    source_type: SourceType
    source_date: date | None = None
    title: str | None = None
    evidence_text: str
    project_id: uuid.UUID | None = None


class SuggestedLinkTarget(BaseModel):
    claim_type: ClaimType
    suggested_entity_type: str
    suggested_entity_id: uuid.UUID
    suggested_entity_label: str
    reason: str


class IntakePacketResponse(BaseModel):
    evidence_payload: EvidenceCreateRequest
    claims_payload: EvidenceClaimsCreateRequest
    suggested_link_targets: list[SuggestedLinkTarget]
    exact_next_steps: list[str]
    uncertainties: list[str]
    warnings: list[str]
    generator_version: str
