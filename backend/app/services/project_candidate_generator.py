from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovered_source import DiscoveredSourceClaim, DiscoveredSourceRecord
from app.models.project_candidate import ProjectCandidate


VALID_PROJECT_CANDIDATE_STATUSES = {"candidate", "needs_review", "rejected", "promoted"}
FIELD_CLAIM_TYPES = {"possible_project_name", "developer", "state", "county", "city", "utility", "load_mw"}


@dataclass
class CandidateDraft:
    candidate_key: str
    candidate_name: str
    developer: str | None
    state: str | None
    county: str | None
    city: str | None
    utility: str | None
    load_mw: float | None
    lifecycle_state: str | None
    confidence: float
    status: str
    source_count: int
    claim_count: int
    primary_source_url: str | None
    discovered_source_ids_json: list[str]
    discovered_source_claim_ids_json: list[str]
    evidence_excerpt: str | None
    raw_metadata_json: dict[str, Any]


@dataclass
class ProjectCandidateGenerationSummary:
    claims_checked: int = 0
    sources_grouped: int = 0
    candidates_created: int = 0
    candidates_updated: int = 0
    candidates_skipped: int = 0
    validation_errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    return text or None


def choose_claim_value(claims: list[DiscoveredSourceClaim], claim_type: str) -> str | None:
    typed = [claim for claim in claims if claim.claim_type == claim_type and claim.claim_value]
    if not typed:
        return None
    typed.sort(key=lambda claim: (claim.confidence, len(claim.claim_value)), reverse=True)
    return canonical_text(typed[0].claim_value)


def choose_excerpt(claims: list[DiscoveredSourceClaim]) -> str | None:
    for claim_type in ("possible_project_name", "load_mw", "case_number", "general_relevance"):
        for claim in claims:
            if claim.claim_type == claim_type and claim.evidence_excerpt:
                return claim.evidence_excerpt[:1000]
    for claim in claims:
        if claim.evidence_excerpt:
            return claim.evidence_excerpt[:1000]
    return None


def parse_load_mw(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def candidate_group_key(source: DiscoveredSourceRecord, claims: list[DiscoveredSourceClaim]) -> str:
    case_number = choose_claim_value(claims, "case_number")
    if case_number:
        return f"case:{case_number.lower()}"
    candidate_name = choose_claim_value(claims, "possible_project_name")
    if candidate_name:
        return "name:" + hashlib.sha256(candidate_name.lower().encode("utf-8")).hexdigest()[:24]
    return f"source:{source.id}"


def candidate_key_for_group(group_key: str) -> str:
    return hashlib.sha256(group_key.encode("utf-8")).hexdigest()


def confidence_for_group(claims: list[DiscoveredSourceClaim], source_count: int, has_name: bool) -> float:
    if not claims:
        return 0.0
    avg_confidence = sum(claim.confidence for claim in claims) / len(claims)
    specificity = 0.0
    if has_name:
        specificity += 0.15
    if any(claim.claim_type == "load_mw" for claim in claims):
        specificity += 0.08
    if any(claim.claim_type == "state" for claim in claims):
        specificity += 0.05
    if any(claim.claim_type == "case_number" for claim in claims):
        specificity += 0.05
    source_bonus = min(0.08, max(0, source_count - 1) * 0.03)
    unresolved_penalty = 0 if has_name else 0.2
    return max(0.0, min(1.0, round(avg_confidence + specificity + source_bonus - unresolved_penalty, 3)))


def build_candidate_draft(
    group_key: str,
    sources: list[DiscoveredSourceRecord],
    claims: list[DiscoveredSourceClaim],
) -> CandidateDraft:
    source_ids = sorted({str(source.id) for source in sources})
    claim_ids = sorted({str(claim.id) for claim in claims})
    name = choose_claim_value(claims, "possible_project_name")
    if not name:
        state_hint = choose_claim_value(claims, "state") or sources[0].geography or "Unknown"
        name = f"Unresolved {state_hint} SCC candidate {str(sources[0].id)[:8]}"
    load_mw = parse_load_mw(choose_claim_value(claims, "load_mw"))
    confidence = confidence_for_group(claims, len(source_ids), has_name=not name.startswith("Unresolved "))
    return CandidateDraft(
        candidate_key=candidate_key_for_group(group_key),
        candidate_name=name[:255],
        developer=choose_claim_value(claims, "developer"),
        state=choose_claim_value(claims, "state"),
        county=choose_claim_value(claims, "county"),
        city=choose_claim_value(claims, "city"),
        utility=choose_claim_value(claims, "utility"),
        load_mw=load_mw,
        lifecycle_state="candidate_unverified",
        confidence=confidence,
        status="candidate" if choose_claim_value(claims, "possible_project_name") else "needs_review",
        source_count=len(source_ids),
        claim_count=len(claim_ids),
        primary_source_url=sources[0].source_url,
        discovered_source_ids_json=source_ids,
        discovered_source_claim_ids_json=claim_ids,
        evidence_excerpt=choose_excerpt(claims),
        raw_metadata_json={
            "group_key": group_key,
            "claim_types": sorted({claim.claim_type for claim in claims}),
            "source_titles": [source.source_title for source in sources if source.source_title],
        },
    )


def validate_candidate(candidate: CandidateDraft) -> str | None:
    if candidate.status not in VALID_PROJECT_CANDIDATE_STATUSES:
        return f"invalid status: {candidate.status}"
    if not 0 <= candidate.confidence <= 1:
        return f"invalid confidence: {candidate.confidence}"
    if not candidate.candidate_name:
        return "candidate_name is required"
    return None


class ProjectCandidateGenerator:
    def __init__(self, db: Session):
        self.db = db

    def generate(
        self,
        *,
        dry_run: bool = False,
        limit: int | None = None,
        status: str | None = "extracted",
        source_id: uuid.UUID | None = None,
    ) -> ProjectCandidateGenerationSummary:
        claims = self._load_claims(limit=limit, status=status, source_id=source_id)
        summary = ProjectCandidateGenerationSummary(claims_checked=len(claims))
        if not claims:
            summary.warnings.append("no_extracted_claims_available")
            return summary
        source_map = self._source_map(claims)
        grouped: dict[str, list[DiscoveredSourceClaim]] = {}
        for claim in claims:
            source = source_map.get(claim.discovered_source_id)
            if source is None:
                summary.validation_errors.append(
                    {"claim_id": str(claim.id), "message": "missing discovered source"}
                )
                continue
            group_key = candidate_group_key(source, [item for item in claims if item.discovered_source_id == source.id])
            grouped.setdefault(group_key, []).append(claim)
        summary.sources_grouped = len({str(claim.discovered_source_id) for claim in claims})
        for group_key, group_claims in grouped.items():
            sources = [source_map[claim.discovered_source_id] for claim in group_claims if claim.discovered_source_id in source_map]
            unique_sources = list({source.id: source for source in sources}.values())
            if not unique_sources:
                continue
            candidate = build_candidate_draft(group_key, unique_sources, group_claims)
            error = validate_candidate(candidate)
            if error:
                summary.validation_errors.append({"group_key": group_key, "message": error})
                continue
            existing = self.get_by_key(candidate.candidate_key)
            if dry_run:
                if existing is None:
                    summary.candidates_created += 1
                else:
                    summary.candidates_skipped += 1
                continue
            if existing is None:
                self.db.add(ProjectCandidate(**asdict(candidate)))
                summary.candidates_created += 1
            else:
                update_project_candidate(existing, candidate)
                summary.candidates_updated += 1
        if not dry_run:
            self.db.flush()
        return summary

    def get_by_key(self, candidate_key: str) -> ProjectCandidate | None:
        return self.db.scalar(select(ProjectCandidate).where(ProjectCandidate.candidate_key == candidate_key))

    def list_candidates(
        self,
        *,
        status: str | None = None,
        state: str | None = None,
        limit: int = 100,
    ) -> list[ProjectCandidate]:
        query = select(ProjectCandidate).order_by(ProjectCandidate.created_at.desc())
        if status:
            query = query.where(ProjectCandidate.status == status)
        if state:
            query = query.where(ProjectCandidate.state == state)
        return list(self.db.scalars(query.limit(max(1, min(limit, 500)))))

    def _load_claims(
        self,
        *,
        limit: int | None,
        status: str | None,
        source_id: uuid.UUID | None,
    ) -> list[DiscoveredSourceClaim]:
        query = select(DiscoveredSourceClaim).order_by(DiscoveredSourceClaim.created_at.asc())
        if status:
            query = query.where(DiscoveredSourceClaim.status == status)
        if source_id:
            query = query.where(DiscoveredSourceClaim.discovered_source_id == source_id)
        if limit is not None:
            query = query.limit(max(0, limit))
        return list(self.db.scalars(query))

    def _source_map(self, claims: list[DiscoveredSourceClaim]) -> dict[uuid.UUID, DiscoveredSourceRecord]:
        source_ids = {claim.discovered_source_id for claim in claims}
        if not source_ids:
            return {}
        sources = self.db.scalars(select(DiscoveredSourceRecord).where(DiscoveredSourceRecord.id.in_(source_ids)))
        return {source.id: source for source in sources}


def update_project_candidate(record: ProjectCandidate, candidate: CandidateDraft) -> None:
    for field_name, value in asdict(candidate).items():
        if field_name == "candidate_key":
            continue
        setattr(record, field_name, value)
