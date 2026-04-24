from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from io import StringIO

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.enums import LifecycleState
from app.models.project import Project
from app.repositories.candidate_repo import CandidateRepository
from app.schemas.candidates import CandidateImportItemResult, CandidateImportResponse


@dataclass
class CandidateRow:
    row_number: int
    canonical_name: str | None
    developer: str | None
    operator: str | None
    state: str | None
    county: str | None
    metadata: dict
    warnings: list[str]


class CandidateImportService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = CandidateRepository(db)

    def import_payload(self, payload: bytes, content_type: str | None) -> CandidateImportResponse:
        rows = self._parse_payload(payload, content_type)
        created: list[CandidateImportItemResult] = []
        updated: list[CandidateImportItemResult] = []
        skipped: list[CandidateImportItemResult] = []
        rejected: list[CandidateImportItemResult] = []

        for row in rows:
            if not row.canonical_name or not row.state:
                rejected.append(
                    CandidateImportItemResult(
                        row_number=row.row_number,
                        canonical_name=row.canonical_name,
                        status="rejected",
                        message="canonical_name and state are required",
                        warnings=row.warnings,
                    )
                )
                continue

            existing = self.repo.get_by_canonical_name(row.canonical_name)
            if existing is None:
                project = self.repo.create_project(
                    Project(
                        canonical_name=row.canonical_name,
                        developer=row.developer,
                        operator=row.operator,
                        state=row.state,
                        county=row.county,
                        lifecycle_state=LifecycleState.NAMED_VERIFIED,
                        candidate_metadata_json=row.metadata or None,
                    )
                )
                created.append(
                    CandidateImportItemResult(
                        row_number=row.row_number,
                        canonical_name=project.canonical_name,
                        project_id=project.id,
                        status="created",
                        message="Project created",
                        warnings=row.warnings,
                    )
                )
                continue

            changed = False
            if row.developer and existing.developer != row.developer:
                existing.developer = row.developer
                changed = True
            if row.operator and existing.operator != row.operator:
                existing.operator = row.operator
                changed = True
            if row.state and existing.state != row.state:
                existing.state = row.state
                changed = True
            if row.county and existing.county != row.county:
                existing.county = row.county
                changed = True

            merged_metadata = self._merge_metadata(existing.candidate_metadata_json, row.metadata)
            if merged_metadata != (existing.candidate_metadata_json or None):
                existing.candidate_metadata_json = merged_metadata
                changed = True

            bucket = updated if changed else skipped
            bucket.append(
                CandidateImportItemResult(
                    row_number=row.row_number,
                    canonical_name=existing.canonical_name,
                    project_id=existing.id,
                    status="updated" if changed else "skipped",
                    message="Project updated" if changed else "Project already exists with no safe changes",
                    warnings=row.warnings,
                )
            )

        self.db.commit()
        return CandidateImportResponse(
            created=created,
            updated=updated,
            skipped=skipped,
            rejected=rejected,
        )

    def _parse_payload(self, payload: bytes, content_type: str | None) -> list[CandidateRow]:
        text = payload.decode("utf-8").strip()
        if not text:
            raise HTTPException(status_code=400, detail="Empty import payload")

        normalized_content_type = (content_type or "").split(";")[0].strip().lower()
        if normalized_content_type == "application/json":
            return self._parse_json(text)
        if normalized_content_type in {"text/csv", "application/csv", "text/plain"}:
            return self._parse_csv(text)

        if text.startswith("[") or text.startswith("{"):
            return self._parse_json(text)
        return self._parse_csv(text)

    def _parse_json(self, text: str) -> list[CandidateRow]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc.msg}") from exc

        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise HTTPException(status_code=400, detail="JSON import payload must be an object or array of objects")

        rows: list[CandidateRow] = []
        for index, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                raise HTTPException(status_code=400, detail="Each JSON candidate row must be an object")
            warnings: list[str] = []
            sources = item.get("sources")
            if sources is not None and not isinstance(sources, list):
                warnings.append("sources ignored because it is not a list")
                sources = []
            rows.append(
                CandidateRow(
                    row_number=index,
                    canonical_name=self._clean_string(item.get("canonical_name")),
                    developer=self._clean_string(item.get("developer")),
                    operator=self._clean_string(item.get("operator")),
                    state=self._normalize_state(item.get("state")),
                    county=self._clean_string(item.get("county")),
                    metadata={
                        "candidate_id": self._clean_string(item.get("candidate_id")),
                        "region_hint": self._clean_string(item.get("region_hint")),
                        "utility_hint": self._clean_string(item.get("utility_hint")),
                        "known_load_mw": item.get("known_load_mw"),
                        "load_note": self._clean_string(item.get("load_note")),
                        "priority_tier": self._clean_string(item.get("priority_tier")),
                        "sources": sources or [],
                        "notes": self._clean_string(item.get("notes")),
                    },
                    warnings=warnings,
                )
            )
        return rows

    def _parse_csv(self, text: str) -> list[CandidateRow]:
        reader = csv.DictReader(StringIO(text))
        if not reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV import payload is missing a header row")

        rows: list[CandidateRow] = []
        for index, item in enumerate(reader, start=2):
            warnings: list[str] = []
            sources: list[dict[str, str]] = []
            for source_index in range(1, 6):
                url = self._clean_string(item.get(f"source_{source_index}_url"))
                source_type = self._clean_string(item.get(f"source_{source_index}_type"))
                if url and source_type:
                    sources.append({"url": url, "source_type": source_type})
                elif url or source_type:
                    warnings.append(f"source_{source_index} ignored because url/type pair is incomplete")

            rows.append(
                CandidateRow(
                    row_number=index,
                    canonical_name=self._clean_string(item.get("canonical_name")),
                    developer=self._clean_string(item.get("developer")),
                    operator=self._clean_string(item.get("operator")),
                    state=self._normalize_state(item.get("state")),
                    county=self._clean_string(item.get("county")),
                    metadata={
                        "candidate_id": self._clean_string(item.get("candidate_id")),
                        "region_hint": self._clean_string(item.get("region_hint")),
                        "utility_hint": self._clean_string(item.get("utility_hint")),
                        "known_load_mw": self._parse_number(item.get("known_load_mw"), warnings, "known_load_mw"),
                        "load_note": self._clean_string(item.get("load_note")),
                        "priority_tier": self._clean_string(item.get("priority_tier")),
                        "sources": sources,
                        "notes": self._clean_string(item.get("notes")),
                    },
                    warnings=warnings,
                )
            )
        return rows

    def _clean_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _normalize_state(self, value: object) -> str | None:
        text = self._clean_string(value)
        if text is None:
            return None
        return text.upper()

    def _parse_number(self, value: object, warnings: list[str], field_name: str) -> float | None:
        text = self._clean_string(value)
        if text is None:
            return None
        try:
            return float(text)
        except ValueError:
            warnings.append(f"{field_name} ignored because it is not numeric")
            return None

    def _merge_metadata(self, existing: dict | list | None, incoming: dict) -> dict | None:
        base = existing.copy() if isinstance(existing, dict) else {}
        merged = {**base}
        for key, value in incoming.items():
            if value is None or value == []:
                continue
            merged[key] = value
        return merged or None
