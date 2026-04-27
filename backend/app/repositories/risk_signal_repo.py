from __future__ import annotations

import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.enums import ClaimEntityType
from app.models.evidence import Claim, Evidence, FieldProvenance


class RiskSignalRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_project_scope_claims(self, project_id: uuid.UUID, phase_ids: list[uuid.UUID]) -> list[Claim]:
        filters = [and_(Claim.entity_type == ClaimEntityType.PROJECT, Claim.entity_id == project_id)]
        if phase_ids:
            filters.append(and_(Claim.entity_type == ClaimEntityType.PHASE, Claim.entity_id.in_(phase_ids)))
        stmt = select(Claim).where(or_(*filters)).order_by(Claim.created_at.asc())
        return list(self.db.execute(stmt).scalars().all())

    def list_project_scope_provenance(self, project_id: uuid.UUID, phase_ids: list[uuid.UUID]) -> list[FieldProvenance]:
        filters = [and_(FieldProvenance.entity_type == ClaimEntityType.PROJECT, FieldProvenance.entity_id == project_id)]
        if phase_ids:
            filters.append(and_(FieldProvenance.entity_type == ClaimEntityType.PHASE, FieldProvenance.entity_id.in_(phase_ids)))
        stmt = select(FieldProvenance).where(or_(*filters)).order_by(FieldProvenance.created_at.asc())
        return list(self.db.execute(stmt).scalars().all())

    def count_project_scope_evidence(self, project_id: uuid.UUID, phase_ids: list[uuid.UUID]) -> int:
        claim_filters = [and_(Claim.entity_type == ClaimEntityType.PROJECT, Claim.entity_id == project_id)]
        prov_filters = [and_(FieldProvenance.entity_type == ClaimEntityType.PROJECT, FieldProvenance.entity_id == project_id)]
        if phase_ids:
            claim_filters.append(and_(Claim.entity_type == ClaimEntityType.PHASE, Claim.entity_id.in_(phase_ids)))
            prov_filters.append(and_(FieldProvenance.entity_type == ClaimEntityType.PHASE, FieldProvenance.entity_id.in_(phase_ids)))

        claim_stmt = select(Claim.evidence_id).where(or_(*claim_filters))
        prov_stmt = select(FieldProvenance.evidence_id).where(or_(*prov_filters))
        evidence_ids = set(self.db.execute(claim_stmt).scalars().all()) | set(self.db.execute(prov_stmt).scalars().all())
        return len({evidence_id for evidence_id in evidence_ids if evidence_id is not None})
