from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovered_source import DiscoveredSourceClaim, DiscoveredSourceRecord


EXTRACTOR_NAME = "discovered_source_rule_based"
EXTRACTOR_VERSION = "0.1"
VALID_DISCOVERED_SOURCE_CLAIM_STATUSES = {"extracted", "rejected", "promoted"}
SUPPORTED_CLAIM_TYPES = {
    "possible_project_name",
    "developer",
    "location",
    "city",
    "county",
    "state",
    "utility",
    "load_mw",
    "case_number",
    "document_type",
    "online_date",
    "investment_amount",
    "jobs",
    "general_relevance",
}
RELEVANCE_TERMS = (
    "data center",
    "large load",
    "electric service agreement",
    "transmission interconnection",
)
CASE_NUMBER_RE = re.compile(r"\b(?:Case\s+(?:No\.?|Number)\s*)?((?:PUR|PUC)-\d{4}-\d{5})\b", re.IGNORECASE)
MW_RE = re.compile(r"\b(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?:MW|megawatts?)\b", re.IGNORECASE)
LABELED_PROJECT_RE = re.compile(
    r"\b(?:project|case title|application)\s*:\s*([^.;\n]{8,160}?(?:data center|large load)[^.;\n]{0,120})",
    re.IGNORECASE,
)
DEVELOPER_RE = re.compile(r"\b(?:developer|applicant|customer)\s*:\s*([^.;\n]{3,120})", re.IGNORECASE)


@dataclass
class ExtractedDiscoveredSourceClaim:
    discovered_source_id: uuid.UUID
    source_url: str
    claim_type: str
    claim_value: str
    claim_unit: str | None
    evidence_excerpt: str | None
    confidence: float
    extractor_name: str = EXTRACTOR_NAME
    extractor_version: str = EXTRACTOR_VERSION
    status: str = "extracted"
    raw_metadata_json: dict[str, Any] = field(default_factory=dict)

    @property
    def claim_fingerprint(self) -> str:
        payload = {
            "discovered_source_id": str(self.discovered_source_id),
            "claim_type": self.claim_type,
            "claim_value": self.claim_value,
            "claim_unit": self.claim_unit,
            "extractor_name": self.extractor_name,
            "extractor_version": self.extractor_version,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        return digest


@dataclass
class ClaimExtractionSummary:
    sources_checked: int = 0
    claims_created: int = 0
    claims_updated: int = 0
    claims_skipped: int = 0
    validation_errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def source_text(source: DiscoveredSourceRecord) -> str:
    parts = [
        source.source_title,
        source.snippet,
        source.search_term,
        source.publisher,
        source.geography,
    ]
    raw = source.raw_metadata_json if isinstance(source.raw_metadata_json, dict) else {}
    for key in ("content", "description", "Description_t", "LongName_txt_en", "MetaDescription_txt_en"):
        value = raw.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value:
            parts.append(str(value))
    return " ".join(part for part in parts if part)


def excerpt_around(text: str, needle: str, *, radius: int = 160) -> str:
    lowered = text.lower()
    index = lowered.find(needle.lower())
    if index < 0:
        return text[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(text), index + len(needle) + radius)
    return text[start:end].strip()


def first_labeled_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    value = " ".join(match.group(1).split()).strip(" -:")
    return value or None


class DiscoveredSourceClaimExtractor:
    def extract(self, source: DiscoveredSourceRecord) -> list[ExtractedDiscoveredSourceClaim]:
        text = source_text(source)
        claims: list[ExtractedDiscoveredSourceClaim] = []
        seen: set[tuple[str, str, str | None]] = set()

        def add(
            claim_type: str,
            claim_value: str,
            *,
            claim_unit: str | None = None,
            evidence_excerpt: str | None = None,
            confidence: float,
            raw_metadata_json: dict[str, Any] | None = None,
        ) -> None:
            normalized_value = " ".join(str(claim_value).split()).strip()
            if not normalized_value:
                return
            key = (claim_type, normalized_value, claim_unit)
            if key in seen:
                return
            seen.add(key)
            claims.append(
                ExtractedDiscoveredSourceClaim(
                    discovered_source_id=source.id,
                    source_url=source.source_url,
                    claim_type=claim_type,
                    claim_value=normalized_value,
                    claim_unit=claim_unit,
                    evidence_excerpt=evidence_excerpt,
                    confidence=confidence,
                    raw_metadata_json=raw_metadata_json or {},
                )
            )

        if source.case_number:
            add(
                "case_number",
                source.case_number,
                evidence_excerpt=excerpt_around(text, source.case_number),
                confidence=0.95,
                raw_metadata_json={"source_field": "case_number"},
            )
        for match in CASE_NUMBER_RE.finditer(text):
            add(
                "case_number",
                match.group(1).upper(),
                evidence_excerpt=excerpt_around(text, match.group(1)),
                confidence=0.9,
            )

        if source.document_type:
            add(
                "document_type",
                source.document_type,
                evidence_excerpt=source.source_title or source.snippet,
                confidence=0.9,
                raw_metadata_json={"source_field": "document_type"},
            )

        if self._is_virginia_scc(source):
            add(
                "state",
                "Virginia",
                evidence_excerpt=source.publisher or source.geography or source.source_url,
                confidence=0.85,
                raw_metadata_json={"basis": "Virginia SCC publisher/geography"},
            )

        for term in RELEVANCE_TERMS:
            if term in text.lower():
                add(
                    "general_relevance",
                    term,
                    evidence_excerpt=excerpt_around(text, term),
                    confidence=0.7,
                )

        for match in MW_RE.finditer(text):
            value = match.group(1).replace(",", "")
            try:
                numeric_value = float(value)
            except ValueError:
                continue
            if numeric_value <= 0:
                continue
            add(
                "load_mw",
                str(numeric_value).rstrip("0").rstrip("."),
                claim_unit="MW",
                evidence_excerpt=excerpt_around(text, match.group(0)),
                confidence=0.65,
            )

        project_name = first_labeled_match(LABELED_PROJECT_RE, text)
        if project_name:
            add(
                "possible_project_name",
                project_name,
                evidence_excerpt=excerpt_around(text, project_name),
                confidence=0.45,
                raw_metadata_json={"basis": "explicit labeled project/case phrase"},
            )

        developer = first_labeled_match(DEVELOPER_RE, text)
        if developer:
            add(
                "developer",
                developer,
                evidence_excerpt=excerpt_around(text, developer),
                confidence=0.55,
                raw_metadata_json={"basis": "explicit labeled developer/applicant/customer phrase"},
            )

        return claims

    def _is_virginia_scc(self, source: DiscoveredSourceRecord) -> bool:
        publisher = (source.publisher or "").lower()
        geography = (source.geography or "").lower()
        url = (source.source_url or "").lower()
        return "virginia state corporation commission" in publisher or geography == "virginia" or "scc.virginia.gov" in url


class DiscoveredSourceClaimService:
    def __init__(self, db: Session, *, extractor: DiscoveredSourceClaimExtractor | None = None):
        self.db = db
        self.extractor = extractor or DiscoveredSourceClaimExtractor()

    def extract_claims(
        self,
        *,
        source_id: uuid.UUID | None = None,
        limit: int | None = None,
        dry_run: bool = False,
    ) -> ClaimExtractionSummary:
        query = select(DiscoveredSourceRecord).order_by(DiscoveredSourceRecord.created_at.asc())
        if source_id is not None:
            query = query.where(DiscoveredSourceRecord.id == source_id)
        if limit is not None:
            query = query.limit(max(0, limit))
        sources = list(self.db.scalars(query))
        summary = ClaimExtractionSummary(sources_checked=len(sources))
        for source in sources:
            extracted = self.extractor.extract(source)
            if not extracted:
                summary.warnings.append(f"no_claims_extracted:{source.id}")
                continue
            for claim in extracted:
                error = validate_claim(claim)
                if error:
                    summary.validation_errors.append({"source_url": source.source_url, "message": error})
                    continue
                existing = self.get_by_fingerprint(claim.claim_fingerprint)
                if dry_run:
                    if existing is None:
                        summary.claims_created += 1
                    else:
                        summary.claims_skipped += 1
                    continue
                if existing is None:
                    self.db.add(record_from_claim(claim))
                    summary.claims_created += 1
                else:
                    update_claim_record(existing, claim)
                    summary.claims_updated += 1
        if not dry_run:
            self.db.flush()
        return summary

    def get_by_fingerprint(self, fingerprint: str) -> DiscoveredSourceClaim | None:
        return self.db.scalar(
            select(DiscoveredSourceClaim).where(DiscoveredSourceClaim.claim_fingerprint == fingerprint)
        )

    def list_claims(
        self,
        *,
        status: str | None = None,
        claim_type: str | None = None,
        discovered_source_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[DiscoveredSourceClaim]:
        query = select(DiscoveredSourceClaim).order_by(DiscoveredSourceClaim.created_at.desc())
        if status:
            query = query.where(DiscoveredSourceClaim.status == status)
        if claim_type:
            query = query.where(DiscoveredSourceClaim.claim_type == claim_type)
        if discovered_source_id:
            query = query.where(DiscoveredSourceClaim.discovered_source_id == discovered_source_id)
        return list(self.db.scalars(query.limit(max(1, min(limit, 500)))))


def validate_claim(claim: ExtractedDiscoveredSourceClaim) -> str | None:
    if claim.claim_type not in SUPPORTED_CLAIM_TYPES:
        return f"unsupported claim_type: {claim.claim_type}"
    if claim.status not in VALID_DISCOVERED_SOURCE_CLAIM_STATUSES:
        return f"unsupported status: {claim.status}"
    if not 0 <= claim.confidence <= 1:
        return f"invalid confidence: {claim.confidence}"
    if not claim.claim_value:
        return "claim_value is required"
    return None


def record_from_claim(claim: ExtractedDiscoveredSourceClaim) -> DiscoveredSourceClaim:
    return DiscoveredSourceClaim(
        discovered_source_id=claim.discovered_source_id,
        source_url=claim.source_url,
        claim_type=claim.claim_type,
        claim_value=claim.claim_value,
        claim_unit=claim.claim_unit,
        evidence_excerpt=claim.evidence_excerpt,
        confidence=claim.confidence,
        extractor_name=claim.extractor_name,
        extractor_version=claim.extractor_version,
        status=claim.status,
        raw_metadata_json=claim.raw_metadata_json,
        claim_fingerprint=claim.claim_fingerprint,
    )


def update_claim_record(record: DiscoveredSourceClaim, claim: ExtractedDiscoveredSourceClaim) -> None:
    record.source_url = claim.source_url
    record.evidence_excerpt = claim.evidence_excerpt
    record.confidence = claim.confidence
    record.raw_metadata_json = {**(record.raw_metadata_json or {}), **claim.raw_metadata_json}
