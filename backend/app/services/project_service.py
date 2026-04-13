from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories import PhaseRepository, ProjectRepository, SnapshotRepository, StressRepository
from app.schemas.phase import PhaseListItem
from app.schemas.project import ProjectDetail, ProjectListItem
from app.schemas.score import ProjectScoreResponse
from app.services.mock_scoring_service import MockScoringInputs, MockScoringService


def _json_number(value: Decimal | int | float | None) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        normalized = value.normalize()
        if normalized == normalized.to_integral():
            return int(normalized)
        return float(value)
    return value


class ProjectService:
    def __init__(self, db: Session):
        self.project_repo = ProjectRepository(db)
        self.phase_repo = PhaseRepository(db)
        self.snapshot_repo = SnapshotRepository(db)
        self.stress_repo = StressRepository(db)
        self.mock_scoring_service = MockScoringService()

    def list_projects(self) -> list[ProjectListItem]:
        rows = self.project_repo.list_projects()
        return [
            ProjectListItem(
                id=row.project.id,
                canonical_name=row.project.canonical_name,
                developer=row.project.developer,
                operator=row.project.operator,
                state=row.project.state,
                county=row.project.county,
                lifecycle_state=row.project.lifecycle_state.value,
                announcement_date=row.project.announcement_date,
                latest_update_date=row.project.latest_update_date,
                modeled_primary_load_mw=_json_number(row.modeled_primary_load_mw),
                phase_count=row.phase_count,
            )
            for row in rows
        ]

    def get_project(self, project_id: uuid.UUID) -> ProjectDetail:
        row = self.project_repo.get_project_summary(project_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Project not found")
        project = row.project
        return ProjectDetail(
            id=project.id,
            canonical_name=project.canonical_name,
            developer=project.developer,
            operator=project.operator,
            state=project.state,
            county=project.county,
            lifecycle_state=project.lifecycle_state.value,
            announcement_date=project.announcement_date,
            latest_update_date=project.latest_update_date,
            region_id=project.region_id,
            utility_id=project.utility_id,
            modeled_primary_load_mw=_json_number(row.modeled_primary_load_mw),
            phase_count=row.phase_count,
        )

    def list_project_phases(self, project_id: uuid.UUID) -> list[PhaseListItem]:
        if self.project_repo.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found")
        rows = self.phase_repo.list_by_project(project_id)
        return [
            PhaseListItem(
                id=row.phase.id,
                project_id=row.phase.project_id,
                phase_name=row.phase.phase_name,
                phase_order=row.phase.phase_order,
                announcement_date=row.phase.announcement_date,
                target_energization_date=row.phase.target_energization_date,
                status=row.phase.status,
                notes=row.phase.notes,
                modeled_primary_load_mw=_json_number(row.modeled_primary_load_mw),
                optional_expansion_mw=_json_number(row.optional_expansion_mw),
            )
            for row in rows
        ]

    def get_project_score(self, project_id: uuid.UUID) -> ProjectScoreResponse:
        project = self.project_repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        phase_quarter = self.snapshot_repo.get_latest_project_phase_quarter(project_id)
        snapshot = self.snapshot_repo.get_latest_project_snapshot(project_id)
        labels = self.snapshot_repo.get_latest_project_labels(project_id)
        stress_score = self.stress_repo.get_latest_project_score(project_id)

        return self.mock_scoring_service.score_project(
            MockScoringInputs(
                project=project,
                phase_quarter=phase_quarter,
                snapshot=snapshot,
                labels=labels,
                stress_score=stress_score,
            )
        )
