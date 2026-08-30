from __future__ import annotations

import uuid
from datetime import datetime

from typing import Any

from pydantic import BaseModel, Field, HttpUrl


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


class DiscoveredSourceReviewItem(BaseModel):
    id: uuid.UUID
    source_title: str | None
    source_url: HttpUrl
    source_type: str | None
    geography: str | None
    publisher: str | None
    status: str
    discovery_run_id: str | None
    source_registry_id: str | None
    adapter_id: str | None
    discovery_method: str | None
    source_query: str | None
    snippet: str | None
    created_at: datetime
    updated_at: datetime
    source_url_quality: str | None = None
    url_quality_warning: str | None = None
    alternate_urls: list[str] = Field(default_factory=list)


class DiscoveredSourceReviewDetail(DiscoveredSourceReviewItem):
    raw_metadata_json: dict | list | None = None


class DiscoveredSourceReviewListResponse(BaseModel):
    items: list[DiscoveredSourceReviewItem]
    total: int
    limit: int
    offset: int
    applied_filters: dict[str, Any]


class DiscoveredSourceReviewSummaryResponse(BaseModel):
    total: int
    counts_by_status: dict[str, int]
    counts_by_source_type: dict[str, int]
    counts_by_geography: dict[str, int]
    counts_by_source_registry_id: dict[str, int]
    counts_by_adapter_id: dict[str, int]
    counts_by_discovery_run_id: dict[str, int]
    weak_url_quality_count: int
    weak_url_quality_examples: list[DiscoveredSourceReviewItem]
    applied_filters: dict[str, Any]


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
