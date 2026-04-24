from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.enums import ClaimReviewStatus
from app.models.evidence import Claim, Evidence, FieldProvenance


@dataclass
class EvidenceQueueRow:
    evidence: Evidence
    claim_count: int
    linked_claim_count: int
    accepted_claim_count: int
    reviewed_claim_count: int


class IngestionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_evidence(self, evidence: Evidence) -> Evidence:
        self.db.add(evidence)
        self.db.flush()
        self.db.refresh(evidence)
        return evidence

    def get_evidence(self, evidence_id: uuid.UUID) -> Evidence | None:
        return self.db.get(Evidence, evidence_id)

    def get_claim(self, claim_id: uuid.UUID) -> Claim | None:
        return self.db.get(Claim, claim_id)

    def create_claims(self, claims: list[Claim]) -> list[Claim]:
        self.db.add_all(claims)
        self.db.flush()
        for claim in claims:
            self.db.refresh(claim)
        return claims

    def list_evidence_queue(self) -> list[EvidenceQueueRow]:
        stmt = (
            select(
                Evidence,
                func.count(Claim.id).label("claim_count"),
                func.sum(
                    case(
                        (
                            Claim.entity_id.is_not(None) & Claim.entity_type.is_not(None),
                            1,
                        ),
                        else_=0,
                    )
                ).label("linked_claim_count"),
                func.sum(
                    case((Claim.review_status == ClaimReviewStatus.ACCEPTED, 1), else_=0)
                ).label("accepted_claim_count"),
                func.sum(
                    case(
                        (
                            Claim.review_status.in_(
                                [
                                    ClaimReviewStatus.ACCEPTED,
                                    ClaimReviewStatus.REJECTED,
                                    ClaimReviewStatus.AMBIGUOUS,
                                ]
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("reviewed_claim_count"),
            )
            .outerjoin(Claim, Claim.evidence_id == Evidence.id)
            .group_by(Evidence.id)
            .order_by(Evidence.source_date.desc().nullslast(), Evidence.created_at.desc())
        )
        rows = self.db.execute(stmt).all()
        return [
            EvidenceQueueRow(
                evidence=row[0],
                claim_count=int(row[1] or 0),
                linked_claim_count=int(row[2] or 0),
                accepted_claim_count=int(row[3] or 0),
                reviewed_claim_count=int(row[4] or 0),
            )
            for row in rows
        ]

    def list_claim_queue(self) -> list[Claim]:
        stmt = select(Claim).order_by(Claim.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def get_evidence_provenance_count(self, evidence_id: uuid.UUID) -> int:
        stmt = select(func.count(FieldProvenance.id)).where(FieldProvenance.evidence_id == evidence_id)
        return int(self.db.execute(stmt).scalar_one() or 0)

    def list_claims_by_evidence(self, evidence_id: uuid.UUID) -> list[Claim]:
        stmt = select(Claim).where(Claim.evidence_id == evidence_id).order_by(Claim.created_at.asc())
        return list(self.db.execute(stmt).scalars().all())

    def list_provenance_by_evidence(self, evidence_id: uuid.UUID) -> list[FieldProvenance]:
        stmt = (
            select(FieldProvenance)
            .where(FieldProvenance.evidence_id == evidence_id)
            .order_by(FieldProvenance.created_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def create_field_provenance(self, provenance: FieldProvenance) -> FieldProvenance:
        self.db.add(provenance)
        self.db.flush()
        self.db.refresh(provenance)
        return provenance
