from __future__ import annotations

from pydantic import BaseModel


class ProjectEnrichmentResponse(BaseModel):
    utility: str | None
    confidence: str | None
    source: str
