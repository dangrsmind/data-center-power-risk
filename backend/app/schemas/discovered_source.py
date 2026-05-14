from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, HttpUrl


class DiscoveredSourceResponse(BaseModel):
    id: uuid.UUID
    source_url: HttpUrl
    source_title: str | None
    source_type: str | None
    publisher: str | None
    geography: str | None
    discovery_method: str | None
    discovered_at: datetime | None
    confidence: str | None
    search_term: str | None
    snippet: str | None
    case_number: str | None
    document_type: str | None
    source_registry_id: str | None
    adapter_id: str | None
    discovery_run_id: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiscoveredSourceListResponse(BaseModel):
    items: list[DiscoveredSourceResponse]


class DiscoveredSourceClaimResponse(BaseModel):
    id: uuid.UUID
    discovered_source_id: uuid.UUID
    source_url: HttpUrl
    claim_type: str
    claim_value: str
    claim_unit: str | None
    evidence_excerpt: str | None
    confidence: float
    extractor_name: str
    extractor_version: str
    status: str
    raw_metadata_json: dict | list | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiscoveredSourceClaimListResponse(BaseModel):
    items: list[DiscoveredSourceClaimResponse]
