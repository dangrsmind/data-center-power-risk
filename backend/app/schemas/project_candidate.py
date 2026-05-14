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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectCandidateListResponse(BaseModel):
    items: list[ProjectCandidateResponse]
