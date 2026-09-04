from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.discovered_source import DiscoveredSourceRecord


VALID_DISCOVERED_SOURCE_STATUSES = {"discovered", "candidate", "rejected", "promoted"}
VALID_DISCOVERED_SOURCE_REVIEW_STATUSES = {"unreviewed", "useful", "maybe", "noisy", "weak", "rejected"}
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

WEAK_SOURCE_URL_QUALITIES = {"public_comment_form", "fallback_reference"}


@dataclass(frozen=True)
class DiscoveredSourceReviewFilters:
    discovery_run_id: str | None = None
    source_registry_id: str | None = None
    adapter_id: str | None = None
    source_type: str | None = None
    geography: str | None = None
    status: str | None = None
    publisher: str | None = None
    source_url_quality: str | None = None
    has_weak_url_quality: bool | None = None
    review_status: str | None = None
    reviewed_by: str | None = None
    has_review_notes: bool | None = None
    q: str | None = None

    def applied(self) -> dict[str, Any]:
        values = asdict(self)
        return {key: value for key, value in values.items() if value is not None and value != ""}


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
    dry_run: bool = False
    allow_existing: bool = False
    sources_created: int = 0
    sources_updated: int = 0
    rows_skipped: int = 0
    duplicate_input_urls_skipped: int = 0
    duplicate_existing_urls_skipped: int = 0
    weak_scc_public_comment_form_count: int = 0
    weak_scc_public_comment_form_rows: list[dict[str, Any]] = field(default_factory=list)
    validation_errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["would_create"] = self.sources_created if self.dry_run else 0
        payload["would_skip_existing"] = self.duplicate_existing_urls_skipped if self.dry_run else 0
        payload["would_update_existing"] = self.sources_updated if self.dry_run and self.allow_existing else 0
        payload["structural_error_count"] = len(self.validation_errors)
        return payload


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


def validate_review_status(value: Any) -> str | None:
    review_status = clean_string(value)
    if review_status is None or review_status == "unreviewed":
        return None
    if review_status not in VALID_DISCOVERED_SOURCE_REVIEW_STATUSES:
        allowed = ", ".join(sorted(VALID_DISCOVERED_SOURCE_REVIEW_STATUSES))
        raise ValueError(f"review_status must be one of: {allowed}")
    return review_status


def display_review_status(record: DiscoveredSourceRecord) -> str:
    return clean_string(record.review_status) or "unreviewed"


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
    source_title = clean_string(raw.get("source_title"))
    source_type = clean_string(raw.get("source_type"))
    geography = clean_string(raw.get("geography"))
    discovery_method = clean_string(raw.get("discovery_method"))
    resolved_source_registry_id = clean_string(raw.get("source_registry_id")) or source_registry_id
    resolved_adapter_id = clean_string(raw.get("adapter_id")) or adapter_id
    required_values = {
        "source_title": source_title,
        "source_type": source_type,
        "geography": geography,
        "discovery_method": discovery_method,
        "source_registry_id": resolved_source_registry_id,
        "adapter_id": resolved_adapter_id,
    }
    missing_fields = [field_name for field_name, value in required_values.items() if not value]
    if missing_fields:
        raise ValueError(f"missing required discovered-source field(s): {', '.join(missing_fields)}")
    return ValidatedDiscoveredSource(
        source_url=source_url,
        source_title=source_title,
        source_type=source_type,
        publisher=clean_string(raw.get("publisher")),
        geography=geography,
        discovery_method=discovery_method,
        discovered_at=discovered_at,
        confidence=validate_confidence(raw.get("confidence")),
        search_term=clean_string(raw.get("search_term")) or clean_string(raw.get("source_query")),
        snippet=clean_string(raw.get("snippet")),
        case_number=clean_string(raw.get("case_number")),
        document_type=clean_string(raw.get("document_type")),
        source_registry_id=resolved_source_registry_id,
        adapter_id=resolved_adapter_id,
        discovery_run_id=clean_string(raw.get("discovery_run_id")) or discovery_run_id,
        raw_metadata_json=raw_metadata,
        status=validate_status(raw.get("status")),
    )


def is_weak_scc_public_comment_form(row: dict[str, Any]) -> bool:
    source_url = clean_string(row.get("source_url")) or ""
    source_title = clean_string(row.get("source_title")) or ""
    snippet = clean_string(row.get("snippet")) or ""
    notes = clean_string(row.get("notes")) or ""
    metadata = row.get("raw_metadata_json") if isinstance(row.get("raw_metadata_json"), dict) else {}
    quality = clean_string(metadata.get("source_url_quality")) or ""
    haystack = " ".join([source_url, source_title, snippet, notes]).casefold()
    return (
        quality.casefold() == "public_comment_form"
        or "/case-information/submit-public-comments/cases/" in source_url.casefold()
        or "case comments for" in haystack
    )


def raw_metadata_dict(record: DiscoveredSourceRecord) -> dict[str, Any]:
    return record.raw_metadata_json if isinstance(record.raw_metadata_json, dict) else {}


def source_url_quality(record: DiscoveredSourceRecord) -> str | None:
    return clean_string(raw_metadata_dict(record).get("source_url_quality"))


def url_quality_warning(record: DiscoveredSourceRecord) -> str | None:
    return clean_string(raw_metadata_dict(record).get("url_quality_warning"))


def alternate_urls(record: DiscoveredSourceRecord) -> list[str]:
    value = raw_metadata_dict(record).get("alternate_urls")
    if not isinstance(value, list):
        return []
    return [item for item in (clean_string(item) for item in value) if item]


def has_weak_url_quality(record: DiscoveredSourceRecord) -> bool:
    quality = source_url_quality(record)
    if quality and quality.casefold() in WEAK_SOURCE_URL_QUALITIES:
        return True
    return is_weak_scc_public_comment_form(
        {
            "source_url": record.source_url,
            "source_title": record.source_title,
            "snippet": record.snippet,
            "raw_metadata_json": raw_metadata_dict(record),
        }
    )


def discovered_source_review_payload(
    record: DiscoveredSourceRecord,
    *,
    include_raw_metadata: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": record.id,
        "source_title": record.source_title,
        "source_url": record.source_url,
        "source_type": record.source_type,
        "geography": record.geography,
        "publisher": record.publisher,
        "status": record.status,
        "discovery_run_id": record.discovery_run_id,
        "source_registry_id": record.source_registry_id,
        "adapter_id": record.adapter_id,
        "discovery_method": record.discovery_method,
        "source_query": record.search_term,
        "snippet": record.snippet,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "source_url_quality": source_url_quality(record),
        "url_quality_warning": url_quality_warning(record),
        "alternate_urls": alternate_urls(record),
        "review_status": display_review_status(record),
        "review_notes": record.review_notes,
        "reviewed_at": record.reviewed_at,
        "reviewed_by": record.reviewed_by,
    }
    if include_raw_metadata:
        payload["raw_metadata_json"] = record.raw_metadata_json
    return payload


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
        summary = DiscoveredSourceIngestSummary(rows_read=len(rows), dry_run=dry_run, allow_existing=allow_existing)
        validated_by_url: dict[str, ValidatedDiscoveredSource] = {}
        for index, raw in enumerate(rows, start=1):
            if isinstance(raw, dict) and is_weak_scc_public_comment_form(raw):
                summary.weak_scc_public_comment_form_count += 1
                summary.weak_scc_public_comment_form_rows.append(
                    {
                        "row_number": index,
                        "source_url": raw.get("source_url"),
                        "source_title": raw.get("source_title"),
                    }
                )
                summary.warnings.append(
                    f"weak_scc_public_comment_form_url: row {index} retained as fallback reference"
                )
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

            if validated.source_url in validated_by_url:
                summary.rows_skipped += 1
                summary.duplicate_input_urls_skipped += 1
                summary.warnings.append(
                    f"duplicate_input_source_url_skipped: row {index} duplicates {validated.source_url}"
                )
                continue
            validated_by_url[validated.source_url] = validated

        existing_by_url = self.get_existing_by_url(validated_by_url.keys())
        for validated in validated_by_url.values():
            existing = existing_by_url.get(validated.source_url)
            if existing is not None and not allow_existing:
                summary.rows_skipped += 1
                summary.duplicate_existing_urls_skipped += 1
                continue
            if dry_run:
                if existing is None:
                    summary.sources_created += 1
                else:
                    summary.sources_updated += 1
                continue
            if existing is None:
                if self._insert_record(validated, summary):
                    summary.sources_created += 1
                continue
            summary.sources_updated += 1
            self._update_record(existing, validated)

        if not dry_run:
            self.db.flush()
        return summary

    def get_by_url(self, source_url: str) -> DiscoveredSourceRecord | None:
        return self.db.scalar(select(DiscoveredSourceRecord).where(DiscoveredSourceRecord.source_url == source_url))

    def get_existing_by_url(self, source_urls: Any) -> dict[str, DiscoveredSourceRecord]:
        urls = list(source_urls)
        if not urls:
            return {}
        records = self.db.scalars(select(DiscoveredSourceRecord).where(DiscoveredSourceRecord.source_url.in_(urls)))
        return {record.source_url: record for record in records}

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

    def list_review_sources(
        self,
        *,
        filters: DiscoveredSourceReviewFilters | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DiscoveredSourceRecord], int, dict[str, Any]]:
        filters = filters or DiscoveredSourceReviewFilters()
        records = self._review_filtered_records(filters)
        total = len(records)
        bounded_limit = max(1, min(limit, 200))
        bounded_offset = max(0, offset)
        return records[bounded_offset : bounded_offset + bounded_limit], total, filters.applied()

    def summarize_review_sources(
        self,
        *,
        filters: DiscoveredSourceReviewFilters | None = None,
    ) -> dict[str, Any]:
        filters = filters or DiscoveredSourceReviewFilters()
        records = self._review_filtered_records(filters)
        weak_records = [record for record in records if has_weak_url_quality(record)]
        counts_by_review_status = self._count_by_review_status(records)
        return {
            "total": len(records),
            "counts_by_status": self._count_by(records, "status"),
            "counts_by_source_type": self._count_by(records, "source_type"),
            "counts_by_geography": self._count_by(records, "geography"),
            "counts_by_source_registry_id": self._count_by(records, "source_registry_id"),
            "counts_by_adapter_id": self._count_by(records, "adapter_id"),
            "counts_by_discovery_run_id": self._count_by(records, "discovery_run_id"),
            "counts_by_review_status": counts_by_review_status,
            "reviewed_count": len(records) - counts_by_review_status.get("unreviewed", 0),
            "unreviewed_count": counts_by_review_status.get("unreviewed", 0),
            "noisy_count": counts_by_review_status.get("noisy", 0),
            "weak_count": counts_by_review_status.get("weak", 0),
            "useful_count": counts_by_review_status.get("useful", 0),
            "maybe_count": counts_by_review_status.get("maybe", 0),
            "rejected_count": counts_by_review_status.get("rejected", 0),
            "weak_url_quality_count": len(weak_records),
            "weak_url_quality_examples": [
                discovered_source_review_payload(record) for record in weak_records[:10]
            ],
            "applied_filters": filters.applied(),
        }

    def get_review_source(self, source_id: Any) -> DiscoveredSourceRecord | None:
        return self.db.get(DiscoveredSourceRecord, source_id)

    def update_review(
        self,
        source_id: Any,
        *,
        review_status: Any,
        review_notes: Any = None,
        reviewed_by: Any = None,
    ) -> DiscoveredSourceRecord | None:
        record = self.get_review_source(source_id)
        if record is None:
            return None
        record.review_status = validate_review_status(review_status)
        record.review_notes = clean_string(review_notes)
        record.reviewed_by = clean_string(reviewed_by)
        record.reviewed_at = datetime.now(timezone.utc)
        self.db.flush()
        return record

    def _review_filtered_records(self, filters: DiscoveredSourceReviewFilters) -> list[DiscoveredSourceRecord]:
        query = select(DiscoveredSourceRecord).order_by(
            DiscoveredSourceRecord.created_at.desc(),
            DiscoveredSourceRecord.id.desc(),
        )
        exact_filters = {
            "discovery_run_id": filters.discovery_run_id,
            "source_registry_id": filters.source_registry_id,
            "adapter_id": filters.adapter_id,
            "source_type": filters.source_type,
            "geography": filters.geography,
            "status": filters.status,
            "publisher": filters.publisher,
            "reviewed_by": filters.reviewed_by,
        }
        for field_name, value in exact_filters.items():
            text = clean_string(value)
            if text:
                query = query.where(getattr(DiscoveredSourceRecord, field_name) == text)
        search_text = clean_string(filters.q)
        if search_text:
            like_pattern = f"%{search_text.casefold()}%"
            query = query.where(
                or_(
                    func.lower(DiscoveredSourceRecord.source_title).like(like_pattern),
                    func.lower(DiscoveredSourceRecord.source_url).like(like_pattern),
                    func.lower(DiscoveredSourceRecord.snippet).like(like_pattern),
                    func.lower(DiscoveredSourceRecord.search_term).like(like_pattern),
                )
            )
        records = list(self.db.scalars(query))
        review_status = clean_string(filters.review_status)
        if review_status:
            if review_status not in VALID_DISCOVERED_SOURCE_REVIEW_STATUSES:
                raise ValueError("invalid review_status")
            records = [
                record for record in records
                if display_review_status(record) == review_status
            ]
        if filters.has_review_notes is not None:
            records = [
                record for record in records
                if (clean_string(record.review_notes) is not None) == filters.has_review_notes
            ]
        quality = clean_string(filters.source_url_quality)
        if quality:
            records = [
                record for record in records
                if (source_url_quality(record) or "").casefold() == quality.casefold()
            ]
        if filters.has_weak_url_quality is not None:
            records = [
                record for record in records
                if has_weak_url_quality(record) == filters.has_weak_url_quality
            ]
        return records

    @staticmethod
    def _count_by(records: list[DiscoveredSourceRecord], field_name: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in records:
            key = clean_string(getattr(record, field_name)) or "unknown"
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    @staticmethod
    def _count_by_review_status(records: list[DiscoveredSourceRecord]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in records:
            key = display_review_status(record)
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    def _record_from_validated(self, source: ValidatedDiscoveredSource) -> DiscoveredSourceRecord:
        return DiscoveredSourceRecord(**asdict(source))

    def _insert_record(
        self,
        source: ValidatedDiscoveredSource,
        summary: DiscoveredSourceIngestSummary,
    ) -> bool:
        try:
            with self.db.begin_nested():
                self.db.add(self._record_from_validated(source))
                self.db.flush()
        except IntegrityError:
            summary.rows_skipped += 1
            summary.duplicate_existing_urls_skipped += 1
            summary.warnings.append(f"duplicate_source_url_integrity_fallback_skipped: {source.source_url}")
            return False
        return True

    def _update_record(self, record: DiscoveredSourceRecord, source: ValidatedDiscoveredSource) -> None:
        for field_name, value in asdict(source).items():
            if field_name == "raw_metadata_json":
                record.raw_metadata_json = {**(record.raw_metadata_json or {}), **source.raw_metadata_json}
            elif field_name not in {"source_url", "status"} and value is not None:
                setattr(record, field_name, value)
