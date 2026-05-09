from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CoordinateStatus = Literal["missing", "unverified", "verified", "needs_review"]
CoordinatePrecision = Literal[
    "exact_site",
    "parcel",
    "campus",
    "city_centroid",
    "county_centroid",
    "state_centroid",
    "approximate",
    "unknown",
]
CoordinateSource = Literal[
    "manual_review",
    "project_announcement",
    "utility_filing",
    "county_record",
    "company_website",
    "inferred_from_city",
    "imported_dataset",
    "other",
]

_LEGACY_COORDINATE_SOURCE: dict[str, str] = {
    "starter_dataset": "imported_dataset",
}


class ProjectCoordinateFields(BaseModel):
    latitude: float | None
    longitude: float | None
    coordinate_status: str | None
    coordinate_precision: str | None
    coordinate_source: str | None
    coordinate_source_url: str | None
    coordinate_notes: str | None
    coordinate_confidence: float | None
    coordinate_updated_at: datetime | None
    coordinate_verified_at: datetime | None


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
    coordinate_status: str | None
    coordinate_precision: str | None
    coordinate_source: str | None
    coordinate_source_url: str | None
    coordinate_notes: str | None
    coordinate_confidence: float | None
    coordinate_updated_at: datetime | None
    coordinate_verified_at: datetime | None
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
    coordinate_status: str | None
    coordinate_precision: str | None
    coordinate_source: str | None
    coordinate_source_url: str | None
    coordinate_notes: str | None
    coordinate_confidence: float | None
    coordinate_updated_at: datetime | None
    coordinate_verified_at: datetime | None
    lifecycle_state: str
    announcement_date: date | None
    latest_update_date: date | None
    region_id: uuid.UUID | None
    utility_id: uuid.UUID | None
    modeled_primary_load_mw: int | float | None
    phase_count: int


class ProjectCoordinatesRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    coordinate_precision: CoordinatePrecision
    coordinate_status: CoordinateStatus = "verified"
    coordinate_source: CoordinateSource | None = None
    coordinate_source_url: str | None = None
    coordinate_notes: str | None = None
    coordinate_confidence: float | None = Field(default=None, ge=0, le=1)
    changed_by: str | None = "manual"

    @field_validator("coordinate_source", mode="before")
    @classmethod
    def normalize_coordinate_source(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _LEGACY_COORDINATE_SOURCE.get(str(value), value)

    @field_validator("coordinate_source_url", "coordinate_notes", "changed_by", mode="before")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None


class ProjectMissingCoordinatesItem(BaseModel):
    id: uuid.UUID
    name: str
    developer: str | None
    utility: str | None
    state: str | None
    county: str | None
    city: str | None = None
    latitude: float | None
    longitude: float | None
    coordinate_status: str | None
    coordinate_precision: str | None
    coordinate_source: str | None
    coordinate_confidence: float | None


class ProjectCoordinateHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: uuid.UUID
    old_latitude: float | None
    old_longitude: float | None
    new_latitude: float | None
    new_longitude: float | None
    old_coordinate_precision: str | None
    new_coordinate_precision: str | None
    old_coordinate_status: str | None
    new_coordinate_status: str | None
    source: str | None
    source_url: str | None
    notes: str | None
    changed_by: str | None
    created_at: datetime


class ProjectEnrichmentResponse(BaseModel):
    utility: str | None
    confidence: str | None
    source: str | None
