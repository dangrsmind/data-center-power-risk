from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovered_source import DiscoveredSourceClaim, DiscoveredSourceRecord
from app.models.project_candidate import ProjectCandidate


AUTO_ADMIT_ELIGIBLE = "auto_admit_eligible"
NEEDS_REVIEW = "needs_review"
QUARANTINED = "quarantined"
VALID_VERIFICATION_STATUSES = {AUTO_ADMIT_ELIGIBLE, NEEDS_REVIEW, QUARANTINED}
OFFICIAL_PUBLISHER_TERMS = ("state corporation commission", "commission", ".gov")
OFFICIAL_SOURCE_TYPES = {"state_regulatory_dockets", "official_filing", "regulatory_record", "county_record"}
CONTEXT_SOURCE_TYPES = {"grid_context"}
PROJECT_SPECIFIC_CLAIMS = {"possible_project_name", "developer", "city", "county", "state", "load_mw", "utility"}


@dataclass
class SourceQualitySummary:
    source_count: int
    claim_count: int
    official_source_count: int
    context_only_source_count: int
    publishers: list[str]
    source_types: list[str]


@dataclass
class ProjectCandidateVerificationResult:
    candidate_id: str
    decision: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    blocking_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    required_fields_present: dict[str, bool] = field(default_factory=dict)
    evidence_requirements_met: dict[str, bool] = field(default_factory=dict)
    source_quality_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProjectCandidateVerifier:
    def __init__(self, db: Session):
        self.db = db

    def verify(
        self,
        candidate: ProjectCandidate,
        *,
        threshold: float = 0.80,
        persist: bool = False,
    ) -> ProjectCandidateVerificationResult:
        source_refs = candidate.discovered_source_ids_json or []
        claim_refs = candidate.discovered_source_claim_ids_json or []
        sources = self._sources(source_refs)
        claims = self._claims(claim_refs)
        source_quality = summarize_sources(sources)
        result = evaluate_candidate(
            candidate,
            sources=sources,
            claims=claims,
            source_quality=source_quality,
            threshold=threshold,
        )
        if persist:
            persist_verification(candidate, result)
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


def valid_uuid_refs(refs: list[str]) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    for ref in refs:
        try:
            ids.append(uuid.UUID(str(ref)))
        except ValueError:
            continue
    return ids


def valid_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def unresolved_name(value: str | None) -> bool:
    return not value or value.startswith("Unresolved ")


def is_official_source(source: DiscoveredSourceRecord) -> bool:
    source_type = (source.source_type or "").lower()
    publisher = (source.publisher or "").lower()
    url = (source.source_url or "").lower()
    return (
        source_type in OFFICIAL_SOURCE_TYPES
        or any(term in publisher for term in OFFICIAL_PUBLISHER_TERMS)
        or ".gov" in url
    )


def is_context_only_source(source: DiscoveredSourceRecord) -> bool:
    source_type = (source.source_type or "").lower()
    registry_id = (source.source_registry_id or "").lower()
    return source_type in CONTEXT_SOURCE_TYPES or "context" in source_type or "context" in registry_id


def summarize_sources(sources: list[DiscoveredSourceRecord]) -> SourceQualitySummary:
    publishers = sorted({source.publisher for source in sources if source.publisher})
    source_types = sorted({source.source_type for source in sources if source.source_type})
    return SourceQualitySummary(
        source_count=len(sources),
        claim_count=0,
        official_source_count=sum(1 for source in sources if is_official_source(source)),
        context_only_source_count=sum(1 for source in sources if is_context_only_source(source)),
        publishers=publishers,
        source_types=source_types,
    )


def evaluate_candidate(
    candidate: ProjectCandidate,
    *,
    sources: list[DiscoveredSourceRecord],
    claims: list[DiscoveredSourceClaim],
    source_quality: SourceQualitySummary,
    threshold: float,
) -> ProjectCandidateVerificationResult:
    source_refs = candidate.discovered_source_ids_json or []
    claim_refs = candidate.discovered_source_claim_ids_json or []
    claim_types = {claim.claim_type for claim in claims}
    source_quality.claim_count = len(claims)
    required = {
        "primary_source_url": bool(candidate.primary_source_url),
        "valid_primary_source_url": valid_url(candidate.primary_source_url),
        "discovered_source_refs": bool(source_refs),
        "discovered_source_records": bool(sources),
        "discovered_source_claim_refs": bool(claim_refs),
        "discovered_source_claim_records": bool(claims),
        "state": bool(candidate.state),
        "candidate_name": bool(candidate.candidate_name),
        "resolved_candidate_name": not unresolved_name(candidate.candidate_name),
    }
    evidence = {
        "official_or_high_trust_source": source_quality.official_source_count > 0,
        "not_context_only": bool(sources) and source_quality.context_only_source_count < len(sources),
        "project_specific_claim": bool(PROJECT_SPECIFIC_CLAIMS & claim_types),
        "explicit_project_name_claim": "possible_project_name" in claim_types,
        "specificity_claim": bool({"developer", "city", "county", "load_mw", "utility"} & claim_types),
        "candidate_confidence_above_threshold": candidate.confidence >= threshold,
    }
    reasons: list[str] = []
    blocking_errors: list[str] = []
    warnings: list[str] = []

    for field_name, present in required.items():
        if not present and field_name in {
            "primary_source_url",
            "valid_primary_source_url",
            "discovered_source_refs",
            "discovered_source_claim_refs",
        }:
            blocking_errors.append(f"missing_or_invalid_{field_name}")

    if not required["candidate_name"]:
        blocking_errors.append("missing_candidate_name")
    if not required["state"]:
        warnings.append("missing_state")
    if not required["resolved_candidate_name"]:
        warnings.append("unresolved_candidate_name")
    if not evidence["not_context_only"]:
        blocking_errors.append("context_only_or_missing_source")
    if candidate.confidence < 0.5:
        blocking_errors.append("candidate_confidence_too_low")
    elif candidate.confidence < threshold:
        warnings.append("candidate_confidence_below_auto_admit_threshold")
    if not evidence["project_specific_claim"]:
        warnings.append("missing_project_specific_claim")
    if not evidence["official_or_high_trust_source"]:
        warnings.append("source_not_official_or_high_trust")

    eligible = (
        not blocking_errors
        and required["state"]
        and required["resolved_candidate_name"]
        and evidence["official_or_high_trust_source"]
        and evidence["project_specific_claim"]
        and evidence["explicit_project_name_claim"]
        and evidence["candidate_confidence_above_threshold"]
    )
    if eligible:
        decision = AUTO_ADMIT_ELIGIBLE
        reasons.append("strict_official_source_project_specific_evidence")
    elif blocking_errors:
        decision = QUARANTINED
        reasons.append("blocking_evidence_or_quality_failure")
    else:
        decision = NEEDS_REVIEW
        reasons.append("source_backed_but_requires_review")

    confidence = verification_confidence(candidate, decision, evidence, required)
    return ProjectCandidateVerificationResult(
        candidate_id=str(candidate.id),
        decision=decision,
        confidence=confidence,
        reasons=reasons,
        blocking_errors=blocking_errors,
        warnings=warnings,
        required_fields_present=required,
        evidence_requirements_met=evidence,
        source_quality_summary=asdict(source_quality),
    )


def verification_confidence(
    candidate: ProjectCandidate,
    decision: str,
    evidence: dict[str, bool],
    required: dict[str, bool],
) -> float:
    score = candidate.confidence
    score += sum(0.025 for value in evidence.values() if value)
    score += sum(0.01 for value in required.values() if value)
    if decision == QUARANTINED:
        score = min(score, 0.49)
    elif decision == NEEDS_REVIEW:
        score = min(score, 0.79)
    return round(max(0.0, min(1.0, score)), 3)


def persist_verification(candidate: ProjectCandidate, result: ProjectCandidateVerificationResult) -> None:
    candidate.verification_status = result.decision
    candidate.verification_confidence = result.confidence
    candidate.verification_reasons_json = result.reasons
    candidate.verification_errors_json = result.blocking_errors
    candidate.auto_admit_eligible = result.decision == AUTO_ADMIT_ELIGIBLE
    candidate.verified_at = datetime.now(timezone.utc)
