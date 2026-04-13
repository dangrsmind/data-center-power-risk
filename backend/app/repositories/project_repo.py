from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.enums import LoadKind
from app.models.project import Phase, PhaseLoad, Project


@dataclass
class ProjectSummaryRow:
    project: Project
    modeled_primary_load_mw: Decimal | None
    phase_count: int


class ProjectRepository:
    def __init__(self, db: Session):
        self.db = db

    def _summary_stmt(self) -> Select:
        load_sum = (
            select(func.sum(PhaseLoad.load_mw))
            .select_from(Phase)
            .join(PhaseLoad, PhaseLoad.phase_id == Phase.id)
            .where(Phase.project_id == Project.id, PhaseLoad.load_kind == LoadKind.MODELED_PRIMARY)
            .scalar_subquery()
        )

        phase_count = (
            select(func.count(Phase.id))
            .where(Phase.project_id == Project.id)
            .scalar_subquery()
        )

        return select(Project, load_sum.label("modeled_primary_load_mw"), phase_count.label("phase_count"))

    def list_projects(self) -> list[ProjectSummaryRow]:
        rows = self.db.execute(self._summary_stmt().order_by(Project.created_at.desc())).all()
        return [
            ProjectSummaryRow(
                project=row[0],
                modeled_primary_load_mw=row[1],
                phase_count=int(row[2] or 0),
            )
            for row in rows
        ]

    def get_project(self, project_id: uuid.UUID) -> Project | None:
        return self.db.get(Project, project_id)

    def get_project_summary(self, project_id: uuid.UUID) -> ProjectSummaryRow | None:
        row = self.db.execute(self._summary_stmt().where(Project.id == project_id)).one_or_none()
        if row is None:
            return None
        return ProjectSummaryRow(project=row[0], modeled_primary_load_mw=row[1], phase_count=int(row[2] or 0))
