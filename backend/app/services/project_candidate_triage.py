from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.discovered_source import DiscoveredSourceClaim, DiscoveredSourceRecord
from app.models.project_candidate import ProjectCandidate
from app.services.project_candidate_energy_strategy import (
    classify_project_candidate_energy_strategy,
)
from app.services.project_candidate_siting_friction import (
    classify_project_candidate_siting_friction,
)
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
    "defer",
}

BUILD_CONSTRAINT_SIGNAL_PATTERNS = {
    "community_opposition": (
        "community opposition",
        "public opposition",
        "residents oppose",
        "resident opposition",
        "neighbors oppose",
        "neighborhood opposition",
        "citizen opposition",
        "public hearing opposition",
        "petition against",
        "moratorium",
    ),
    "litigation_or_legal": (
        "lawsuit",
        "litigation",
        "legal challenge",
        "court challenge",
        "appeal filed",
        "sued",
    ),
    "permitting_or_regulatory": (
        "permit application",
        "permit approval",
        "permitting",
        "regulatory approval",
        "regulatory review",
        "certificate of public convenience",
        "site plan approval",
        "special use permit",
        "conditional use permit",
        "rezoning application",
    ),
    "onsite_generation": (
        "onsite generation",
        "on-site generation",
        "behind-the-meter",
        "behind the meter",
        "dedicated power plant",
        "self generation",
        "microgrid",
        "fuel cell",
    ),
    "diesel_generation": (
        "diesel generator",
        "diesel generators",
        "backup generator",
        "backup generators",
        "emergency generator",
        "emergency generators",
    ),
    "gas_turbine_generation": (
        "gas turbine",
        "gas turbines",
        "combustion turbine",
        "combustion turbines",
        "natural gas generation",
        "gas-fired generation",
        "gas fired generation",
    ),
    "nuclear_or_smr": (
        "small modular reactor",
        "small modular reactors",
        "smr",
        "nuclear power",
        "nuclear reactor",
        "advanced nuclear",
    ),
    "air_emissions": (
        "air permit",
        "air quality permit",
        "air emissions",
        "emissions permit",
        "emissions compliance",
        "greenhouse gas",
        "nox emissions",
        "particulate emissions",
    ),
    "water_cooling": (
        "water use",
        "water usage",
        "water withdrawal",
        "cooling water",
        "cooling tower",
        "cooling towers",
        "chiller",
        "wastewater",
    ),
    "cost_financing": (
        "capital cost",
        "project cost",
        "financing",
        "funding gap",
        "cost overrun",
        "ratepayer cost",
        "bond financing",
        "tax incentive",
    ),
}


@dataclass
class ProjectCandidateTriageResult:
    candidate_id: str
    triage_score: float
    triage_tier: str
    triage_reasons: list[str] = field(default_factory=list)
    triage_warnings: list[str] = field(default_factory=list)
    recommended_action: str = "defer"
    energy_strategy_classification: dict[str, Any] = field(default_factory=dict)
    siting_friction_classification: dict[str, Any] = field(default_factory=dict)

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
        result = evaluate_candidate_triage(
            candidate,
            sources=sources,
            claims=claims,
            verification=verification.to_dict(),
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
    build_constraint_signals = detect_build_constraint_signals(candidate, sources, claims)
    energy_strategy = classify_project_candidate_energy_strategy(candidate, sources=sources, claims=claims)
    siting_friction = classify_project_candidate_siting_friction(candidate, sources=sources, claims=claims)

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
    if build_constraint_signals:
        signal_bonus = min(0.08, 0.015 * len(build_constraint_signals))
        score += signal_bonus
        reasons.extend(f"build_constraint_signal_{signal}" for signal in build_constraint_signals)
    apply_energy_strategy_triage(energy_strategy.to_dict(), reasons, warnings)
    apply_siting_friction_triage(siting_friction.to_dict(), reasons, warnings)

    score = round(max(0.0, min(1.0, score)), 3)
    tier = tier_for_score(score)
    action = recommended_action_for(
        score=score,
        has_context_only_source=has_context_only_source,
        has_project_claim=has_project_claim,
        has_location=has_location,
        has_named_project=has_named_project,
        official_count=official_count,
    )
    return ProjectCandidateTriageResult(
        candidate_id=str(candidate.id),
        triage_score=score,
        triage_tier=tier,
        triage_reasons=reasons,
        triage_warnings=warnings,
        recommended_action=action,
        energy_strategy_classification=energy_strategy.to_dict(),
        siting_friction_classification=siting_friction.to_dict(),
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
    official_count: int,
) -> str:
    if has_context_only_source:
        return "likely_context_only"
    if not has_named_project:
        return "needs_project_name"
    if not has_location:
        return "needs_location"
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


def detect_build_constraint_signals(
    candidate: ProjectCandidate,
    sources: list[DiscoveredSourceRecord],
    claims: list[DiscoveredSourceClaim],
) -> list[str]:
    text = searchable_candidate_text(candidate, sources, claims)
    detected = [
        signal
        for signal, patterns in BUILD_CONSTRAINT_SIGNAL_PATTERNS.items()
        if any(text_contains_pattern(text, pattern) for pattern in patterns)
    ]
    return sorted(detected)


def apply_energy_strategy_triage(
    classification: dict[str, Any],
    reasons: list[str],
    warnings: list[str],
) -> None:
    strategy = classification.get("energy_strategy") or "unknown"
    tags = set(classification.get("energy_risk_tags") or [])
    strategy_reason_map = {
        "grid_plus_onsite": "energy_strategy_onsite_generation",
        "diesel_generation": "energy_strategy_diesel",
        "dedicated_gas_generation": "energy_strategy_gas_turbine",
        "nuclear_or_smr": "energy_strategy_nuclear_or_smr",
        "fuel_cell": "energy_strategy_fuel_cell",
        "hybrid_power": "energy_strategy_hybrid_power",
        "unknown": "energy_strategy_unknown",
    }
    reason = strategy_reason_map.get(str(strategy))
    if reason:
        reasons.append(reason)
    if strategy == "grid_plus_backup":
        warnings.append("backup_generation_not_primary_power")
    if strategy in {"grid_plus_onsite", "diesel_generation", "dedicated_gas_generation", "fuel_cell", "hybrid_power"}:
        warnings.append("onsite_generation_requires_permit_review")
    if strategy == "nuclear_or_smr":
        warnings.append("nuclear_strategy_uncertain")
    if "fuel_supply" in tags:
        warnings.append("fuel_supply_risk_possible")
    if {"air_permit", "emissions"} & tags:
        warnings.append("air_emissions_review_needed")


def apply_siting_friction_triage(
    classification: dict[str, Any],
    reasons: list[str],
    warnings: list[str],
) -> None:
    categories = set(classification.get("siting_friction_categories") or [])
    category_reason_map = {
        "community_opposition": "siting_community_opposition",
        "public_hearing": "siting_public_hearing",
        "zoning_land_use": "siting_zoning_land_use",
        "litigation": "siting_litigation",
        "permit_delay": "siting_permit_delay",
        "environmental_review": "siting_permit_delay",
        "air_permitting": "siting_air_emissions",
        "emissions_concern": "siting_air_emissions",
        "water_cooling": "siting_water_cooling",
        "cost_financing": "siting_cost_financing",
        "political_opposition": "siting_political_opposition",
    }
    for category, reason in category_reason_map.items():
        if category in categories:
            reasons.append(reason)
    if "public_hearing" in categories and "community_opposition" not in categories:
        warnings.append("public_hearing_not_opposition")
    if "litigation" in categories:
        warnings.append("litigation_requires_source_review")
    if "water_cooling" in categories:
        warnings.append("water_risk_requires_source_review")
    if {"air_permitting", "emissions_concern"} & categories:
        warnings.append("air_emissions_requires_permit_review")
    if "cost_financing" in categories:
        warnings.append("cost_signal_not_delay_proof")


def text_contains_pattern(text: str, pattern: str) -> bool:
    escaped = re.escape(pattern)
    if pattern.replace("-", "").replace(" ", "").isalnum():
        return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None
    return pattern in text


def searchable_candidate_text(
    candidate: ProjectCandidate,
    sources: list[DiscoveredSourceRecord],
    claims: list[DiscoveredSourceClaim],
) -> str:
    parts: list[str] = [
        candidate.candidate_name,
        candidate.developer,
        candidate.state,
        candidate.county,
        candidate.city,
        candidate.utility,
        candidate.primary_source_url,
        candidate.evidence_excerpt,
    ]
    for source in sources:
        parts.extend(
            [
                source.source_url,
                source.source_title,
                source.source_type,
                source.publisher,
                source.geography,
                source.search_term,
                source.snippet,
                source.document_type,
            ]
        )
        parts.extend(metadata_text_parts(source.raw_metadata_json))
    for claim in claims:
        parts.extend([claim.claim_type, claim.claim_value, claim.evidence_excerpt])
        parts.extend(metadata_text_parts(claim.raw_metadata_json))
    parts.extend(metadata_text_parts(candidate.raw_metadata_json))
    return " ".join(str(part).lower() for part in parts if part)


def metadata_text_parts(value: Any) -> list[str]:
    if isinstance(value, dict):
        parts: list[str] = []
        for item in value.values():
            parts.extend(metadata_text_parts(item))
        return parts
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            parts.extend(metadata_text_parts(item))
        return parts
    if isinstance(value, str):
        return [value]
    return []


def persist_triage(candidate: ProjectCandidate, result: ProjectCandidateTriageResult) -> None:
    candidate.triage_score = result.triage_score
    candidate.triage_tier = result.triage_tier
    candidate.triage_reasons_json = result.triage_reasons
    candidate.triage_warnings_json = result.triage_warnings
    candidate.recommended_action = result.recommended_action
    candidate.triaged_at = datetime.now(timezone.utc)
    if result.energy_strategy_classification:
        metadata = candidate.raw_metadata_json if isinstance(candidate.raw_metadata_json, dict) else {}
        candidate.raw_metadata_json = {
            **metadata,
            "energy_strategy_classification": result.energy_strategy_classification,
        }
    if result.siting_friction_classification:
        metadata = candidate.raw_metadata_json if isinstance(candidate.raw_metadata_json, dict) else {}
        candidate.raw_metadata_json = {
            **metadata,
            "siting_friction_classification": result.siting_friction_classification,
        }
