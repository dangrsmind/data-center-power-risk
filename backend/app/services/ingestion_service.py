from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.enums import ClaimEntityType, ClaimReviewStatus, ClaimType, LoadKind
from app.models.evidence import Claim, Evidence, FieldProvenance
from app.models.project import Phase, PhaseLoad, Project
from app.models.reference import Region, Utility
from app.repositories.ingestion_repo import IngestionRepository
from app.schemas.ingestion import (
    ClaimAcceptRequest,
    ClaimAcceptResponse,
    ClaimLinkRequest,
    ClaimQueueItem,
    ClaimQueueResponse,
    ClaimReviewRequest,
    ClaimResponse,
    EvidenceDetailResponse,
    EvidenceClaimsCreateRequest,
    EvidenceClaimsCreateResponse,
    EvidenceCreateRequest,
    EvidenceQueueItem,
    EvidenceQueueResponse,
    EvidenceResponse,
    ProvenanceLinkResponse,
)


class IngestionService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = IngestionRepository(db)

    def create_evidence(self, request: EvidenceCreateRequest) -> EvidenceResponse:
        evidence = self.repo.create_evidence(
            Evidence(
                source_type=request.source_type,
                source_date=request.source_date,
                source_url=request.source_url,
                source_rank=request.source_rank,
                title=request.title,
                extracted_text=request.extracted_text,
                reviewer_status=request.reviewer_status,
            )
        )
        self.db.commit()
        return self._to_evidence_response(evidence)

    def create_claims(self, evidence_id: uuid.UUID, request: EvidenceClaimsCreateRequest) -> EvidenceClaimsCreateResponse:
        evidence = self.repo.get_evidence(evidence_id)
        if evidence is None:
            raise HTTPException(status_code=404, detail="Evidence not found")

        claims = self.repo.create_claims(
            [
                Claim(
                    evidence_id=evidence_id,
                    entity_type=None,
                    entity_id=None,
                    claim_type=item.claim_type,
                    claim_value_json=item.claim_value.model_dump(),
                    claim_date=item.claim_date,
                    confidence=item.confidence,
                    is_contradictory=False,
                    review_status=ClaimReviewStatus.UNREVIEWED,
                    reviewed_at=None,
                    reviewed_by=None,
                    review_notes=None,
                    accepted_at=None,
                    accepted_by=None,
                )
                for item in request.claims
            ]
        )
        self.db.commit()
        return EvidenceClaimsCreateResponse(
            evidence_id=evidence_id,
            created_claims=[self._to_claim_response(claim) for claim in claims],
        )

    def get_evidence_detail(self, evidence_id: uuid.UUID) -> EvidenceDetailResponse:
        evidence = self.repo.get_evidence(evidence_id)
        if evidence is None:
            raise HTTPException(status_code=404, detail="Evidence not found")
        all_claims = self.repo.list_claims_by_evidence(evidence_id)
        linked_claims = [claim for claim in all_claims if claim.entity_type is not None and claim.entity_id is not None]
        unlinked_claims = [claim for claim in all_claims if claim.entity_type is None or claim.entity_id is None]
        provenance_rows = self.repo.list_provenance_by_evidence(evidence_id)
        return EvidenceDetailResponse(
            evidence=self._to_evidence_response(evidence),
            linked_claims=[self._to_claim_response(claim) for claim in linked_claims],
            unlinked_claims=[self._to_claim_response(claim) for claim in unlinked_claims],
            provenance_links=[self._to_provenance_response(row) for row in provenance_rows],
        )

    def link_claim(self, claim_id: uuid.UUID, request: ClaimLinkRequest) -> ClaimResponse:
        claim = self.repo.get_claim(claim_id)
        if claim is None:
            raise HTTPException(status_code=404, detail="Claim not found")
        if claim.review_status in {
            ClaimReviewStatus.ACCEPTED_CANDIDATE,
            ClaimReviewStatus.ACCEPTED,
            ClaimReviewStatus.REJECTED,
        }:
            raise HTTPException(status_code=400, detail="Claim cannot be relinked from its current state")
        entity_type, entity_id = self._resolve_link_target(request)
        self._assert_entity_exists(entity_type, entity_id)
        claim.entity_type = entity_type
        claim.entity_id = entity_id
        claim.review_status = ClaimReviewStatus.LINKED
        self.db.commit()
        self.db.refresh(claim)
        return self._to_claim_response(claim)

    def review_claim(self, claim_id: uuid.UUID, request: ClaimReviewRequest) -> ClaimResponse:
        claim = self.repo.get_claim(claim_id)
        if claim is None:
            raise HTTPException(status_code=404, detail="Claim not found")
        if claim.review_status == ClaimReviewStatus.ACCEPTED:
            raise HTTPException(status_code=400, detail="Accepted claims cannot be re-reviewed")
        if request.review_status == ClaimReviewStatus.ACCEPTED_CANDIDATE and (
            claim.entity_type is None or claim.entity_id is None
        ):
            raise HTTPException(status_code=400, detail="Claim must be linked before it can be marked accepted_candidate")

        claim.review_status = request.review_status
        claim.reviewed_by = request.reviewer
        claim.reviewed_at = datetime.now(timezone.utc)
        claim.review_notes = request.notes
        claim.is_contradictory = request.is_contradictory
        self.db.commit()
        self.db.refresh(claim)
        return self._to_claim_response(claim)

    def accept_claim(self, claim_id: uuid.UUID, request: ClaimAcceptRequest) -> ClaimAcceptResponse:
        claim = self.repo.get_claim(claim_id)
        if claim is None:
            raise HTTPException(status_code=404, detail="Claim not found")
        if claim.review_status != ClaimReviewStatus.ACCEPTED_CANDIDATE:
            raise HTTPException(status_code=400, detail="Only accepted_candidate claims can be accepted")
        if claim.entity_type is None or claim.entity_id is None:
            raise HTTPException(status_code=400, detail="Claim must be linked before acceptance")
        if claim.is_contradictory:
            raise HTTPException(status_code=400, detail="Contradictory claims cannot be accepted")

        field_name, normalized_update = self._apply_claim_acceptance(claim)
        claim.review_status = ClaimReviewStatus.ACCEPTED
        claim.accepted_by = request.accepted_by
        claim.accepted_at = datetime.now(timezone.utc)
        if request.notes:
            claim.review_notes = f"{claim.review_notes}\n{request.notes}" if claim.review_notes else request.notes

        provenance = self.repo.create_field_provenance(
            FieldProvenance(
                entity_type=claim.entity_type,
                entity_id=claim.entity_id,
                field_name=field_name,
                evidence_id=claim.evidence_id,
                claim_id=claim.id,
            )
        )
        self.db.commit()
        self.db.refresh(claim)
        return ClaimAcceptResponse(
            claim_id=claim.id,
            review_status=claim.review_status,
            accepted_at=claim.accepted_at,
            accepted_by=claim.accepted_by,
            entity_label=self._get_entity_label(claim.entity_type, claim.entity_id),
            next_action="complete",
            normalized_update=normalized_update,
            field_provenance=self._to_provenance_response(provenance),
        )

    def get_evidence_queue(self) -> EvidenceQueueResponse:
        rows = self.repo.list_evidence_queue()
        items: list[EvidenceQueueItem] = []
        for row in rows:
            if row.claim_count == 0:
                status_bucket = "unclaimed"
            elif row.linked_claim_count < row.claim_count:
                status_bucket = "claims_unlinked"
            elif row.reviewed_claim_count < row.claim_count:
                status_bucket = "claims_pending_review"
            else:
                status_bucket = "review_complete"

            items.append(
                EvidenceQueueItem(
                    evidence_id=row.evidence.id,
                    source_type=row.evidence.source_type,
                    source_date=row.evidence.source_date,
                    title=row.evidence.title,
                    reviewer_status=row.evidence.reviewer_status,
                    claim_count=row.claim_count,
                    linked_claim_count=row.linked_claim_count,
                    accepted_claim_count=row.accepted_claim_count,
                    provenance_link_count=self.repo.get_evidence_provenance_count(row.evidence.id),
                    status_bucket=status_bucket,
                    recommended_action=self._recommended_action_for_evidence(status_bucket),
                    created_at=row.evidence.created_at,
                    updated_at=row.evidence.updated_at,
                )
            )
        return EvidenceQueueResponse(items=items)

    def get_claim_queue(self) -> ClaimQueueResponse:
        claims = self.repo.list_claim_queue()
        items: list[ClaimQueueItem] = []
        for claim in claims:
            if claim.entity_id is None or claim.entity_type is None:
                status_bucket = "needs_link"
            elif claim.review_status in {
                ClaimReviewStatus.UNREVIEWED,
                ClaimReviewStatus.LINKED,
                ClaimReviewStatus.ACCEPTED_CANDIDATE,
                ClaimReviewStatus.AMBIGUOUS,
                ClaimReviewStatus.NEEDS_MORE_REVIEW,
            }:
                status_bucket = "needs_review"
            elif claim.review_status == ClaimReviewStatus.ACCEPTED:
                status_bucket = "accepted"
            else:
                status_bucket = "rejected"

            items.append(
                ClaimQueueItem(
                    claim_id=claim.id,
                    evidence_id=claim.evidence_id,
                    claim_type=claim.claim_type,
                    claim_value=claim.claim_value_json or {},
                    claim_date=claim.claim_date,
                    confidence=claim.confidence,
                    entity_type=claim.entity_type.value if claim.entity_type else None,
                    entity_id=claim.entity_id,
                    entity_label=self._get_entity_label(claim.entity_type, claim.entity_id),
                    review_status=claim.review_status,
                    is_contradictory=claim.is_contradictory,
                    status_bucket=status_bucket,
                    recommended_action=self._recommended_action_for_claim(claim, status_bucket),
                    created_at=claim.created_at,
                    updated_at=claim.updated_at,
                )
            )
        return ClaimQueueResponse(items=items)

    def _to_evidence_response(self, evidence: Evidence) -> EvidenceResponse:
        return EvidenceResponse(
            evidence_id=evidence.id,
            source_type=evidence.source_type,
            source_date=evidence.source_date,
            source_url=evidence.source_url,
            source_rank=evidence.source_rank,
            title=evidence.title,
            extracted_text=evidence.extracted_text,
            reviewer_status=evidence.reviewer_status,
            next_action="create_claims" if evidence.reviewer_status.value == "pending" else "review_evidence",
            created_at=evidence.created_at,
            updated_at=evidence.updated_at,
        )

    def _to_claim_response(self, claim: Claim) -> ClaimResponse:
        return ClaimResponse(
            claim_id=claim.id,
            evidence_id=claim.evidence_id,
            claim_type=claim.claim_type,
            claim_value=claim.claim_value_json or {},
            claim_date=claim.claim_date,
            confidence=claim.confidence,
            entity_type=claim.entity_type.value if claim.entity_type else None,
            entity_id=claim.entity_id,
            entity_label=self._get_entity_label(claim.entity_type, claim.entity_id),
            review_status=claim.review_status,
            is_contradictory=claim.is_contradictory,
            next_action=self._next_action_for_claim(claim),
            reviewed_at=claim.reviewed_at,
            reviewed_by=claim.reviewed_by,
            review_notes=claim.review_notes,
            accepted_at=claim.accepted_at,
            accepted_by=claim.accepted_by,
            created_at=claim.created_at,
            updated_at=claim.updated_at,
        )

    def _to_provenance_response(self, row: FieldProvenance) -> ProvenanceLinkResponse:
        return ProvenanceLinkResponse(
            field_provenance_id=row.id,
            entity_type=row.entity_type.value,
            entity_id=row.entity_id,
            field_name=row.field_name,
            evidence_id=row.evidence_id,
            claim_id=row.claim_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _assert_entity_exists(self, entity_type: ClaimEntityType, entity_id: uuid.UUID) -> None:
        model_map = {
            ClaimEntityType.PROJECT: Project,
            ClaimEntityType.PHASE: Phase,
            ClaimEntityType.REGION: Region,
            ClaimEntityType.UTILITY: Utility,
        }
        model = model_map.get(entity_type)
        if model is None or self.db.get(model, entity_id) is None:
            raise HTTPException(status_code=400, detail="Linked entity does not exist or is unsupported")

    def _resolve_link_target(self, request: ClaimLinkRequest) -> tuple[ClaimEntityType, uuid.UUID]:
        if request.project_id is not None:
            return ClaimEntityType.PROJECT, request.project_id
        if request.phase_id is not None:
            return ClaimEntityType.PHASE, request.phase_id
        if request.entity_type is None or request.entity_id is None:
            raise HTTPException(
                status_code=400,
                detail="Linking requires project_id, phase_id, or both entity_type and entity_id.",
            )
        return request.entity_type, request.entity_id

    def _get_entity_label(self, entity_type: ClaimEntityType | None, entity_id: uuid.UUID | None) -> str | None:
        if entity_type is None or entity_id is None:
            return None
        if entity_type == ClaimEntityType.PROJECT:
            project = self.db.get(Project, entity_id)
            return project.canonical_name if project else None
        if entity_type == ClaimEntityType.PHASE:
            phase = self.db.get(Phase, entity_id)
            return phase.phase_name if phase else None
        if entity_type == ClaimEntityType.REGION:
            region = self.db.get(Region, entity_id)
            return region.name if region else None
        if entity_type == ClaimEntityType.UTILITY:
            utility = self.db.get(Utility, entity_id)
            return utility.name if utility else None
        return None

    def _next_action_for_claim(self, claim: Claim) -> str:
        if claim.entity_id is None or claim.entity_type is None:
            return "link_claim"
        if claim.review_status in {
            ClaimReviewStatus.UNREVIEWED,
            ClaimReviewStatus.LINKED,
            ClaimReviewStatus.AMBIGUOUS,
            ClaimReviewStatus.NEEDS_MORE_REVIEW,
        }:
            return "review_claim"
        if claim.review_status == ClaimReviewStatus.ACCEPTED_CANDIDATE:
            return "accept_claim"
        return "complete"

    def _recommended_action_for_evidence(self, status_bucket: str) -> str:
        mapping = {
            "unclaimed": "create_claims",
            "claims_unlinked": "link_claims",
            "claims_pending_review": "review_claims",
            "review_complete": "complete",
        }
        return mapping[status_bucket]

    def _recommended_action_for_claim(self, claim: Claim, status_bucket: str) -> str:
        if status_bucket == "needs_link":
            return "link_claim"
        if claim.review_status == ClaimReviewStatus.ACCEPTED_CANDIDATE:
            return "accept_claim"
        if status_bucket == "needs_review":
            return "review_claim"
        return "complete"

    def _apply_claim_acceptance(self, claim: Claim) -> tuple[str, dict]:
        claim_value = claim.claim_value_json or {}
        if claim.entity_type == ClaimEntityType.PROJECT:
            project = self.db.get(Project, claim.entity_id)
            if project is None:
                raise HTTPException(status_code=400, detail="Target project not found")
            if claim.claim_type == ClaimType.PROJECT_NAME_MENTION:
                project.canonical_name = str(claim_value["project_name"])
                return "canonical_name", {"target_table": "projects", "field_name": "canonical_name", "accepted_value": project.canonical_name}
            if claim.claim_type == ClaimType.DEVELOPER_NAMED:
                project.developer = str(claim_value["developer_name"])
                return "developer", {"target_table": "projects", "field_name": "developer", "accepted_value": project.developer}
            if claim.claim_type == ClaimType.OPERATOR_NAMED:
                project.operator = str(claim_value["operator_name"])
                return "operator", {"target_table": "projects", "field_name": "operator", "accepted_value": project.operator}
            if claim.claim_type == ClaimType.LOCATION_STATE:
                project.state = str(claim_value["state"])
                return "state", {"target_table": "projects", "field_name": "state", "accepted_value": project.state}
            if claim.claim_type == ClaimType.LOCATION_COUNTY:
                project.county = str(claim_value["county"])
                return "county", {"target_table": "projects", "field_name": "county", "accepted_value": project.county}
            if claim.claim_type == ClaimType.ANNOUNCEMENT_DATE:
                project.announcement_date = claim_value["announcement_date"]
                return "announcement_date", {"target_table": "projects", "field_name": "announcement_date", "accepted_value": project.announcement_date.isoformat()}
            if claim.claim_type == ClaimType.LATEST_UPDATE_DATE:
                project.latest_update_date = claim_value["latest_update_date"]
                return "latest_update_date", {"target_table": "projects", "field_name": "latest_update_date", "accepted_value": project.latest_update_date.isoformat()}
            if claim.claim_type == ClaimType.UTILITY_NAMED:
                utility = self.db.query(Utility).filter(Utility.name == str(claim_value["utility_name"])).one_or_none()
                if utility is None:
                    raise HTTPException(status_code=400, detail="No matching utility found for accepted claim")
                project.utility_id = utility.id
                return "utility_id", {"target_table": "projects", "field_name": "utility_id", "accepted_value": str(utility.id)}
            if claim.claim_type == ClaimType.REGION_OR_RTO_NAMED:
                region_name = str(claim_value["region_name"])
                region = self.db.query(Region).filter((Region.name == region_name) | (Region.code == region_name)).one_or_none()
                if region is None:
                    raise HTTPException(status_code=400, detail="No matching region found for accepted claim")
                project.region_id = region.id
                return "region_id", {"target_table": "projects", "field_name": "region_id", "accepted_value": str(region.id)}

        if claim.entity_type == ClaimEntityType.PHASE:
            phase = self.db.get(Phase, claim.entity_id)
            if phase is None:
                raise HTTPException(status_code=400, detail="Target phase not found")
            if claim.claim_type == ClaimType.PHASE_NAME_MENTION:
                phase.phase_name = str(claim_value["phase_name"])
                return "phase_name", {"target_table": "phases", "field_name": "phase_name", "accepted_value": phase.phase_name}
            if claim.claim_type == ClaimType.ANNOUNCEMENT_DATE:
                phase.announcement_date = claim_value["announcement_date"]
                return "announcement_date", {"target_table": "phases", "field_name": "announcement_date", "accepted_value": phase.announcement_date.isoformat()}
            if claim.claim_type == ClaimType.TARGET_ENERGIZATION_DATE:
                phase.target_energization_date = claim_value["target_energization_date"]
                return "target_energization_date", {"target_table": "phases", "field_name": "target_energization_date", "accepted_value": phase.target_energization_date.isoformat()}
            if claim.claim_type == ClaimType.MODELED_LOAD_MW:
                return self._upsert_phase_load(
                    phase_id=phase.id,
                    load_kind=LoadKind.MODELED_PRIMARY,
                    value=float(claim_value["modeled_primary_load_mw"]),
                    field_name="modeled_primary_load_mw",
                    is_optional_expansion=False,
                )
            if claim.claim_type == ClaimType.OPTIONAL_EXPANSION_MW:
                return self._upsert_phase_load(
                    phase_id=phase.id,
                    load_kind=LoadKind.OPTIONAL_EXPANSION,
                    value=float(claim_value["optional_expansion_mw"]),
                    field_name="optional_expansion_mw",
                    is_optional_expansion=True,
                )

        raise HTTPException(status_code=400, detail="Claim type is not currently supported for normalized acceptance")

    def _upsert_phase_load(
        self,
        *,
        phase_id: uuid.UUID,
        load_kind: LoadKind,
        value: float,
        field_name: str,
        is_optional_expansion: bool,
    ) -> tuple[str, dict]:
        row = (
            self.db.query(PhaseLoad)
            .filter(PhaseLoad.phase_id == phase_id, PhaseLoad.load_kind == load_kind)
            .one_or_none()
        )
        if row is None:
            row = PhaseLoad(
                phase_id=phase_id,
                load_kind=load_kind,
                load_mw=value,
                load_basis_type=field_name,
                load_source="analyst_accept",
                load_confidence=None,
                is_optional_expansion=is_optional_expansion,
                is_firm=not is_optional_expansion,
            )
            self.db.add(row)
        else:
            row.load_mw = value
            row.load_basis_type = field_name
            row.load_source = "analyst_accept"
            row.is_optional_expansion = is_optional_expansion
            row.is_firm = not is_optional_expansion
        self.db.flush()
        return field_name, {"target_table": "phase_loads", "field_name": field_name, "accepted_value": value}
