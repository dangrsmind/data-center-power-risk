from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel


class CandidateImportItemResult(BaseModel):
    row_number: int
    canonical_name: str | None
    project_id: uuid.UUID | None = None
    status: Literal["created", "updated", "skipped", "rejected"]
    message: str
    warnings: list[str] = []


class CandidateImportResponse(BaseModel):
    created: list[CandidateImportItemResult]
    updated: list[CandidateImportItemResult]
    skipped: list[CandidateImportItemResult]
    rejected: list[CandidateImportItemResult]
