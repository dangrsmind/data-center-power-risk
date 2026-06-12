from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


ProjectCandidateReviewDecision = Literal[
    "needs_source",
    "needs_location",
    "likely_duplicate",
    "ready_for_verification",
    "rejected_dataset_only",
    "rejected_not_data_center",
    "rejected_stale",
    "keep_under_review",
]


class ProjectCandidateCsvProvenance(BaseModel):
    provenance: str | None = None
    dataset_name: str | None = None
    dataset_source: str | None = None
    source_file: str | None = None
    row_number: int | None = None
    imported_row_ids: list[str] = []
    imported_row_count: int = 0
    source_urls: list[str] = []
    citation: str | None = None
    license_note: str | None = None
    duplicate_status: str | None = None
    duplicate_cluster_key: str | None = None
    warnings: list[str] = []


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
    csv_provenance: ProjectCandidateCsvProvenance | None = None
    promoted_project_id: uuid.UUID | None
    verification_status: str | None
    verification_confidence: float | None
    verification_reasons_json: list | None
    verification_errors_json: list | None
    auto_admit_eligible: bool
    verified_at: datetime | None
    triage_score: float | None
    triage_tier: str | None
    triage_reasons_json: list | None
    triage_warnings_json: list | None
    recommended_action: str | None
    triaged_at: datetime | None
    review_decision: str | None
    review_notes: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectCandidateListResponse(BaseModel):
    items: list[ProjectCandidateResponse]


class ProjectCandidateReviewDecisionRequest(BaseModel):
    review_decision: ProjectCandidateReviewDecision | None = None
    review_notes: str | None = Field(default=None, max_length=2000)
    reviewed_by: str | None = Field(default=None, max_length=255)


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


class ProjectCandidateVerificationResponse(BaseModel):
    candidate_id: uuid.UUID
    decision: str
    confidence: float
    reasons: list[str]
    blocking_errors: list[str]
    warnings: list[str]
    required_fields_present: dict
    evidence_requirements_met: dict
    source_quality_summary: dict
