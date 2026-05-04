from __future__ import annotations

import csv
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/discover", tags=["discover"])

# CSV lives at <workspace_root>/data/starter_sources/discovered_sources_v0_1.csv
# __file__ = backend/app/api/routes/discover.py → parents[4] = workspace root
_CSV_PATH = Path(__file__).parents[4] / "data" / "starter_sources" / "discovered_sources_v0_1.csv"


class DiscoveredSourceItem(BaseModel):
    discovery_id: str
    candidate_project_name: str
    developer: str
    state: str
    county: str
    source_url: str
    source_type: str
    source_date: str
    title: str
    extracted_text: str
    detected_load_mw: float | None
    detected_region: str
    detected_utility: str
    confidence: str
    requires_review_reason: str
    discovery_method: str
    retrieved_at: str


@router.get("/sources", response_model=list[DiscoveredSourceItem])
def list_discovered_sources() -> list[DiscoveredSourceItem]:
    """Return discovered sources from the CSV written by the discovery script."""
    if not _CSV_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=f"discovered_sources_v0_1.csv not found at {_CSV_PATH}. "
                   "Run `python3 scripts/discover_starter_dataset.py` first.",
        )
    sources: list[DiscoveredSourceItem] = []
    with open(_CSV_PATH, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            raw_mw = row.get("detected_load_mw", "").strip()
            try:
                mw: float | None = float(raw_mw) if raw_mw else None
            except ValueError:
                mw = None
            sources.append(DiscoveredSourceItem(
                discovery_id=row.get("discovery_id", ""),
                candidate_project_name=row.get("candidate_project_name", ""),
                developer=row.get("developer", ""),
                state=row.get("state", ""),
                county=row.get("county", ""),
                source_url=row.get("source_url", ""),
                source_type=row.get("source_type", ""),
                source_date=row.get("source_date", ""),
                title=row.get("title", ""),
                extracted_text=row.get("extracted_text", ""),
                detected_load_mw=mw,
                detected_region=row.get("detected_region", ""),
                detected_utility=row.get("detected_utility", ""),
                confidence=row.get("confidence", ""),
                requires_review_reason=row.get("requires_review_reason", ""),
                discovery_method=row.get("discovery_method", ""),
                retrieved_at=row.get("retrieved_at", ""),
            ))
    return sources
