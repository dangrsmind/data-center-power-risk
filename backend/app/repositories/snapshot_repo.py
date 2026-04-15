from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.project import Phase
from app.models.quarterly import ProjectPhaseQuarter, QuarterlyLabel, QuarterlySnapshot


@dataclass
class ProjectHistoryRow:
    phase_quarter: ProjectPhaseQuarter
    phase: Phase
    snapshot: QuarterlySnapshot | None
    label: QuarterlyLabel | None


class SnapshotRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_latest_project_snapshot(self, project_id: uuid.UUID) -> QuarterlySnapshot | None:
        stmt = (
            select(QuarterlySnapshot)
            .join(ProjectPhaseQuarter, QuarterlySnapshot.project_phase_quarter_id == ProjectPhaseQuarter.id)
            .where(ProjectPhaseQuarter.project_id == project_id)
            .order_by(desc(ProjectPhaseQuarter.quarter), desc(QuarterlySnapshot.created_at))
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_latest_project_labels(self, project_id: uuid.UUID) -> QuarterlyLabel | None:
        stmt = (
            select(QuarterlyLabel)
            .join(ProjectPhaseQuarter, QuarterlyLabel.project_phase_quarter_id == ProjectPhaseQuarter.id)
            .where(ProjectPhaseQuarter.project_id == project_id)
            .order_by(desc(ProjectPhaseQuarter.quarter), desc(QuarterlyLabel.created_at))
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_latest_project_phase_quarter(self, project_id: uuid.UUID) -> ProjectPhaseQuarter | None:
        stmt = (
            select(ProjectPhaseQuarter)
            .where(ProjectPhaseQuarter.project_id == project_id)
            .order_by(desc(ProjectPhaseQuarter.quarter), desc(ProjectPhaseQuarter.created_at))
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_project_history_rows(self, project_id: uuid.UUID) -> list[ProjectHistoryRow]:
        stmt = (
            select(ProjectPhaseQuarter, Phase, QuarterlySnapshot, QuarterlyLabel)
            .join(Phase, ProjectPhaseQuarter.phase_id == Phase.id)
            .outerjoin(QuarterlySnapshot, QuarterlySnapshot.project_phase_quarter_id == ProjectPhaseQuarter.id)
            .outerjoin(QuarterlyLabel, QuarterlyLabel.project_phase_quarter_id == ProjectPhaseQuarter.id)
            .where(ProjectPhaseQuarter.project_id == project_id)
            .order_by(ProjectPhaseQuarter.quarter.desc(), Phase.phase_order.asc(), ProjectPhaseQuarter.created_at.desc())
        )
        rows = self.db.execute(stmt).all()
        return [
            ProjectHistoryRow(
                phase_quarter=row[0],
                phase=row[1],
                snapshot=row[2],
                label=row[3],
            )
            for row in rows
        ]
