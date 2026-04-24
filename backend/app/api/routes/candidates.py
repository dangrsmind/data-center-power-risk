from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.candidates import CandidateImportResponse
from app.services.candidate_import_service import CandidateImportService


router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.post(
    "/import",
    response_model=CandidateImportResponse,
    response_model_exclude_none=True,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "oneOf": [
                            {
                                "type": "object",
                                "properties": {
                                    "candidate_id": {"type": "string"},
                                    "canonical_name": {"type": "string"},
                                    "developer": {"type": "string", "nullable": True},
                                    "operator": {"type": "string", "nullable": True},
                                    "state": {"type": "string"},
                                    "county": {"type": "string", "nullable": True},
                                    "region_hint": {"type": "string", "nullable": True},
                                    "utility_hint": {"type": "string", "nullable": True},
                                    "known_load_mw": {"type": "number", "nullable": True},
                                    "load_note": {"type": "string", "nullable": True},
                                    "priority_tier": {"type": "string", "nullable": True},
                                    "sources": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "url": {"type": "string"},
                                                "source_type": {"type": "string"},
                                            },
                                            "required": ["url", "source_type"],
                                        },
                                    },
                                    "notes": {"type": "string", "nullable": True},
                                },
                                "required": ["canonical_name", "state"],
                            },
                            {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "candidate_id": {"type": "string"},
                                        "canonical_name": {"type": "string"},
                                        "developer": {"type": "string", "nullable": True},
                                        "operator": {"type": "string", "nullable": True},
                                        "state": {"type": "string"},
                                        "county": {"type": "string", "nullable": True},
                                        "region_hint": {"type": "string", "nullable": True},
                                        "utility_hint": {"type": "string", "nullable": True},
                                        "known_load_mw": {"type": "number", "nullable": True},
                                        "load_note": {"type": "string", "nullable": True},
                                        "priority_tier": {"type": "string", "nullable": True},
                                        "sources": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "url": {"type": "string"},
                                                    "source_type": {"type": "string"},
                                                },
                                                "required": ["url", "source_type"],
                                            },
                                        },
                                        "notes": {"type": "string", "nullable": True},
                                    },
                                    "required": ["canonical_name", "state"],
                                },
                            },
                        ]
                    },
                    "examples": {
                        "single_candidate": {
                            "summary": "Single candidate JSON object",
                            "value": {
                                "candidate_id": "CAND_001",
                                "canonical_name": "CleanArc VA1",
                                "developer": "CleanArc Data Centers",
                                "state": "VA",
                                "county": "Caroline",
                                "region_hint": "PJM",
                                "utility_hint": "Rappahannock Electric Cooperative",
                                "known_load_mw": 300,
                                "load_note": "First tranche",
                                "priority_tier": "A",
                                "sources": [
                                    {
                                        "url": "https://example.com/source-1",
                                        "source_type": "developer_statement",
                                    }
                                ],
                                "notes": "Initial shortlist import",
                            },
                        },
                        "candidate_array": {
                            "summary": "Array of candidate JSON objects",
                            "value": [
                                {
                                    "candidate_id": "CAND_001",
                                    "canonical_name": "CleanArc VA1",
                                    "developer": "CleanArc Data Centers",
                                    "state": "VA",
                                    "county": "Caroline",
                                    "region_hint": "PJM",
                                    "utility_hint": "Rappahannock Electric Cooperative",
                                    "known_load_mw": 300,
                                    "priority_tier": "A",
                                    "sources": [
                                        {
                                            "url": "https://example.com/source-1",
                                            "source_type": "developer_statement",
                                        }
                                    ],
                                }
                            ],
                        },
                    },
                },
                "text/csv": {
                    "schema": {"type": "string"},
                    "example": (
                        "candidate_id,canonical_name,developer,state,county,region_hint,utility_hint,known_load_mw,"
                        "priority_tier,source_1_url,source_1_type,notes\n"
                        "CAND_001,CleanArc VA1,CleanArc Data Centers,VA,Caroline,PJM,"
                        "Rappahannock Electric Cooperative,300,A,https://example.com/source-1,"
                        "developer_statement,Initial shortlist import"
                    ),
                },
            },
        }
    },
)
async def import_candidates(request: Request, db: Session = Depends(get_db)) -> CandidateImportResponse:
    payload = await request.body()
    content_type = request.headers.get("content-type")
    return CandidateImportService(db).import_payload(payload, content_type)
