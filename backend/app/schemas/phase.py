from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class PhaseListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    phase_name: str
    phase_order: int | None
    announcement_date: date | None
    target_energization_date: date | None
    status: str | None
    notes: str | None
    modeled_primary_load_mw: int | float | None
    optional_expansion_mw: int | float | None
