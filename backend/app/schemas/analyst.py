from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.core.enums import EventFamily


class EventListItem(BaseModel):
    event_id: uuid.UUID
    event_family: EventFamily
    event_scope: str
    event_date: date
    phase_id: uuid.UUID | None
    phase_name: str | None
    region_id: uuid.UUID | None
    region_name: str | None
    utility_id: uuid.UUID | None
    utility_name: str | None
    severity: str | None
    reason_class: str | None
    confidence: str | None
    evidence_class: str | None
    causal_strength: str
    stress_direction: str
    weak_label_weight: float | None
    adjudicated: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ProjectEventsResponse(BaseModel):
    project_id: uuid.UUID
    project_name: str
    events: list[EventListItem]


class StressSignalItem(BaseModel):
    stress_observation_id: uuid.UUID
    signal_name: str
    source_signal_type: str
    quarter: str
    signal_value: float
    signal_weight: float
    derived_by: str | None
    run_id: str | None
    source_ref_ids: list | None
    created_at: datetime
    updated_at: datetime


class CurrentStressResponse(BaseModel):
    stress_score_id: uuid.UUID
    quarter: str
    project_stress_score: float | None
    regional_stress_score: float | None
    anomaly_score: float | None
    evidence_quality_score: float | None
    model_version: str
    run_id: str | None
    region_id: uuid.UUID | None
    region_name: str | None
    utility_id: uuid.UUID | None
    utility_name: str | None
    decomposition: dict | list | None
    created_at: datetime
    updated_at: datetime


class ProjectStressResponse(BaseModel):
    project_id: uuid.UUID
    project_name: str
    current_stress: CurrentStressResponse | None
    signals: list[StressSignalItem]


class ProjectHistoryItem(BaseModel):
    project_phase_quarter_id: uuid.UUID
    quarter: str
    phase_id: uuid.UUID
    phase_name: str
    snapshot_id: uuid.UUID | None
    snapshot_version: str | None
    quarterly_label_id: uuid.UUID | None
    stored_score_id: uuid.UUID | None
    current_hazard: float | None
    deadline_probability: float | None
    project_stress_score: float | None
    regional_stress_score: float | None
    anomaly_score: float | None
    E1_label: bool | None
    E2_label: bool | None
    E3_intensity: float | None
    E4_label: bool | None
    observability_score: float | None
    data_quality_score: float | None
    model_version: str | None
    run_id: str | None
    created_at: datetime
    updated_at: datetime


class ProjectHistoryResponse(BaseModel):
    project_id: uuid.UUID
    project_name: str
    history: list[ProjectHistoryItem]


class EvidenceListItem(BaseModel):
    evidence_id: uuid.UUID
    source_type: str
    source_date: date | None
    title: str | None
    source_url: str | None
    source_rank: int | None
    reviewer_status: str
    excerpt: str | None
    claim_ids: list[uuid.UUID]
    field_names: list[str]
    related_phase_ids: list[uuid.UUID]
    related_event_ids: list[uuid.UUID]
    created_at: datetime
    updated_at: datetime


class ProjectEvidenceResponse(BaseModel):
    project_id: uuid.UUID
    project_name: str
    evidence: list[EvidenceListItem]


class RiskSignalEvidenceSummary(BaseModel):
    evidence_count: int
    accepted_claim_count: int
    unresolved_claim_count: int


class ProjectRiskSignalResponse(BaseModel):
    project_id: uuid.UUID
    risk_signal: str
    risk_signal_score: float
    risk_signal_tier: str
    drivers: list[str]
    missing_fields: list[str]
    evidence_summary: RiskSignalEvidenceSummary
    method: str


class PredictionDriver(BaseModel):
    driver: str
    direction: str
    weight: float
    evidence: str


class ProjectPredictionResponse(BaseModel):
    model_version: str
    prediction_type: str
    p_delay_6mo: float
    p_delay_12mo: float
    p_delay_18mo: float
    risk_tier: str
    confidence: str
    drivers: list[PredictionDriver]
    missing_inputs: list[str]
    method_note: str = "This is a deterministic baseline, not a trained ML model."
    drivers: list[PredictionDriver]
    missing_inputs: list[str]
    confidence: str
