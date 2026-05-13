from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovered_source import DiscoveredSourceRecord


VALID_DISCOVERED_SOURCE_STATUSES = {"discovered", "candidate", "rejected", "promoted"}
KNOWN_DISCOVERED_SOURCE_FIELDS = {
    "source_url",
    "source_title",
    "source_type",
    "publisher",
    "geography",
    "discovery_method",
    "discovered_at",
    "confidence",
    "search_term",
    "source_query",
    "snippet",
    "case_number",
    "document_type",
    "source_registry_id",
    "adapter_id",
    "discovery_run_id",
    "raw_metadata_json",
    "status",
}


@dataclass
class ValidatedDiscoveredSource:
    source_url: str
    source_title: str | None
    source_type: str | None
    publisher: str | None
    geography: str | None
    discovery_method: str | None
    discovered_at: datetime | None
    confidence: str | None
    search_term: str | None
    snippet: str | None
    case_number: str | None
    document_type: str | None
    source_registry_id: str | None
    adapter_id: str | None
    discovery_run_id: str | None
    raw_metadata_json: dict[str, Any]
    status: str = "discovered"


@dataclass
class DiscoveredSourceValidationError:
    row_number: int
    source_url: str | None
    message: str


@dataclass
class DiscoveredSourceIngestSummary:
    rows_read: int = 0
    sources_created: int = 0
    sources_updated: int = 0
    rows_skipped: int = 0
    validation_errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def validate_http_url(value: Any) -> str:
    text = clean_string(value)
    if text is None:
        raise ValueError("source_url is required")
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source_url must be an absolute http/https URL")
    return text


def parse_datetime(value: Any) -> datetime | None:
    text = clean_string(value)
    if text is None:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("discovered_at must be an ISO datetime") from exc


def validate_confidence(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("confidence must not be boolean")
    if isinstance(value, int | float):
        numeric = float(value)
        if not 0 <= numeric <= 1:
            raise ValueError("confidence must be between 0 and 1")
        return str(value)
    text = clean_string(value)
    if text is None:
        return None
    try:
        numeric = float(text)
    except ValueError:
        return text
    if not 0 <= numeric <= 1:
        raise ValueError("confidence must be between 0 and 1")
    return text


def validate_status(value: Any) -> str:
    status = clean_string(value) or "discovered"
    if status not in VALID_DISCOVERED_SOURCE_STATUSES:
        allowed = ", ".join(sorted(VALID_DISCOVERED_SOURCE_STATUSES))
        raise ValueError(f"status must be one of: {allowed}")
    return status


def validate_discovered_source_row(
    raw: dict[str, Any],
    *,
    row_number: int,
    discovery_run_id: str | None = None,
    adapter_id: str | None = None,
    source_registry_id: str | None = None,
) -> ValidatedDiscoveredSource:
    if not isinstance(raw, dict):
        raise ValueError("row must be a JSON object")
    source_url = validate_http_url(raw.get("source_url"))
    discovered_at = parse_datetime(raw.get("discovered_at"))
    unknown_fields = {key: value for key, value in raw.items() if key not in KNOWN_DISCOVERED_SOURCE_FIELDS}
    existing_raw_metadata = raw.get("raw_metadata_json") if isinstance(raw.get("raw_metadata_json"), dict) else {}
    raw_metadata = {
        **existing_raw_metadata,
        **unknown_fields,
        "original_row_number": row_number,
    }
    return ValidatedDiscoveredSource(
        source_url=source_url,
        source_title=clean_string(raw.get("source_title")),
        source_type=clean_string(raw.get("source_type")),
        publisher=clean_string(raw.get("publisher")),
        geography=clean_string(raw.get("geography")),
        discovery_method=clean_string(raw.get("discovery_method")),
        discovered_at=discovered_at,
        confidence=validate_confidence(raw.get("confidence")),
        search_term=clean_string(raw.get("search_term")) or clean_string(raw.get("source_query")),
        snippet=clean_string(raw.get("snippet")),
        case_number=clean_string(raw.get("case_number")),
        document_type=clean_string(raw.get("document_type")),
        source_registry_id=clean_string(raw.get("source_registry_id")) or source_registry_id,
        adapter_id=clean_string(raw.get("adapter_id")) or adapter_id,
        discovery_run_id=clean_string(raw.get("discovery_run_id")) or discovery_run_id,
        raw_metadata_json=raw_metadata,
        status=validate_status(raw.get("status")),
    )


class DiscoveredSourceService:
    def __init__(self, db: Session):
        self.db = db

    def ingest_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        dry_run: bool = False,
        allow_existing: bool = False,
        discovery_run_id: str | None = None,
        adapter_id: str | None = None,
        source_registry_id: str | None = None,
    ) -> DiscoveredSourceIngestSummary:
        summary = DiscoveredSourceIngestSummary(rows_read=len(rows))
        for index, raw in enumerate(rows, start=1):
            try:
                validated = validate_discovered_source_row(
                    raw,
                    row_number=index,
                    discovery_run_id=discovery_run_id,
                    adapter_id=adapter_id,
                    source_registry_id=source_registry_id,
                )
            except ValueError as exc:
                summary.rows_skipped += 1
                summary.validation_errors.append(
                    asdict(
                        DiscoveredSourceValidationError(
                            row_number=index,
                            source_url=raw.get("source_url") if isinstance(raw, dict) else None,
                            message=str(exc),
                        )
                    )
                )
                continue

            if dry_run:
                summary.sources_created += 1
                continue
            existing = self.get_by_url(validated.source_url)
            if existing is not None and not allow_existing:
                summary.rows_skipped += 1
                continue
            if existing is None:
                summary.sources_created += 1
                self.db.add(self._record_from_validated(validated))
                continue
            summary.sources_updated += 1
            self._update_record(existing, validated)

        if not dry_run:
            self.db.flush()
        return summary

    def get_by_url(self, source_url: str) -> DiscoveredSourceRecord | None:
        return self.db.scalar(select(DiscoveredSourceRecord).where(DiscoveredSourceRecord.source_url == source_url))

    def list_sources(
        self,
        *,
        status: str | None = None,
        source_type: str | None = None,
        publisher: str | None = None,
        limit: int = 100,
    ) -> list[DiscoveredSourceRecord]:
        query = select(DiscoveredSourceRecord).order_by(DiscoveredSourceRecord.created_at.desc())
        if status:
            query = query.where(DiscoveredSourceRecord.status == status)
        if source_type:
            query = query.where(DiscoveredSourceRecord.source_type == source_type)
        if publisher:
            query = query.where(DiscoveredSourceRecord.publisher == publisher)
        return list(self.db.scalars(query.limit(max(1, min(limit, 500)))))

    def _record_from_validated(self, source: ValidatedDiscoveredSource) -> DiscoveredSourceRecord:
        return DiscoveredSourceRecord(**asdict(source))

    def _update_record(self, record: DiscoveredSourceRecord, source: ValidatedDiscoveredSource) -> None:
        for field_name, value in asdict(source).items():
            if field_name == "raw_metadata_json":
                record.raw_metadata_json = {**(record.raw_metadata_json or {}), **source.raw_metadata_json}
            elif value is not None:
                setattr(record, field_name, value)
