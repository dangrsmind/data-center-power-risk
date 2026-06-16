from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.discovered_source import DiscoveredSourceClaim, DiscoveredSourceRecord
from app.models.project_candidate import ProjectCandidate, ProjectCandidateSourceAttachment
from app.services.project_candidate_verifier import (
    NEEDS_REVIEW,
    PROJECT_SPECIFIC_CLAIMS,
    ProjectCandidateVerifier,
    is_context_only_source,
    is_official_source,
    unresolved_name,
)


TRIAGE_TIERS = {"high", "medium", "low"}
RECOMMENDED_ACTIONS = {
    "review_for_promotion",
    "needs_source_detail",
    "needs_location",
    "needs_project_name",
    "likely_context_only",
    "ready_for_verification",
    "defer",
}


@dataclass
class ProjectCandidateTriageResult:
    candidate_id: str
    triage_score: float
    triage_tier: str
    triage_reasons: list[str] = field(default_factory=list)
    triage_warnings: list[str] = field(default_factory=list)
    recommended_action: str = "defer"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProjectCandidateTriageService:
    def __init__(self, db: Session):
        self.db = db

    def triage(
        self,
        candidate: ProjectCandidate,
        *,
        persist: bool = False,
    ) -> ProjectCandidateTriageResult:
        sources = self._sources(candidate.discovered_source_ids_json or [])
        claims = self._claims(candidate.discovered_source_claim_ids_json or [])
        verification = ProjectCandidateVerifier(self.db).verify(candidate)
        source_attachment_count = self._source_attachment_count(candidate.id)
        result = evaluate_candidate_triage(
            candidate,
            sources=sources,
            claims=claims,
            verification=verification.to_dict(),
            source_attachment_count=source_attachment_count,
        )
        if persist:
            persist_triage(candidate, result)
            self.db.flush()
        return result

    def get_candidate(self, candidate_id: uuid.UUID) -> ProjectCandidate | None:
        return self.db.get(ProjectCandidate, candidate_id)

    def list_candidates(self, *, candidate_id: uuid.UUID | None = None, limit: int | None = None) -> list[ProjectCandidate]:
        query = select(ProjectCandidate).order_by(ProjectCandidate.created_at.asc())
        if candidate_id:
            query = query.where(ProjectCandidate.id == candidate_id)
        if limit is not None:
            query = query.limit(max(0, limit))
        return list(self.db.scalars(query))

    def _sources(self, source_refs: list[str]) -> list[DiscoveredSourceRecord]:
        source_ids = valid_uuid_refs(source_refs)
        if not source_ids:
            return []
        return list(self.db.scalars(select(DiscoveredSourceRecord).where(DiscoveredSourceRecord.id.in_(source_ids))))

    def _claims(self, claim_refs: list[str]) -> list[DiscoveredSourceClaim]:
        claim_ids = valid_uuid_refs(claim_refs)
        if not claim_ids:
            return []
        return list(self.db.scalars(select(DiscoveredSourceClaim).where(DiscoveredSourceClaim.id.in_(claim_ids))))

    def _source_attachment_count(self, candidate_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count(ProjectCandidateSourceAttachment.id)).where(
                    ProjectCandidateSourceAttachment.project_candidate_id == candidate_id
                )
            )
            or 0
        )


def valid_uuid_refs(refs: list[str]) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    for ref in refs:
        try:
            ids.append(uuid.UUID(str(ref)))
        except ValueError:
            continue
    return ids


def evaluate_candidate_triage(
    candidate: ProjectCandidate,
    *,
    sources: list[DiscoveredSourceRecord],
    claims: list[DiscoveredSourceClaim],
    verification: dict[str, Any],
    source_attachment_count: int = 0,
) -> ProjectCandidateTriageResult:
    reasons: list[str] = []
    warnings: list[str] = []
    score = 0.12
    claim_types = {claim.claim_type for claim in claims}
    official_count = sum(1 for source in sources if is_official_source(source))
    context_count = sum(1 for source in sources if is_context_only_source(source))
    has_context_only_source = bool(sources) and context_count >= len(sources)
    has_project_claim = bool(PROJECT_SPECIFIC_CLAIMS & claim_types)
    has_named_project = not unresolved_name(candidate.candidate_name)
    has_location = bool(candidate.state)
    has_specific_location = bool(candidate.county or candidate.city)
    has_load_or_utility = bool(candidate.utility or candidate.load_mw or {"load_mw", "utility"} & claim_types)
    dataset_provenance = dataset_import_provenance(candidate.raw_metadata_json)
    generic_title_count = sum(1 for source in sources if generic_source_title(source.source_title))
    has_source_attachment = source_attachment_count > 0

    if official_count:
        score += 0.18
        reasons.append("official_or_high_trust_source")
    else:
        warnings.append("non_official_source_only")
        score -= 0.08

    if has_project_claim:
        score += 0.16
        reasons.append("project_specific_claim")
    else:
        warnings.append("missing_project_specific_claim")
        score -= 0.12

    if has_named_project:
        score += 0.12
        reasons.append("resolved_candidate_name")
    else:
        warnings.append("unresolved_candidate_name")
        score -= 0.15

    if candidate.developer:
        score += 0.06
        reasons.append("developer_present")
    if has_location:
        score += 0.10
        reasons.append("state_present")
    else:
        warnings.append("missing_state")
        score -= 0.12
    if has_specific_location:
        score += 0.05
        reasons.append("county_or_city_present")
    if has_load_or_utility:
        score += 0.08
        reasons.append("utility_or_load_reference")
    if dataset_provenance:
        score += 0.04
        reasons.append("dataset_import_provenance")
        if dataset_provenance.get("source_urls") or candidate.primary_source_url:
            score += 0.04
            reasons.append("dataset_source_url_present")
        if dataset_provenance.get("citation") or dataset_provenance.get("license_note"):
            score += 0.03
            reasons.append("dataset_citation_or_license_present")
        if has_location:
            score += 0.03
            reasons.append("dataset_location_signal")
        if candidate.developer:
            score += 0.02
            reasons.append("dataset_operator_or_developer_present")
        if candidate.load_mw:
            score += 0.03
            reasons.append("dataset_load_reference")
        warnings.append("dataset_import_requires_source_review")
    if has_source_attachment:
        score += 0.05
        reasons.append("analyst_source_attachment_present")
    if len(claims) >= 4:
        score += 0.06
        reasons.append("multiple_supporting_claims")
    elif len(claims) >= 2:
        score += 0.03
        reasons.append("supporting_claims_present")
    if candidate.source_count and candidate.source_count > 1:
        score += 0.04
        reasons.append("multiple_sources")
    if candidate.confidence >= 0.75:
        score += 0.10
        reasons.append("high_candidate_confidence")
    elif candidate.confidence < 0.5:
        warnings.append("low_candidate_confidence")
        score -= 0.12
    elif candidate.confidence < 0.65:
        warnings.append("moderate_candidate_confidence")
        score -= 0.04

    if verification.get("decision") == NEEDS_REVIEW and verification.get("confidence", 0) >= 0.75:
        score += 0.08
        reasons.append("near_auto_admit_threshold_but_needs_review")
    if has_context_only_source:
        warnings.append("context_only_source")
        score -= 0.25
    if generic_title_count:
        warnings.append("generic_or_duplicate_source_title")
        score -= 0.04

    score = round(max(0.0, min(1.0, score)), 3)
    tier = tier_for_score(score)
    action = recommended_action_for(
        score=score,
        has_context_only_source=has_context_only_source,
        has_project_claim=has_project_claim,
        has_location=has_location,
        has_named_project=has_named_project,
        has_source_attachment=has_source_attachment,
        official_count=official_count,
    )
    return ProjectCandidateTriageResult(
        candidate_id=str(candidate.id),
        triage_score=score,
        triage_tier=tier,
        triage_reasons=reasons,
        triage_warnings=warnings,
        recommended_action=action,
    )


def tier_for_score(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def recommended_action_for(
    *,
    score: float,
    has_context_only_source: bool,
    has_project_claim: bool,
    has_location: bool,
    has_named_project: bool,
    has_source_attachment: bool,
    official_count: int,
) -> str:
    if has_context_only_source:
        return "likely_context_only"
    if not has_named_project:
        return "needs_project_name"
    if not has_location:
        return "needs_location"
    if has_source_attachment:
        return "ready_for_verification"
    if not has_project_claim or not official_count:
        return "needs_source_detail"
    if score >= 0.7:
        return "review_for_promotion"
    return "defer"


def generic_source_title(value: str | None) -> bool:
    if not value:
        return False
    text = value.strip().lower()
    return text in {"data center", "planning commission", "agenda"} or text.startswith("search result")


def dataset_import_provenance(metadata: dict | list | None) -> dict[str, Any] | None:
    if isinstance(metadata, dict) and metadata.get("provenance") == "dataset_import":
        return metadata
    return None


def persist_triage(candidate: ProjectCandidate, result: ProjectCandidateTriageResult) -> None:
    candidate.triage_score = result.triage_score
    candidate.triage_tier = result.triage_tier
    candidate.triage_reasons_json = result.triage_reasons
    candidate.triage_warnings_json = result.triage_warnings
    candidate.recommended_action = result.recommended_action
    candidate.triaged_at = datetime.now(timezone.utc)
