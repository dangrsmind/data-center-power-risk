from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.enums import ClaimEntityType
from app.models.evidence import Claim, Evidence, FieldProvenance


@dataclass
class LinkedEvidenceRow:
    evidence: Evidence
    claim_ids: list[uuid.UUID]
    field_names: list[str]
    related_phase_ids: list[uuid.UUID]
    related_event_ids: list[uuid.UUID]


class EvidenceRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_explicitly_linked_evidence(
        self,
        project_id: uuid.UUID,
        phase_ids: list[uuid.UUID],
        event_ids: list[uuid.UUID],
    ) -> list[LinkedEvidenceRow]:
        claim_filters = [
            and_(Claim.entity_type == ClaimEntityType.PROJECT, Claim.entity_id == project_id),
        ]
        provenance_filters = [
            and_(FieldProvenance.entity_type == ClaimEntityType.PROJECT, FieldProvenance.entity_id == project_id),
        ]

        if phase_ids:
            claim_filters.append(and_(Claim.entity_type == ClaimEntityType.PHASE, Claim.entity_id.in_(phase_ids)))
            provenance_filters.append(
                and_(FieldProvenance.entity_type == ClaimEntityType.PHASE, FieldProvenance.entity_id.in_(phase_ids))
            )
        if event_ids:
            claim_filters.append(and_(Claim.entity_type == ClaimEntityType.EVENT, Claim.entity_id.in_(event_ids)))
            provenance_filters.append(
                and_(FieldProvenance.entity_type == ClaimEntityType.EVENT, FieldProvenance.entity_id.in_(event_ids))
            )

        claims = list(self.db.execute(select(Claim).where(or_(*claim_filters))).scalars().all())
        provenance_rows = list(
            self.db.execute(select(FieldProvenance).where(or_(*provenance_filters))).scalars().all()
        )

        evidence_ids = {claim.evidence_id for claim in claims} | {row.evidence_id for row in provenance_rows}
        if not evidence_ids:
            return []

        evidence_rows = list(
            self.db.execute(
                select(Evidence)
                .where(Evidence.id.in_(evidence_ids))
                .order_by(Evidence.source_date.desc(), Evidence.created_at.desc())
            ).scalars().all()
        )

        linked_map = {
            evidence.id: LinkedEvidenceRow(
                evidence=evidence,
                claim_ids=[],
                field_names=[],
                related_phase_ids=[],
                related_event_ids=[],
            )
            for evidence in evidence_rows
        }

        for claim in claims:
            linked = linked_map.get(claim.evidence_id)
            if linked is None:
                continue
            linked.claim_ids.append(claim.id)
            if claim.entity_type == ClaimEntityType.PHASE:
                linked.related_phase_ids.append(claim.entity_id)
            elif claim.entity_type == ClaimEntityType.EVENT:
                linked.related_event_ids.append(claim.entity_id)

        for row in provenance_rows:
            linked = linked_map.get(row.evidence_id)
            if linked is None:
                continue
            linked.field_names.append(row.field_name)
            if row.entity_type == ClaimEntityType.PHASE:
                linked.related_phase_ids.append(row.entity_id)
            elif row.entity_type == ClaimEntityType.EVENT:
                linked.related_event_ids.append(row.entity_id)

        result: list[LinkedEvidenceRow] = []
        for evidence in evidence_rows:
            linked = linked_map[evidence.id]
            linked.claim_ids = sorted(set(linked.claim_ids))
            linked.field_names = sorted(set(linked.field_names))
            linked.related_phase_ids = sorted(set(linked.related_phase_ids))
            linked.related_event_ids = sorted(set(linked.related_event_ids))
            result.append(linked)
        return result
