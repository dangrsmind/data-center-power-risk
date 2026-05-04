from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/discover", tags=["discover"])

# Workspace root = parents[4] of this file
# backend/app/api/routes/discover.py → parents[4] = workspace root
_DATA_DIR   = Path(__file__).parents[4] / "data" / "starter_sources"
_CSV_PATH   = _DATA_DIR / "discovered_sources_v0_1.csv"
_DEC_PATH   = _DATA_DIR / "discovery_decisions_v0_1.json"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

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


class DiscoverDecisionsRequest(BaseModel):
    approved_ids: list[str]
    rejected_ids: list[str]


class DiscoverDecisionsResponse(BaseModel):
    approved: list[str]
    rejected: list[str]
    updated_at: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_decisions() -> DiscoverDecisionsResponse:
    if not _DEC_PATH.exists():
        return DiscoverDecisionsResponse(approved=[], rejected=[], updated_at=None)
    with _DEC_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return DiscoverDecisionsResponse(
        approved=data.get("approved", []),
        rejected=data.get("rejected", []),
        updated_at=data.get("updated_at"),
    )


def _write_decisions(approved: list[str], rejected: list[str]) -> DiscoverDecisionsResponse:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    payload = {"approved": approved, "rejected": rejected, "updated_at": now}
    _DEC_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return DiscoverDecisionsResponse(approved=approved, rejected=rejected, updated_at=now)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

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


@router.get("/decisions", response_model=DiscoverDecisionsResponse)
def get_decisions() -> DiscoverDecisionsResponse:
    """Return the current persisted decisions (approved/rejected IDs)."""
    return _read_decisions()


@router.post("/decisions", response_model=DiscoverDecisionsResponse)
def save_decisions(body: DiscoverDecisionsRequest) -> DiscoverDecisionsResponse:
    """Persist the full set of approved and rejected discovery IDs."""
    # De-duplicate and remove any IDs that appear in both lists (approved wins)
    approved_set = set(body.approved_ids)
    rejected_set = set(body.rejected_ids) - approved_set
    return _write_decisions(
        approved=sorted(approved_set),
        rejected=sorted(rejected_set),
    )
