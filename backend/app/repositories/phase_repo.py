from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.enums import LoadKind
from app.models.project import Phase, PhaseLoad


@dataclass
class PhaseSummaryRow:
    phase: Phase
    modeled_primary_load_mw: Decimal | None
    optional_expansion_mw: Decimal | None


class PhaseRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_phase_ids_by_project(self, project_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(Phase.id).where(Phase.project_id == project_id)
        return list(self.db.execute(stmt).scalars().all())

    def list_by_project(self, project_id: uuid.UUID) -> list[PhaseSummaryRow]:
        modeled_primary = func.sum(
            case((PhaseLoad.load_kind == LoadKind.MODELED_PRIMARY, PhaseLoad.load_mw), else_=0)
        )
        optional_expansion = func.sum(
            case((PhaseLoad.load_kind == LoadKind.OPTIONAL_EXPANSION, PhaseLoad.load_mw), else_=0)
        )

        stmt = (
            select(
                Phase,
                modeled_primary.label("modeled_primary_load_mw"),
                optional_expansion.label("optional_expansion_mw"),
            )
            .outerjoin(PhaseLoad, PhaseLoad.phase_id == Phase.id)
            .where(Phase.project_id == project_id)
            .group_by(Phase.id)
            .order_by(Phase.phase_order.is_(None), Phase.phase_order.asc(), Phase.created_at.asc())
        )
        rows = self.db.execute(stmt).all()
        return [
            PhaseSummaryRow(
                phase=row[0],
                modeled_primary_load_mw=row[1],
                optional_expansion_mw=row[2],
            )
            for row in rows
        ]
