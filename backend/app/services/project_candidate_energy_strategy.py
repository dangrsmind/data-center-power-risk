from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.models.discovered_source import DiscoveredSourceClaim, DiscoveredSourceRecord
from app.models.project_candidate import ProjectCandidate


EnergyStrategy = Literal[
    "grid_only",
    "grid_plus_backup",
    "grid_plus_onsite",
    "dedicated_gas_generation",
    "diesel_generation",
    "fuel_cell",
    "nuclear_or_smr",
    "hybrid_power",
    "unknown",
]

ENERGY_STRATEGIES: tuple[str, ...] = (
    "grid_only",
    "grid_plus_backup",
    "grid_plus_onsite",
    "dedicated_gas_generation",
    "diesel_generation",
    "fuel_cell",
    "nuclear_or_smr",
    "hybrid_power",
    "unknown",
)

ENERGY_RISK_TAGS: tuple[str, ...] = (
    "grid",
    "diesel",
    "gas_turbine",
    "fuel_cell",
    "nuclear",
    "battery_storage",
    "renewable_ppa",
    "substation",
    "transmission",
    "fuel_supply",
    "air_permit",
    "emissions",
)


@dataclass(frozen=True)
class EnergyStrategyClassification:
    energy_strategy: EnergyStrategy = "unknown"
    energy_strategy_confidence: float = 0.2
    energy_strategy_reasons: list[str] = field(default_factory=list)
    energy_risk_tags: list[str] = field(default_factory=list)
    energy_strategy_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_project_candidate_energy_strategy(
    candidate: ProjectCandidate,
    *,
    sources: list[DiscoveredSourceRecord] | None = None,
    claims: list[DiscoveredSourceClaim] | None = None,
) -> EnergyStrategyClassification:
    text = searchable_energy_text(candidate, sources or [], claims or [])
    tags: set[str] = set()
    reasons: list[str] = []
    warnings: list[str] = []
    strategy_signals: set[str] = set()

    if not text:
        return EnergyStrategyClassification(
            energy_strategy="unknown",
            energy_strategy_confidence=0.2,
            energy_strategy_reasons=["no_explicit_energy_strategy_signal"],
            energy_risk_tags=[],
            energy_strategy_warnings=["energy_strategy_unknown"],
        )

    if any_text(text, GRID_CONTEXT_PATTERNS):
        tags.add("grid")
        reasons.append("energy_text_references_grid_or_interconnection")
    if any_text(text, SUBSTATION_PATTERNS):
        tags.add("substation")
    if any_text(text, TRANSMISSION_PATTERNS):
        tags.add("transmission")
    if any_text(text, BATTERY_PATTERNS):
        tags.add("battery_storage")
        reasons.append("energy_text_references_battery_storage")
    if any_text(text, RENEWABLE_PPA_PATTERNS):
        tags.add("renewable_ppa")
        reasons.append("energy_text_references_renewable_ppa")

    backup = any_text(text, BACKUP_GENERATOR_PATTERNS)
    diesel = any_text(text, DIESEL_PATTERNS)
    gas = any_text(text, GAS_TURBINE_PATTERNS)
    fuel_cell = any_text(text, FUEL_CELL_PATTERNS)
    nuclear = any_text(text, NUCLEAR_PATTERNS)
    onsite = any_text(text, ONSITE_PATTERNS)
    dedicated = any_text(text, DEDICATED_POWER_PATTERNS)
    grid_only = any_text(text, GRID_ONLY_PATTERNS)

    if backup:
        tags.add("grid")
        reasons.append("explicit_backup_or_emergency_generator_signal")
        warnings.append("backup_generation_not_primary_power")

    if diesel:
        tags.add("diesel")
        reasons.append("explicit_diesel_generation_signal")
        if backup and not dedicated and not onsite_primary_context(text, "diesel"):
            strategy_signals.add("grid_plus_backup")
        else:
            strategy_signals.add("diesel_generation")
        if any_text(text, AIR_PERMIT_PATTERNS):
            tags.add("air_permit")
            reasons.append("energy_text_references_air_permit")
        if any_text(text, EMISSIONS_PATTERNS) or backup or "generator" in text:
            tags.add("emissions")
            reasons.append("diesel_generation_emissions_review_signal")
        if any_text(text, FUEL_SUPPLY_PATTERNS):
            tags.add("fuel_supply")

    if gas:
        tags.update({"gas_turbine", "fuel_supply", "emissions"})
        reasons.append("explicit_gas_turbine_or_gas_generation_signal")
        if any_text(text, AIR_PERMIT_PATTERNS):
            tags.add("air_permit")
        if dedicated:
            strategy_signals.add("dedicated_gas_generation")
        else:
            strategy_signals.add("grid_plus_onsite")
        warnings.append("fuel_supply_risk_possible")
        warnings.append("air_emissions_review_needed")

    if fuel_cell:
        tags.add("fuel_cell")
        reasons.append("explicit_fuel_cell_signal")
        strategy_signals.add("fuel_cell")

    if nuclear:
        tags.add("nuclear")
        reasons.append("explicit_nuclear_or_smr_signal")
        strategy_signals.add("nuclear_or_smr")
        warnings.append("nuclear_strategy_uncertain")

    if onsite and not (diesel or gas or fuel_cell or nuclear):
        reasons.append("explicit_onsite_or_behind_the_meter_power_signal")
        strategy_signals.add("grid_plus_onsite")
        warnings.append("onsite_generation_requires_permit_review")

    if grid_only and not strategy_signals:
        strategy_signals.add("grid_only")
        tags.add("grid")
        reasons.append("explicit_grid_only_signal")

    if not strategy_signals and backup:
        strategy_signals.add("grid_plus_backup")

    if not strategy_signals:
        warning = "grid_or_interconnection_only_not_onsite_generation" if tags & {"grid", "substation", "transmission"} else "energy_strategy_unknown"
        return EnergyStrategyClassification(
            energy_strategy="unknown",
            energy_strategy_confidence=0.25 if tags else 0.2,
            energy_strategy_reasons=reasons or ["no_explicit_energy_strategy_signal"],
            energy_risk_tags=sorted(tags),
            energy_strategy_warnings=[warning],
        )

    if len(strategy_signals) > 1:
        strategy: EnergyStrategy = "hybrid_power"
        reasons.append("multiple_energy_strategy_signals")
        warnings.append("onsite_generation_requires_permit_review")
    else:
        strategy = next(iter(strategy_signals))  # type: ignore[assignment]

    confidence = confidence_for(strategy, strategy_signals, tags, warnings)
    return EnergyStrategyClassification(
        energy_strategy=strategy,
        energy_strategy_confidence=confidence,
        energy_strategy_reasons=dedupe_preserve_order(reasons),
        energy_risk_tags=sorted(tags),
        energy_strategy_warnings=dedupe_preserve_order(warnings),
    )


def energy_strategy_from_metadata(metadata: dict | list | None) -> EnergyStrategyClassification | None:
    if not isinstance(metadata, dict):
        return None
    raw = metadata.get("energy_strategy_classification")
    if not isinstance(raw, dict):
        return None
    strategy = raw.get("energy_strategy")
    if strategy not in ENERGY_STRATEGIES:
        return None
    confidence = raw.get("energy_strategy_confidence")
    return EnergyStrategyClassification(
        energy_strategy=strategy,
        energy_strategy_confidence=float(confidence) if isinstance(confidence, int | float) else 0.2,
        energy_strategy_reasons=[str(item) for item in raw.get("energy_strategy_reasons") or []],
        energy_risk_tags=[str(item) for item in raw.get("energy_risk_tags") or []],
        energy_strategy_warnings=[str(item) for item in raw.get("energy_strategy_warnings") or []],
    )


def persist_energy_strategy_classification(
    candidate: ProjectCandidate,
    classification: EnergyStrategyClassification,
) -> None:
    metadata = candidate.raw_metadata_json if isinstance(candidate.raw_metadata_json, dict) else {}
    candidate.raw_metadata_json = {
        **metadata,
        "energy_strategy_classification": classification.to_dict(),
    }


def confidence_for(
    strategy: EnergyStrategy,
    strategy_signals: set[str],
    tags: set[str],
    warnings: list[str],
) -> float:
    if strategy == "unknown":
        return 0.2
    if strategy == "hybrid_power":
        return 0.72
    if strategy == "grid_plus_backup":
        return 0.62
    if strategy == "nuclear_or_smr":
        return 0.58 if "nuclear_strategy_uncertain" in warnings else 0.68
    if tags & {"diesel", "gas_turbine", "fuel_cell"}:
        return 0.74
    if strategy_signals:
        return 0.6
    return 0.25


def searchable_energy_text(
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
        for key, item in value.items():
            if key == "energy_strategy_classification":
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


def any_text(text: str, patterns: tuple[str, ...]) -> bool:
    return any(text_contains_pattern(text, pattern) for pattern in patterns)


def text_contains_pattern(text: str, pattern: str) -> bool:
    escaped = re.escape(pattern)
    if pattern.replace("-", "").replace(" ", "").replace("/", "").isalnum():
        return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None
    return pattern in text


def onsite_primary_context(text: str, source: str) -> bool:
    source_pattern = re.escape(source)
    return re.search(rf"(primary|main|dedicated|behind[- ]the[- ]meter|on[- ]site|onsite).{{0,80}}{source_pattern}", text) is not None


def dedupe_preserve_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


GRID_ONLY_PATTERNS = (
    "grid only",
    "utility service only",
    "no onsite generation",
    "no on-site generation",
)
GRID_CONTEXT_PATTERNS = (
    "grid",
    "utility service",
    "electric service",
    "interconnection",
)
SUBSTATION_PATTERNS = (
    "substation",
    "switchyard",
)
TRANSMISSION_PATTERNS = (
    "transmission",
    "transmission line",
    "power line",
)
BACKUP_GENERATOR_PATTERNS = (
    "backup generator",
    "backup generators",
    "backup diesel generator",
    "backup diesel generators",
    "emergency backup generator",
    "emergency backup generators",
    "emergency backup diesel generator",
    "emergency backup diesel generators",
    "emergency generator",
    "emergency generators",
    "standby generator",
    "standby generators",
)
DIESEL_PATTERNS = (
    "diesel generator",
    "diesel generators",
    "diesel-fired generator",
    "diesel fired generator",
    "diesel generation",
)
GAS_TURBINE_PATTERNS = (
    "gas turbine",
    "gas turbines",
    "combustion turbine",
    "combustion turbines",
    "natural gas generation",
    "gas-fired generation",
    "gas fired generation",
    "natural gas power plant",
    "gas plant",
)
FUEL_CELL_PATTERNS = (
    "fuel cell",
    "fuel cells",
)
NUCLEAR_PATTERNS = (
    "small modular reactor",
    "small modular reactors",
    "advanced nuclear",
    "nuclear power",
    "nuclear reactor",
    "nuclear reactors",
    "smr",
)
ONSITE_PATTERNS = (
    "onsite generation",
    "on-site generation",
    "behind-the-meter",
    "behind the meter",
    "self generation",
    "self-generation",
    "microgrid",
    "onsite power",
    "on-site power",
)
DEDICATED_POWER_PATTERNS = (
    "dedicated power plant",
    "dedicated power",
    "behind-the-meter",
    "behind the meter",
    "captive power plant",
)
BATTERY_PATTERNS = (
    "battery storage",
    "battery energy storage",
    "bess",
)
RENEWABLE_PPA_PATTERNS = (
    "renewable ppa",
    "power purchase agreement",
    "solar ppa",
    "wind ppa",
)
AIR_PERMIT_PATTERNS = (
    "air permit",
    "air quality permit",
    "emissions permit",
)
EMISSIONS_PATTERNS = (
    "emissions",
    "greenhouse gas",
    "nox",
    "particulate",
)
FUEL_SUPPLY_PATTERNS = (
    "fuel supply",
    "gas pipeline",
    "natural gas supply",
    "diesel fuel",
)
