from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, HttpUrl


class ProjectCandidateResponse(BaseModel):
    id: uuid.UUID
    candidate_name: str
    developer: str | None
    state: str | None
    county: str | None
    city: str | None
    utility: str | None
    load_mw: float | None
    lifecycle_state: str | None
    confidence: float
    status: str
    source_count: int
    claim_count: int
    primary_source_url: HttpUrl | None
    discovered_source_ids_json: list | None
    discovered_source_claim_ids_json: list | None
    evidence_excerpt: str | None
    raw_metadata_json: dict | list | None
    promoted_project_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectCandidateListResponse(BaseModel):
    items: list[ProjectCandidateResponse]


class ProjectCandidatePromotionRequest(BaseModel):
    confirm: bool = False
    allow_unresolved_name: bool = False
    allow_incomplete: bool = False


class ProjectCandidatePromotionResponse(BaseModel):
    dry_run: bool
    candidate_id: uuid.UUID
    promoted: bool
    project_created: bool
    project_updated: bool
    would_promote: bool
    would_create_project: bool
    would_update_project: bool
    evidence_created: int
    warnings: list[str]
    errors: list[str]
    promoted_project_id: uuid.UUID | None
