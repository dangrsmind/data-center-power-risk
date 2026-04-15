from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.quarterly import PhaseQuarterScore, ProjectPhaseQuarter


@dataclass
class LatestProjectScoreRow:
    score: PhaseQuarterScore
    phase_quarter: ProjectPhaseQuarter


class ScoreRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_latest_project_score_row(self, project_id: uuid.UUID) -> LatestProjectScoreRow | None:
        stmt = (
            select(PhaseQuarterScore, ProjectPhaseQuarter)
            .join(ProjectPhaseQuarter, PhaseQuarterScore.project_phase_quarter_id == ProjectPhaseQuarter.id)
            .where(ProjectPhaseQuarter.project_id == project_id)
            .order_by(desc(ProjectPhaseQuarter.quarter), desc(PhaseQuarterScore.created_at))
            .limit(1)
        )
        row = self.db.execute(stmt).one_or_none()
        if row is None:
            return None
        return LatestProjectScoreRow(score=row[0], phase_quarter=row[1])

    def get_latest_project_score(self, project_id: uuid.UUID) -> PhaseQuarterScore | None:
        row = self.get_latest_project_score_row(project_id)
        return row.score if row is not None else None

    def list_latest_project_scores_by_phase_quarter(self, project_id: uuid.UUID) -> list[LatestProjectScoreRow]:
        stmt = (
            select(PhaseQuarterScore, ProjectPhaseQuarter)
            .join(ProjectPhaseQuarter, PhaseQuarterScore.project_phase_quarter_id == ProjectPhaseQuarter.id)
            .where(ProjectPhaseQuarter.project_id == project_id)
            .order_by(ProjectPhaseQuarter.quarter.desc(), PhaseQuarterScore.created_at.desc())
        )
        rows = self.db.execute(stmt).all()
        latest: dict[uuid.UUID, LatestProjectScoreRow] = {}
        for score, phase_quarter in rows:
            if phase_quarter.id not in latest:
                latest[phase_quarter.id] = LatestProjectScoreRow(score=score, phase_quarter=phase_quarter)
        return list(latest.values())
