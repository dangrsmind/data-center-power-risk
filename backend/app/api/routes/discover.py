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
_MAN_PATH   = _DATA_DIR / "manual_source_captures_v0_1.json"


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


class ManualCaptureItem(BaseModel):
    discovery_id: str
    manual_extracted_text: str
    source_date: str
    notes: str
    captured_at: str
    captured_by: str
    latitude: float | None = None
    longitude: float | None = None
    coordinate_source: str = ""
    coordinate_confidence: str = ""


class ManualCaptureRequest(BaseModel):
    discovery_id: str
    manual_extracted_text: str
    source_date: str = ""
    notes: str = ""
    captured_by: str = "analyst"
    latitude: float | None = None
    longitude: float | None = None
    coordinate_source: str = ""
    coordinate_confidence: str = ""


class ManualCapturesResponse(BaseModel):
    captures: list[ManualCaptureItem]
    updated_at: str | None


# ---------------------------------------------------------------------------
# Helpers — decisions
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
# Helpers — manual captures
# ---------------------------------------------------------------------------

def _read_manual_captures() -> dict[str, dict]:
    """Return the raw captures dict keyed by discovery_id."""
    if not _MAN_PATH.exists():
        return {}
    with _MAN_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_manual_capture(
    discovery_id: str,
    manual_extracted_text: str,
    source_date: str,
    notes: str,
    captured_by: str,
    latitude: float | None,
    longitude: float | None,
    coordinate_source: str,
    coordinate_confidence: str,
) -> ManualCaptureItem:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    captures = _read_manual_captures()
    now = datetime.now(timezone.utc).isoformat()
    entry: dict = {
        "manual_extracted_text": manual_extracted_text,
        "source_date": source_date,
        "notes": notes,
        "captured_at": now,
        "captured_by": captured_by,
        "latitude": latitude,
        "longitude": longitude,
        "coordinate_source": coordinate_source,
        "coordinate_confidence": coordinate_confidence,
    }
    captures[discovery_id] = entry
    _MAN_PATH.write_text(json.dumps(captures, indent=2, ensure_ascii=False), encoding="utf-8")
    return ManualCaptureItem(discovery_id=discovery_id, **entry)


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


@router.get("/manual-captures", response_model=ManualCapturesResponse)
def get_manual_captures() -> ManualCapturesResponse:
    """Return all persisted manual text captures."""
    raw = _read_manual_captures()
    captures = [
        ManualCaptureItem(discovery_id=did, **entry)
        for did, entry in raw.items()
    ]
    # updated_at = most recent captured_at across all entries
    updated_at: str | None = None
    if captures:
        updated_at = max(c.captured_at for c in captures)
    return ManualCapturesResponse(captures=captures, updated_at=updated_at)


@router.post("/manual-captures", response_model=ManualCaptureItem)
def save_manual_capture(body: ManualCaptureRequest) -> ManualCaptureItem:
    """Persist a single manual text capture for a discovery row."""
    if not body.manual_extracted_text.strip():
        raise HTTPException(status_code=422, detail="manual_extracted_text must not be empty.")
    # Validate coordinates if provided
    if body.latitude is not None and not (-90 <= body.latitude <= 90):
        raise HTTPException(status_code=422, detail="latitude must be between -90 and 90.")
    if body.longitude is not None and not (-180 <= body.longitude <= 180):
        raise HTTPException(status_code=422, detail="longitude must be between -180 and 180.")
    return _write_manual_capture(
        discovery_id=body.discovery_id,
        manual_extracted_text=body.manual_extracted_text.strip(),
        source_date=body.source_date.strip(),
        notes=body.notes.strip(),
        captured_by=body.captured_by or "analyst",
        latitude=body.latitude,
        longitude=body.longitude,
        coordinate_source=body.coordinate_source.strip(),
        coordinate_confidence=body.coordinate_confidence.strip(),
    )
