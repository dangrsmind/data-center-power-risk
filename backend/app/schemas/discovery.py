from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


DiscoveryConfidence = Literal[
    "confirmed_discovered",
    "probable_discovered",
    "candidate_discovered",
    "context_only",
    "quarantined",
]


class DiscoveredSource(BaseModel):
    source_url: HttpUrl
    source_title: str | None = None
    source_type: str
    publisher: str | None = None
    geography: str | None = None
    discovered_at: datetime
    discovery_method: str
    content_hash: str | None = None
    confidence: DiscoveryConfidence
    notes: str | None = None
    source_query: str | None = None
    snippet: str | None = None
    case_number: str | None = None
    document_type: str | None = None


class ExtractedClaim(BaseModel):
    source_url: HttpUrl
    claim_type: str
    claim_value: str | int | float | bool | dict | list | None
    claim_unit: str | None = None
    evidence_excerpt: str | None = None
    confidence: float = Field(ge=0, le=1)


class ProjectCandidate(BaseModel):
    canonical_name: str | None = None
    developer: str | None = None
    city: str | None = None
    county: str | None = None
    state: str | None = None
    utility: str | None = None
    load_mw: float | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    lifecycle_state: str | None = None
    discovery_status: DiscoveryConfidence
    confidence: float = Field(ge=0, le=1)
    source_urls: list[HttpUrl]


class DiscoveryRunSummary(BaseModel):
    sources_checked: int = 0
    sources_discovered: int = 0
    project_candidates_created: int = 0
    claims_extracted: int = 0
    quarantined_items: int = 0
    output_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
