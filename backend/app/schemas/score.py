from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel


class ScoreDriver(BaseModel):
    signal: str
    contribution: float


class GraphFragilitySummary(BaseModel):
    most_likely_break_node: str
    unresolved_critical_nodes: int


class ProjectScoreResponse(BaseModel):
    project_id: uuid.UUID
    phase_id: uuid.UUID | None
    quarter: date | None
    deadline_date: date
    current_hazard: float
    deadline_probability: float
    project_stress_score: float
    regional_stress_score: float
    anomaly_score: float
    evidence_quality_score: float
    model_version: str
    scoring_method: str
    top_drivers: list[ScoreDriver]
    weak_signal_summary: dict[str, float | bool | None]
    graph_fragility_summary: GraphFragilitySummary
