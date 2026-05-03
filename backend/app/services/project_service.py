from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.reference import Region, Utility
from app.repositories import (
    EvidenceRepository,
    EventRepository,
    PhaseRepository,
    ProjectRepository,
    ScoreRepository,
    SnapshotRepository,
    StressRepository,
)
from app.schemas.analyst import (
    CurrentStressResponse,
    EvidenceListItem,
    EventListItem,
    ProjectEvidenceResponse,
    ProjectEventsResponse,
    ProjectHistoryItem,
    ProjectHistoryResponse,
    ProjectRiskSignalResponse,
    ProjectStressResponse,
    StressSignalItem,
)
from app.schemas.phase import PhaseListItem
from app.schemas.project import ProjectDetail, ProjectEnrichmentResponse, ProjectListItem
from app.schemas.score import ProjectScoreResponse
from app.services.mock_scoring_service import MockScoringInputs, MockScoringService
from app.services.risk_signal_service import RiskSignalService


def _json_number(value: Decimal | int | float | None) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        normalized = value.normalize()
        if normalized == normalized.to_integral():
            return int(normalized)
        return float(value)
    return value


def _format_quarter(value: date | None) -> str | None:
    if value is None:
        return None
    quarter_number = ((value.month - 1) // 3) + 1
    return f"{value.year}-Q{quarter_number}"


def _risk_tier(deadline_probability: float) -> str:
    if deadline_probability >= 0.66:
        return "high"
    if deadline_probability >= 0.33:
        return "medium"
    return "low"


@dataclass
class ProjectDashboardScore:
    current_hazard: float
    deadline_probability: float
    as_of_quarter: str | None


class ProjectService:
    def __init__(self, db: Session):
        self.db = db
        self.evidence_repo = EvidenceRepository(db)
        self.event_repo = EventRepository(db)
        self.project_repo = ProjectRepository(db)
        self.phase_repo = PhaseRepository(db)
        self.score_repo = ScoreRepository(db)
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
                current_hazard=dashboard_score.current_hazard,
                deadline_probability=dashboard_score.deadline_probability,
                risk_tier=_risk_tier(dashboard_score.deadline_probability),
                as_of_quarter=dashboard_score.as_of_quarter,
            )
            for row in rows
            for dashboard_score in [self._get_project_dashboard_score(row.project)]
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

    def get_project_enrichment(self, project_id: uuid.UUID) -> ProjectEnrichmentResponse:
        project = self.project_repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if project.utility_id is None:
            return ProjectEnrichmentResponse(utility=None, confidence=None, source=None)
        utility = self.db.get(Utility, project.utility_id)
        if utility is None:
            return ProjectEnrichmentResponse(utility=None, confidence=None, source=None)
        return ProjectEnrichmentResponse(
            utility=utility.name,
            confidence="medium",
            source="HIFLD",
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

        return self._build_project_score_response(project)

    def get_project_events(self, project_id: uuid.UUID) -> ProjectEventsResponse:
        project = self.project_repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        rows = self.event_repo.list_by_project(project_id)
        return ProjectEventsResponse(
            project_id=project.id,
            project_name=project.canonical_name,
            events=[
                EventListItem(
                    event_id=row.event.id,
                    event_family=row.event.event_family,
                    event_scope=row.event.event_scope.value,
                    event_date=row.event.event_date,
                    phase_id=row.event.phase_id,
                    phase_name=row.phase_name,
                    region_id=row.event.region_id,
                    region_name=row.region_name,
                    utility_id=row.event.utility_id,
                    utility_name=row.utility_name,
                    severity=row.event.severity,
                    reason_class=row.event.reason_class,
                    confidence=row.event.confidence,
                    evidence_class=row.event.evidence_class,
                    causal_strength=row.event.causal_strength.value,
                    stress_direction=row.event.stress_direction.value,
                    weak_label_weight=_json_number(row.event.weak_label_weight),
                    adjudicated=row.event.adjudicated,
                    notes=row.event.notes,
                    created_at=row.event.created_at,
                    updated_at=row.event.updated_at,
                )
                for row in rows
            ],
        )

    def get_project_stress(self, project_id: uuid.UUID) -> ProjectStressResponse:
        project = self.project_repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        current_score = self.stress_repo.get_latest_project_score(project_id)
        observations = self.stress_repo.list_project_observations(project_id)

        current_stress = None
        if current_score is not None:
            region = self.db.get(Region, current_score.region_id) if current_score.region_id else None
            utility = self.db.get(Utility, current_score.utility_id) if current_score.utility_id else None
            current_stress = CurrentStressResponse(
                stress_score_id=current_score.id,
                quarter=_format_quarter(current_score.quarter),
                project_stress_score=_json_number(current_score.project_stress_score),
                regional_stress_score=_json_number(current_score.regional_stress_score),
                anomaly_score=_json_number(current_score.anomaly_score),
                evidence_quality_score=_json_number(current_score.confidence_score),
                model_version=current_score.model_version,
                run_id=current_score.run_id,
                region_id=current_score.region_id,
                region_name=region.name if region else None,
                utility_id=current_score.utility_id,
                utility_name=utility.name if utility else None,
                decomposition=current_score.decomposition_json,
                created_at=current_score.created_at,
                updated_at=current_score.updated_at,
            )

        return ProjectStressResponse(
            project_id=project.id,
            project_name=project.canonical_name,
            current_stress=current_stress,
            signals=[
                StressSignalItem(
                    stress_observation_id=row.id,
                    signal_name=row.signal_name,
                    source_signal_type=row.source_signal_type.value,
                    quarter=_format_quarter(row.quarter),
                    signal_value=float(row.signal_value),
                    signal_weight=float(row.signal_weight),
                    derived_by=row.derived_by,
                    run_id=row.run_id,
                    source_ref_ids=row.source_ref_ids,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in observations
            ],
        )

    def get_project_history(self, project_id: uuid.UUID) -> ProjectHistoryResponse:
        project = self.project_repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        history_rows = self.snapshot_repo.list_project_history_rows(project_id)
        stress_scores = self.stress_repo.list_project_scores(project_id)
        stored_scores = self.score_repo.list_latest_project_scores_by_phase_quarter(project_id)

        stress_by_quarter = {row.quarter: row for row in stress_scores}
        stored_by_phase_quarter = {row.phase_quarter.id: row for row in stored_scores}

        return ProjectHistoryResponse(
            project_id=project.id,
            project_name=project.canonical_name,
            history=[
                ProjectHistoryItem(
                    project_phase_quarter_id=row.phase_quarter.id,
                    quarter=_format_quarter(row.phase_quarter.quarter),
                    phase_id=row.phase.id,
                    phase_name=row.phase.phase_name,
                    snapshot_id=row.snapshot.id if row.snapshot else None,
                    snapshot_version=row.snapshot.snapshot_version if row.snapshot else None,
                    quarterly_label_id=row.label.id if row.label else None,
                    stored_score_id=stored_by_phase_quarter[row.phase_quarter.id].score.id
                    if row.phase_quarter.id in stored_by_phase_quarter
                    else None,
                    current_hazard=_json_number(stored_by_phase_quarter[row.phase_quarter.id].score.quarterly_hazard)
                    if row.phase_quarter.id in stored_by_phase_quarter
                    else None,
                    deadline_probability=_json_number(
                        stored_by_phase_quarter[row.phase_quarter.id].score.deadline_probability
                    )
                    if row.phase_quarter.id in stored_by_phase_quarter
                    else None,
                    project_stress_score=_json_number(stress_by_quarter[row.phase_quarter.quarter].project_stress_score)
                    if row.phase_quarter.quarter in stress_by_quarter
                    else None,
                    regional_stress_score=_json_number(
                        stress_by_quarter[row.phase_quarter.quarter].regional_stress_score
                    )
                    if row.phase_quarter.quarter in stress_by_quarter
                    else None,
                    anomaly_score=_json_number(stress_by_quarter[row.phase_quarter.quarter].anomaly_score)
                    if row.phase_quarter.quarter in stress_by_quarter
                    else None,
                    E1_label=row.label.E1_label if row.label else None,
                    E2_label=row.label.E2_label if row.label else None,
                    E3_intensity=_json_number(row.label.E3_intensity) if row.label else None,
                    E4_label=row.label.E4_label if row.label else None,
                    observability_score=_json_number(row.snapshot.observability_score) if row.snapshot else None,
                    data_quality_score=_json_number(row.snapshot.data_quality_score) if row.snapshot else None,
                    model_version=(
                        stored_by_phase_quarter[row.phase_quarter.id].score.model_version
                        if row.phase_quarter.id in stored_by_phase_quarter
                        else (stress_by_quarter[row.phase_quarter.quarter].model_version if row.phase_quarter.quarter in stress_by_quarter else None)
                    ),
                    run_id=(
                        stress_by_quarter[row.phase_quarter.quarter].run_id
                        if row.phase_quarter.quarter in stress_by_quarter
                        else None
                    ),
                    created_at=row.phase_quarter.created_at,
                    updated_at=row.phase_quarter.updated_at,
                )
                for row in history_rows
            ],
        )

    def get_project_evidence(self, project_id: uuid.UUID) -> ProjectEvidenceResponse:
        project = self.project_repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        phase_ids = self.phase_repo.list_phase_ids_by_project(project_id)
        event_ids = self.event_repo.list_explicit_project_event_ids(project_id)
        evidence_rows = self.evidence_repo.list_explicitly_linked_evidence(project_id, phase_ids, event_ids)

        return ProjectEvidenceResponse(
            project_id=project.id,
            project_name=project.canonical_name,
            evidence=[
                EvidenceListItem(
                    evidence_id=row.evidence.id,
                    source_type=row.evidence.source_type.value,
                    source_date=row.evidence.source_date,
                    title=row.evidence.title,
                    source_url=row.evidence.source_url,
                    source_rank=row.evidence.source_rank,
                    reviewer_status=row.evidence.reviewer_status.value,
                    excerpt=row.evidence.extracted_text,
                    claim_ids=row.claim_ids,
                    field_names=row.field_names,
                    related_phase_ids=row.related_phase_ids,
                    related_event_ids=row.related_event_ids,
                    created_at=row.evidence.created_at,
                    updated_at=row.evidence.updated_at,
                )
                for row in evidence_rows
            ],
        )

    def get_project_risk_signal(self, project_id: uuid.UUID) -> ProjectRiskSignalResponse:
        return RiskSignalService(self.db).get_project_risk_signal(project_id)

    def _build_project_score_response(self, project: Project) -> ProjectScoreResponse:
        phase_quarter = self.snapshot_repo.get_latest_project_phase_quarter(project.id)
        snapshot = self.snapshot_repo.get_latest_project_snapshot(project.id)
        labels = self.snapshot_repo.get_latest_project_labels(project.id)
        stress_score = self.stress_repo.get_latest_project_score(project.id)

        return self.mock_scoring_service.score_project(
            MockScoringInputs(
                project=project,
                phase_quarter=phase_quarter,
                snapshot=snapshot,
                labels=labels,
                stress_score=stress_score,
            )
        )

    def _get_project_dashboard_score(self, project: Project) -> ProjectDashboardScore:
        latest_stored_score = self.score_repo.get_latest_project_score_row(project.id)
        if latest_stored_score is not None:
            quarterly_hazard = _json_number(latest_stored_score.score.quarterly_hazard)
            deadline_probability = _json_number(latest_stored_score.score.deadline_probability)
            if isinstance(quarterly_hazard, (int, float)) and isinstance(deadline_probability, (int, float)):
                return ProjectDashboardScore(
                    current_hazard=float(quarterly_hazard),
                    deadline_probability=float(deadline_probability),
                    as_of_quarter=_format_quarter(latest_stored_score.phase_quarter.quarter),
                )

        score = self._build_project_score_response(project)
        return ProjectDashboardScore(
            current_hazard=score.current_hazard,
            deadline_probability=score.deadline_probability,
            as_of_quarter=_format_quarter(score.quarter),
        )
