from __future__ import annotations

import uuid
from datetime import datetime

from typing import Any
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


DiscoveredSourceReviewStatus = Literal["unreviewed", "useful", "maybe", "noisy", "weak", "rejected"]


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
    review_status: DiscoveredSourceReviewStatus = "unreviewed"
    review_notes: str | None = None
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None


class DiscoveredSourceReviewDetail(DiscoveredSourceReviewItem):
    raw_metadata_json: dict | list | None = None


class DiscoveredSourceReviewListResponse(BaseModel):
    items: list[DiscoveredSourceReviewItem]
    total: int
    limit: int
    offset: int
    applied_filters: dict[str, Any]


class DiscoveredSourceReviewUpdate(BaseModel):
    review_status: DiscoveredSourceReviewStatus | None = None
    review_notes: str | None = Field(default=None, max_length=2000)
    reviewed_by: str | None = Field(default=None, max_length=255)

    @field_validator("review_status", mode="before")
    @classmethod
    def normalize_review_status(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return value

    @field_validator("review_notes", "reviewed_by", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return value


class DiscoveredSourceReviewSummaryResponse(BaseModel):
    total: int
    counts_by_status: dict[str, int]
    counts_by_source_type: dict[str, int]
    counts_by_geography: dict[str, int]
    counts_by_source_registry_id: dict[str, int]
    counts_by_adapter_id: dict[str, int]
    counts_by_discovery_run_id: dict[str, int]
    counts_by_review_status: dict[str, int]
    reviewed_count: int
    unreviewed_count: int
    noisy_count: int
    weak_count: int
    useful_count: int
    maybe_count: int
    rejected_count: int
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
