from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.models.discovered_source import DiscoveredSourceClaim, DiscoveredSourceRecord
from app.models.project_candidate import ProjectCandidate


SitingFrictionCategory = Literal[
    "community_opposition",
    "public_hearing",
    "moratorium",
    "zoning_land_use",
    "litigation",
    "permit_delay",
    "environmental_review",
    "air_permitting",
    "emissions_concern",
    "water_cooling",
    "noise_concern",
    "traffic_concern",
    "tax_incentive_backlash",
    "political_opposition",
    "utility_regulatory_approval",
    "cost_financing",
    "schedule_credibility",
    "unknown",
]

SITING_FRICTION_CATEGORIES: tuple[str, ...] = (
    "community_opposition",
    "public_hearing",
    "moratorium",
    "zoning_land_use",
    "litigation",
    "permit_delay",
    "environmental_review",
    "air_permitting",
    "emissions_concern",
    "water_cooling",
    "noise_concern",
    "traffic_concern",
    "tax_incentive_backlash",
    "political_opposition",
    "utility_regulatory_approval",
    "cost_financing",
    "schedule_credibility",
    "unknown",
)


@dataclass(frozen=True)
class SitingFrictionClassification:
    siting_friction_categories: list[SitingFrictionCategory] = field(default_factory=lambda: ["unknown"])
    siting_friction_confidence: float = 0.2
    siting_friction_reasons: list[str] = field(default_factory=list)
    siting_friction_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_project_candidate_siting_friction(
    candidate: ProjectCandidate,
    *,
    sources: list[DiscoveredSourceRecord] | None = None,
    claims: list[DiscoveredSourceClaim] | None = None,
) -> SitingFrictionClassification:
    text = searchable_siting_text(candidate, sources or [], claims or [])
    categories: set[str] = set()
    reasons: list[str] = []
    warnings: list[str] = []

    if not text:
        return SitingFrictionClassification(
            siting_friction_categories=["unknown"],
            siting_friction_confidence=0.2,
            siting_friction_reasons=["no_explicit_siting_friction_signal"],
            siting_friction_warnings=["siting_friction_unknown"],
        )

    add_if(text, COMMUNITY_OPPOSITION_PATTERNS, "community_opposition", categories, reasons, "explicit_community_opposition_signal")
    add_if(text, PUBLIC_HEARING_PATTERNS, "public_hearing", categories, reasons, "explicit_public_hearing_or_meeting_signal")
    add_if(text, MORATORIUM_PATTERNS, "moratorium", categories, reasons, "explicit_moratorium_pause_ban_or_suspension_signal")
    add_if(text, ZONING_LAND_USE_PATTERNS, "zoning_land_use", categories, reasons, "explicit_zoning_or_land_use_signal")
    add_if(text, LITIGATION_PATTERNS, "litigation", categories, reasons, "explicit_litigation_or_legal_challenge_signal")
    add_if(text, PERMIT_DELAY_PATTERNS, "permit_delay", categories, reasons, "explicit_permit_or_regulatory_delay_signal")
    add_if(text, ENVIRONMENTAL_REVIEW_PATTERNS, "environmental_review", categories, reasons, "explicit_environmental_review_signal")
    add_if(text, NOISE_PATTERNS, "noise_concern", categories, reasons, "explicit_noise_concern_signal")
    add_if(text, TRAFFIC_PATTERNS, "traffic_concern", categories, reasons, "explicit_traffic_concern_signal")
    add_if(text, TAX_BACKLASH_PATTERNS, "tax_incentive_backlash", categories, reasons, "explicit_tax_incentive_backlash_signal")
    add_if(text, POLITICAL_OPPOSITION_PATTERNS, "political_opposition", categories, reasons, "explicit_political_opposition_signal")
    add_if(text, UTILITY_REGULATORY_PATTERNS, "utility_regulatory_approval", categories, reasons, "explicit_utility_regulatory_approval_signal")
    add_if(text, COST_FINANCING_PATTERNS, "cost_financing", categories, reasons, "explicit_cost_or_financing_signal")
    add_if(text, SCHEDULE_PATTERNS, "schedule_credibility", categories, reasons, "explicit_schedule_credibility_signal")

    if any_text(text, AIR_PERMITTING_PATTERNS):
        categories.add("air_permitting")
        reasons.append("explicit_air_permitting_signal")
    if any_text(text, EMISSIONS_PATTERNS) or any_text(text, GENERATION_AIR_CONTEXT_PATTERNS):
        categories.add("emissions_concern")
        reasons.append("explicit_air_emissions_or_generator_signal")

    if any_text(text, WATER_RISK_PATTERNS):
        categories.add("water_cooling")
        reasons.append("explicit_water_or_cooling_water_signal")

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

    if not categories:
        return SitingFrictionClassification(
            siting_friction_categories=["unknown"],
            siting_friction_confidence=0.2,
            siting_friction_reasons=["no_explicit_siting_friction_signal"],
            siting_friction_warnings=["siting_friction_unknown"],
        )

    return SitingFrictionClassification(
        siting_friction_categories=sorted(categories, key=SITING_FRICTION_CATEGORIES.index),  # type: ignore[arg-type]
        siting_friction_confidence=confidence_for(categories),
        siting_friction_reasons=dedupe_preserve_order(reasons),
        siting_friction_warnings=dedupe_preserve_order(warnings),
    )


def siting_friction_from_metadata(metadata: dict | list | None) -> SitingFrictionClassification | None:
    if not isinstance(metadata, dict):
        return None
    raw = metadata.get("siting_friction_classification")
    if not isinstance(raw, dict):
        return None
    categories = [
        str(item)
        for item in raw.get("siting_friction_categories") or []
        if str(item) in SITING_FRICTION_CATEGORIES
    ]
    if not categories:
        return None
    confidence = raw.get("siting_friction_confidence")
    return SitingFrictionClassification(
        siting_friction_categories=categories,  # type: ignore[arg-type]
        siting_friction_confidence=float(confidence) if isinstance(confidence, int | float) else 0.2,
        siting_friction_reasons=[str(item) for item in raw.get("siting_friction_reasons") or []],
        siting_friction_warnings=[str(item) for item in raw.get("siting_friction_warnings") or []],
    )


def confidence_for(categories: set[str]) -> float:
    if not categories or categories == {"unknown"}:
        return 0.2
    high_specificity = {
        "community_opposition",
        "moratorium",
        "litigation",
        "permit_delay",
        "air_permitting",
        "emissions_concern",
        "water_cooling",
        "political_opposition",
    }
    base = 0.62 if categories & high_specificity else 0.52
    return round(min(0.82, base + 0.04 * max(0, len(categories) - 1)), 2)


def searchable_siting_text(
    candidate: ProjectCandidate,
    sources: list[DiscoveredSourceRecord],
    claims: list[DiscoveredSourceClaim],
) -> str:
    parts: list[Any] = [
        candidate.candidate_name,
        candidate.developer,
        candidate.state,
        candidate.county,
        candidate.city,
        candidate.utility,
        candidate.primary_source_url,
        candidate.evidence_excerpt,
        candidate.review_decision,
        candidate.review_notes,
    ]
    parts.extend(candidate.triage_reasons_json or [])
    parts.extend(candidate.triage_warnings_json or [])
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
        for key, item in value.items():
            if key in {"energy_strategy_classification", "siting_friction_classification"}:
                continue
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


def add_if(
    text: str,
    patterns: tuple[str, ...],
    category: str,
    categories: set[str],
    reasons: list[str],
    reason: str,
) -> None:
    if any_text(text, patterns):
        categories.add(category)
        reasons.append(reason)


def any_text(text: str, patterns: tuple[str, ...]) -> bool:
    return any(text_contains_pattern(text, pattern) for pattern in patterns)


def text_contains_pattern(text: str, pattern: str) -> bool:
    escaped = re.escape(pattern)
    if pattern.replace("-", "").replace("/", "").replace(" ", "").isalnum():
        return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None
    return pattern in text


def dedupe_preserve_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


COMMUNITY_OPPOSITION_PATTERNS = (
    "community opposition",
    "public opposition",
    "residents oppose",
    "residents opposed",
    "resident opposition",
    "neighbors oppose",
    "neighbors opposed",
    "neighborhood opposition",
    "citizen opposition",
    "petition against",
    "opponents of the data center",
)
PUBLIC_HEARING_PATTERNS = (
    "public hearing",
    "public meeting",
    "town hall",
    "planning commission hearing",
)
MORATORIUM_PATTERNS = (
    "moratorium",
    "temporary ban",
    "data center ban",
    "pause on data centers",
    "paused data center approvals",
    "approval freeze",
    "permit freeze",
    "suspension of approvals",
)
ZONING_LAND_USE_PATTERNS = (
    "rezoning",
    "zoning",
    "land use",
    "site plan",
    "special use permit",
    "conditional use permit",
    "variance",
    "comprehensive plan",
)
LITIGATION_PATTERNS = (
    "lawsuit",
    "litigation",
    "legal challenge",
    "court challenge",
    "appeal filed",
    "complaint filed",
    "sued",
)
PERMIT_DELAY_PATTERNS = (
    "permit delay",
    "permitting delay",
    "delayed permit",
    "permit pending",
    "approval delayed",
    "regulatory delay",
    "regulatory review delayed",
)
ENVIRONMENTAL_REVIEW_PATTERNS = (
    "environmental review",
    "environmental impact",
    "environmental assessment",
    "environmental impact statement",
    "nepa review",
)
AIR_PERMITTING_PATTERNS = (
    "air permit",
    "air quality permit",
    "emissions permit",
    "air permitting",
)
EMISSIONS_PATTERNS = (
    "air emissions",
    "emissions concern",
    "emissions compliance",
    "pollution",
    "nox",
    "co2",
    "greenhouse gas",
    "particulate",
)
GENERATION_AIR_CONTEXT_PATTERNS = (
    "diesel generator",
    "diesel generators",
    "backup generator",
    "backup generators",
    "emergency generator",
    "emergency generators",
    "gas turbine",
    "gas turbines",
    "combustion turbine",
    "combustion turbines",
    "natural gas generation",
    "gas-fired generation",
    "gas fired generation",
)
WATER_RISK_PATTERNS = (
    "water use",
    "water usage",
    "water withdrawal",
    "cooling water",
    "aquifer",
    "river withdrawal",
    "wastewater",
    "drought",
    "water supply",
    "water demand",
)
NOISE_PATTERNS = (
    "noise concern",
    "noise concerns",
    "noise complaint",
    "sound study",
    "generator noise",
)
TRAFFIC_PATTERNS = (
    "traffic concern",
    "traffic concerns",
    "traffic study",
    "truck traffic",
    "road congestion",
)
TAX_BACKLASH_PATTERNS = (
    "tax incentive backlash",
    "tax abatement opposition",
    "tax break opposition",
    "incentive backlash",
)
POLITICAL_OPPOSITION_PATTERNS = (
    "political opposition",
    "council opposed",
    "supervisors opposed",
    "mayor opposed",
    "legislators opposed",
    "lawmakers opposed",
)
UTILITY_REGULATORY_PATTERNS = (
    "utility regulatory approval",
    "regulatory approval",
    "commission approval",
    "public service commission approval",
    "certificate of public convenience",
    "electric service agreement approval",
)
COST_FINANCING_PATTERNS = (
    "capital cost",
    "project cost",
    "financing",
    "funding gap",
    "cost overrun",
    "ratepayer cost",
    "bond financing",
)
SCHEDULE_PATTERNS = (
    "schedule delay",
    "construction delay",
    "timeline uncertainty",
    "schedule credibility",
    "delayed construction",
    "cancelled due to",
    "canceled due to",
    "paused construction",
    "revised schedule",
)
