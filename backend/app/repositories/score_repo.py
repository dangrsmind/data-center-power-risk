from __future__ import annotations

import uuid

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.quarterly import PhaseQuarterScore, ProjectPhaseQuarter


class ScoreRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_latest_project_score(self, project_id: uuid.UUID) -> PhaseQuarterScore | None:
        stmt = (
            select(PhaseQuarterScore)
            .join(ProjectPhaseQuarter, PhaseQuarterScore.project_phase_quarter_id == ProjectPhaseQuarter.id)
            .where(ProjectPhaseQuarter.project_id == project_id)
            .order_by(desc(ProjectPhaseQuarter.quarter), desc(PhaseQuarterScore.created_at))
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()
