from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.enums import ClaimEntityType, ClaimReviewStatus, ClaimType, ReviewerStatus, SourceType


class EvidenceCreateRequest(BaseModel):
    source_type: SourceType
    source_date: date | None = None
    source_url: str | None = None
    source_rank: int | None = None
    title: str | None = None
    extracted_text: str | None = None
    reviewer_status: ReviewerStatus = ReviewerStatus.PENDING


class EvidenceResponse(BaseModel):
    evidence_id: uuid.UUID
    source_type: SourceType
    source_date: date | None
    source_url: str | None
    source_rank: int | None
    title: str | None
    extracted_text: str | None
    reviewer_status: ReviewerStatus
    next_action: Literal["create_claims", "review_evidence"]
    reviewed_at: datetime | None
    reviewed_by: str | None
    review_notes: str | None
    created_at: datetime
    updated_at: datetime


class ProjectNameClaimValue(BaseModel):
    project_name: str


class PhaseNameClaimValue(BaseModel):
    phase_name: str = Field(pattern=r"^Phase\s+(?:[IVX]+|\d+|[A-Z])$")


class DeveloperNamedClaimValue(BaseModel):
    developer_name: str


class OperatorNamedClaimValue(BaseModel):
    operator_name: str


class LocationStateClaimValue(BaseModel):
    state: str


class LocationCountyClaimValue(BaseModel):
    county: str


class UtilityNamedClaimValue(BaseModel):
    utility_name: str


class RegionNamedClaimValue(BaseModel):
    region_name: str


class ModeledLoadClaimValue(BaseModel):
    modeled_primary_load_mw: float


class OptionalExpansionClaimValue(BaseModel):
    optional_expansion_mw: float


class AnnouncementDateClaimValue(BaseModel):
    announcement_date: date


class TargetEnergizationDateClaimValue(BaseModel):
    target_energization_date: date


class LatestUpdateDateClaimValue(BaseModel):
    latest_update_date: date


class BooleanFlagClaimValue(BaseModel):
    value: bool


class TimelineDisruptionClaimValue(BaseModel):
    summary: str
    disruption_type: str


class EventSupportClaimValue(BaseModel):
    summary: str
    reason_class: str | None = None


class ClaimCreateBase(BaseModel):
    claim_date: date | None = None
    confidence: str | None = None


class ProjectNameClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.PROJECT_NAME_MENTION]
    claim_value: ProjectNameClaimValue


class PhaseNameClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.PHASE_NAME_MENTION]
    claim_value: PhaseNameClaimValue


class DeveloperNamedClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.DEVELOPER_NAMED]
    claim_value: DeveloperNamedClaimValue


class OperatorNamedClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.OPERATOR_NAMED]
    claim_value: OperatorNamedClaimValue


class LocationStateClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.LOCATION_STATE]
    claim_value: LocationStateClaimValue


class LocationCountyClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.LOCATION_COUNTY]
    claim_value: LocationCountyClaimValue


class UtilityNamedClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.UTILITY_NAMED]
    claim_value: UtilityNamedClaimValue


class RegionNamedClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.REGION_OR_RTO_NAMED]
    claim_value: RegionNamedClaimValue


class ModeledLoadClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.MODELED_LOAD_MW]
    claim_value: ModeledLoadClaimValue


class OptionalExpansionClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.OPTIONAL_EXPANSION_MW]
    claim_value: OptionalExpansionClaimValue


class AnnouncementDateClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.ANNOUNCEMENT_DATE]
    claim_value: AnnouncementDateClaimValue


class TargetEnergizationDateClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.TARGET_ENERGIZATION_DATE]
    claim_value: TargetEnergizationDateClaimValue


class LatestUpdateDateClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.LATEST_UPDATE_DATE]
    claim_value: LatestUpdateDateClaimValue


class PowerPathIdentifiedClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.POWER_PATH_IDENTIFIED_FLAG]
    claim_value: BooleanFlagClaimValue


class NewTransmissionRequiredClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.NEW_TRANSMISSION_REQUIRED_FLAG]
    claim_value: BooleanFlagClaimValue


class NewSubstationRequiredClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.NEW_SUBSTATION_REQUIRED_FLAG]
    claim_value: BooleanFlagClaimValue


class OnsiteGenerationClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.ONSITE_GENERATION_FLAG]
    claim_value: BooleanFlagClaimValue


class TimelineDisruptionClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.TIMELINE_DISRUPTION_SIGNAL]
    claim_value: TimelineDisruptionClaimValue


class EventSupportE2ClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.EVENT_SUPPORT_E2]
    claim_value: EventSupportClaimValue


class EventSupportE3ClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.EVENT_SUPPORT_E3]
    claim_value: EventSupportClaimValue


class EventSupportE4ClaimCreate(ClaimCreateBase):
    claim_type: Literal[ClaimType.EVENT_SUPPORT_E4]
    claim_value: EventSupportClaimValue


ClaimCreateItem = Annotated[
    ProjectNameClaimCreate
    | PhaseNameClaimCreate
    | DeveloperNamedClaimCreate
    | OperatorNamedClaimCreate
    | LocationStateClaimCreate
    | LocationCountyClaimCreate
    | UtilityNamedClaimCreate
    | RegionNamedClaimCreate
    | ModeledLoadClaimCreate
    | OptionalExpansionClaimCreate
    | AnnouncementDateClaimCreate
    | TargetEnergizationDateClaimCreate
    | LatestUpdateDateClaimCreate
    | PowerPathIdentifiedClaimCreate
    | NewTransmissionRequiredClaimCreate
    | NewSubstationRequiredClaimCreate
    | OnsiteGenerationClaimCreate
    | TimelineDisruptionClaimCreate
    | EventSupportE2ClaimCreate
    | EventSupportE3ClaimCreate
    | EventSupportE4ClaimCreate,
    Field(discriminator="claim_type"),
]


class EvidenceClaimsCreateRequest(BaseModel):
    claims: list[ClaimCreateItem]


class ClaimResponse(BaseModel):
    claim_id: uuid.UUID
    evidence_id: uuid.UUID
    claim_type: ClaimType
    claim_value: dict
    claim_date: date | None
    confidence: str | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    entity_label: str | None
    review_status: ClaimReviewStatus
    is_contradictory: bool
    next_action: Literal["link_claim", "review_claim", "accept_claim", "complete"]
    reviewed_at: datetime | None
    reviewed_by: str | None
    review_notes: str | None
    accepted_at: datetime | None
    accepted_by: str | None
    created_at: datetime
    updated_at: datetime


class EvidenceClaimsCreateResponse(BaseModel):
    evidence_id: uuid.UUID
    created_claims: list[ClaimResponse]


class EvidenceQueueItem(BaseModel):
    evidence_id: uuid.UUID
    source_type: SourceType
    source_date: date | None
    title: str | None
    reviewer_status: ReviewerStatus
    claim_count: int
    linked_claim_count: int
    accepted_claim_count: int
    provenance_link_count: int
    status_bucket: Literal["unclaimed", "claims_unlinked", "claims_pending_review", "review_complete"]
    recommended_action: Literal["create_claims", "link_claims", "review_claims", "complete"]
    created_at: datetime
    updated_at: datetime


class EvidenceQueueResponse(BaseModel):
    items: list[EvidenceQueueItem]


class ClaimQueueItem(BaseModel):
    claim_id: uuid.UUID
    evidence_id: uuid.UUID
    claim_type: ClaimType
    claim_value: dict
    claim_date: date | None
    confidence: str | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    entity_label: str | None
    review_status: ClaimReviewStatus
    is_contradictory: bool
    status_bucket: Literal["needs_link", "needs_review", "accepted", "rejected"]
    recommended_action: Literal["link_claim", "review_claim", "accept_claim", "complete"]
    created_at: datetime
    updated_at: datetime


class ClaimQueueResponse(BaseModel):
    items: list[ClaimQueueItem]


class ClaimLinkRequest(BaseModel):
    entity_type: ClaimEntityType | None = None
    entity_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    phase_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_link_target(self) -> "ClaimLinkRequest":
        alias_count = int(self.project_id is not None) + int(self.phase_id is not None)
        explicit_count = int(self.entity_type is not None) + int(self.entity_id is not None)

        if alias_count > 1:
            raise ValueError("Provide only one of project_id or phase_id.")
        if alias_count == 1 and explicit_count > 0:
            raise ValueError("Use either project_id/phase_id or entity_type/entity_id, not both.")
        if alias_count == 0 and explicit_count != 2:
            raise ValueError(
                "Linking requires either project_id, phase_id, or both entity_type and entity_id."
            )
        if alias_count == 0 and self.entity_type not in {ClaimEntityType.PROJECT, ClaimEntityType.PHASE}:
            raise ValueError("entity_type must be project or phase for this operator flow.")
        return self


class ClaimReviewRequest(BaseModel):
    review_status: Literal[
        ClaimReviewStatus.ACCEPTED_CANDIDATE,
        ClaimReviewStatus.REJECTED,
        ClaimReviewStatus.AMBIGUOUS,
        ClaimReviewStatus.NEEDS_MORE_REVIEW,
    ]
    reviewer: str
    notes: str | None = None
    is_contradictory: bool = False


class EvidenceReviewRequest(BaseModel):
    reviewer_status: Literal[ReviewerStatus.REVIEWED]
    reviewed_by: str
    notes: str | None = None


class ClaimAcceptRequest(BaseModel):
    accepted_by: str
    notes: str | None = None


class ProvenanceLinkResponse(BaseModel):
    field_provenance_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    field_name: str
    evidence_id: uuid.UUID
    claim_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ClaimAcceptResponse(BaseModel):
    claim_id: uuid.UUID
    review_status: ClaimReviewStatus
    accepted_at: datetime
    accepted_by: str
    entity_label: str | None
    next_action: Literal["complete"]
    normalized_update: dict
    field_provenance: ProvenanceLinkResponse


class EvidenceDetailResponse(BaseModel):
    evidence: EvidenceResponse
    linked_claims: list[ClaimResponse]
    unlinked_claims: list[ClaimResponse]
    provenance_links: list[ProvenanceLinkResponse]


class EvidenceReviewRequest(BaseModel):
    reviewer_status: ReviewerStatus
    reviewed_by: str
