from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class ProjectListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    canonical_name: str
    developer: str | None
    operator: str | None
    state: str | None
    county: str | None
    latitude: float | None
    longitude: float | None
    lifecycle_state: str
    announcement_date: date | None
    latest_update_date: date | None
    modeled_primary_load_mw: int | float | None
    phase_count: int
    current_hazard: float
    deadline_probability: float
    risk_tier: str
    as_of_quarter: str | None


class ProjectDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    canonical_name: str
    developer: str | None
    operator: str | None
    state: str | None
    county: str | None
    latitude: float | None
    longitude: float | None
    lifecycle_state: str
    announcement_date: date | None
    latest_update_date: date | None
    region_id: uuid.UUID | None
    utility_id: uuid.UUID | None
    modeled_primary_load_mw: int | float | None
    phase_count: int


class ProjectCoordinatesRequest(BaseModel):
    latitude: float
    longitude: float
    coordinate_source: str = ""
    coordinate_confidence: str = ""


class ProjectEnrichmentResponse(BaseModel):
    utility: str | None
    confidence: str | None
    source: str | None
