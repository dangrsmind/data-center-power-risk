from __future__ import annotations

import re
from datetime import datetime
import uuid

from sqlalchemy.orm import Session

from app.core.enums import ClaimType, SourceType
from app.models.project import Phase, Project
from app.repositories.phase_repo import PhaseRepository
from app.repositories.project_repo import ProjectRepository
from app.schemas.automation import (
    ClaimSuggestRequest,
    ClaimSuggestResponse,
    IntakePacketRequest,
    IntakePacketResponse,
    SuggestedLinkTarget,
)
from app.schemas.ingestion import EvidenceClaimsCreateRequest, EvidenceCreateRequest


STATE_NAME_TO_CODE = {
    "alabama": "AL",
    "arizona": "AZ",
    "california": "CA",
    "florida": "FL",
    "georgia": "GA",
    "illinois": "IL",
    "new jersey": "NJ",
    "nevada": "NV",
    "north carolina": "NC",
    "ohio": "OH",
    "pennsylvania": "PA",
    "tennessee": "TN",
    "texas": "TX",
    "virginia": "VA",
    "washington": "WA",
}

UTILITY_PATTERNS = [
    "Rappahannock Electric Cooperative",
    "Dominion Energy",
    "Oncor",
    "Oncor Electric Delivery",
    "Georgia Power",
    "Duke Energy",
    "AEP Texas",
    "CenterPoint Energy",
    "Appalachian Power",
    "NOVEC",
]

RTO_PATTERNS = ["PJM", "ERCOT", "MISO", "SERC", "WECC", "CAISO", "SPP", "ISO-NE", "NYISO"]

GENERATOR_VERSION = "claims_suggest_v1"
INTAKE_PACKET_VERSION = "intake_packet_v1"

PROJECT_LEVEL_CLAIM_TYPES = {
    ClaimType.PROJECT_NAME_MENTION,
    ClaimType.DEVELOPER_NAMED,
    ClaimType.OPERATOR_NAMED,
    ClaimType.LOCATION_STATE,
    ClaimType.LOCATION_COUNTY,
    ClaimType.UTILITY_NAMED,
    ClaimType.REGION_OR_RTO_NAMED,
}

PHASE_LEVEL_CLAIM_TYPES = {
    ClaimType.PHASE_NAME_MENTION,
    ClaimType.MODELED_LOAD_MW,
    ClaimType.OPTIONAL_EXPANSION_MW,
    ClaimType.TARGET_ENERGIZATION_DATE,
    ClaimType.POWER_PATH_IDENTIFIED_FLAG,
    ClaimType.NEW_SUBSTATION_REQUIRED_FLAG,
    ClaimType.NEW_TRANSMISSION_REQUIRED_FLAG,
    ClaimType.ONSITE_GENERATION_FLAG,
}


class AutomationService:
    def __init__(self, db: Session | None = None):
        self.db = db
        self.project_repo = ProjectRepository(db) if db is not None else None
        self.phase_repo = PhaseRepository(db) if db is not None else None

    def suggest_claims(self, request: ClaimSuggestRequest) -> ClaimSuggestResponse:
        text = request.evidence_text.strip()
        normalized_text = re.sub(r"\s+", " ", text)
        lowered = normalized_text.lower()

        claims: list[dict] = []
        warnings: list[str] = []
        uncertainties: list[str] = []

        def add_claim(claim_type: ClaimType, claim_value: dict, confidence: str, claim_date: str | None = None) -> None:
            claims.append(
                {
                    "claim_type": claim_type,
                    "claim_value": claim_value,
                    "confidence": confidence,
                    **({"claim_date": claim_date} if claim_date else {}),
                }
            )

        project_name = self._extract_project_name(normalized_text)
        if project_name:
            add_claim(ClaimType.PROJECT_NAME_MENTION, {"project_name": project_name}, "medium")

        developer_name = self._extract_developer_name(normalized_text)
        if developer_name:
            add_claim(ClaimType.DEVELOPER_NAMED, {"developer_name": developer_name}, "high")

        operator_name = self._extract_operator_name(normalized_text)
        if operator_name:
            add_claim(ClaimType.OPERATOR_NAMED, {"operator_name": operator_name}, "high")

        county = self._extract_county(normalized_text)
        if county:
            add_claim(ClaimType.LOCATION_COUNTY, {"county": county}, "high")

        state = self._extract_state(lowered)
        if state:
            add_claim(ClaimType.LOCATION_STATE, {"state": state}, "high")
        else:
            uncertainties.append("No explicit state detected")

        utility = self._extract_named_match(normalized_text, UTILITY_PATTERNS)
        if utility:
            add_claim(ClaimType.UTILITY_NAMED, {"utility_name": utility}, "medium")
        else:
            uncertainties.append("No explicit utility named")

        region = self._extract_named_match(normalized_text, RTO_PATTERNS)
        if region:
            add_claim(ClaimType.REGION_OR_RTO_NAMED, {"region_name": region}, "medium")

        loads, load_warnings = self._extract_load_claims(normalized_text)
        warnings.extend(load_warnings)
        claims.extend(loads)

        phase_name = self._extract_phase_name(normalized_text)
        if phase_name:
            add_claim(ClaimType.PHASE_NAME_MENTION, {"phase_name": phase_name}, "medium")

        target_date = self._extract_target_energization_date(normalized_text)
        if target_date:
            add_claim(ClaimType.TARGET_ENERGIZATION_DATE, {"target_energization_date": target_date}, "medium")
        elif any(token in lowered for token in ["targeted for", "planned for", "expected by", "service by"]):
            warnings.append("Timing language detected but no exact energization date could be normalized")

        if any(token in lowered for token in ["substation", "new substation"]):
            add_claim(ClaimType.NEW_SUBSTATION_REQUIRED_FLAG, {"value": True}, "medium")
        if any(token in lowered for token in ["transmission line", "new transmission", "transmission upgrade"]):
            add_claim(ClaimType.NEW_TRANSMISSION_REQUIRED_FLAG, {"value": True}, "medium")
        if any(token in lowered for token in ["onsite generation", "behind-the-meter", "behind the meter", "on-site generation"]):
            add_claim(ClaimType.ONSITE_GENERATION_FLAG, {"value": True}, "medium")
        if any(token in lowered for token in ["served by", "interconnection", "substation", "transmission", "utility service"]):
            add_claim(ClaimType.POWER_PATH_IDENTIFIED_FLAG, {"value": True}, "low")

        event_summary = self._extract_timeline_disruption(normalized_text)
        if event_summary:
            add_claim(
                ClaimType.TIMELINE_DISRUPTION_SIGNAL,
                {"summary": event_summary, "disruption_type": "timeline_delay_signal"},
                "medium",
            )
            if any(token in lowered for token in ["substation", "transmission", "interconnection"]):
                add_claim(
                    ClaimType.EVENT_SUPPORT_E2,
                    {"summary": event_summary, "reason_class": "power_infrastructure_delay_signal"},
                    "medium",
                )

        if request.source_type in {SourceType.UTILITY_STATEMENT, SourceType.REGULATORY_RECORD} and region:
            add_claim(
                ClaimType.EVENT_SUPPORT_E3,
                {"summary": "Regional large-load or utility context referenced in evidence text", "reason_class": "regional_large_load_context"},
                "low",
            )

        unique_claims = self._dedupe_claims(claims)
        payload = EvidenceClaimsCreateRequest(claims=unique_claims)
        return ClaimSuggestResponse(
            claims_payload=payload,
            uncertainties=self._dedupe_strings(uncertainties),
            warnings=self._dedupe_strings(warnings),
            generator_version=GENERATOR_VERSION,
        )

    def build_intake_packet(self, request: IntakePacketRequest) -> IntakePacketResponse:
        claim_suggestion = self.suggest_claims(
            ClaimSuggestRequest(evidence_text=request.evidence_text, source_type=request.source_type)
        )
        evidence_payload = EvidenceCreateRequest(
            source_type=request.source_type,
            source_date=request.source_date,
            source_url=request.source_url,
            source_rank=1,
            title=request.title,
            extracted_text=request.evidence_text,
        )

        warnings = list(claim_suggestion.warnings)
        uncertainties = list(claim_suggestion.uncertainties)
        suggested_link_targets: list[SuggestedLinkTarget] = []

        if request.project_id is not None:
            if self.project_repo is None or self.phase_repo is None:
                warnings.append("Link suggestions unavailable because database access was not configured")
            else:
                project = self.project_repo.get_project(request.project_id)
                if project is None:
                    warnings.append("Provided project_id was not found; no link targets suggested")
                else:
                    phases = self.phase_repo.list_by_project(request.project_id)
                    suggested_link_targets, extra_warnings, extra_uncertainties = self._build_link_suggestions(
                        project=project,
                        phases=phases,
                        claims_payload=claim_suggestion.claims_payload,
                    )
                    warnings.extend(extra_warnings)
                    uncertainties.extend(extra_uncertainties)

        exact_next_steps = self._build_next_steps(has_project_id=request.project_id is not None)
        return IntakePacketResponse(
            evidence_payload=evidence_payload,
            claims_payload=claim_suggestion.claims_payload,
            suggested_link_targets=suggested_link_targets,
            exact_next_steps=exact_next_steps,
            uncertainties=self._dedupe_strings(uncertainties),
            warnings=self._dedupe_strings(warnings),
            generator_version=INTAKE_PACKET_VERSION,
        )

    def _extract_project_name(self, text: str) -> str | None:
        patterns = [
            r"^\s*([A-Z][A-Za-z0-9&'./ -]{1,120}?)\s*,\s*(?:developed by|operated by|is planned|located in|will be)\b",
            r"\b([A-Z][A-Za-z0-9&' -]+(?:Campus|Data Center|Compute Campus|Compute Hub|Foundry|Reserve|Park|Facility|Project))\b",
            r"\bProject ([A-Z][A-Za-z0-9&' -]+)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value = match.group(1).strip()
                return value if value.startswith("Project ") else value
        return None

    def _extract_developer_name(self, text: str) -> str | None:
        patterns = [
            r"developed by ([A-Z][A-Za-z0-9&.,' -]+?)(?:,|\.| is | will )",
            r"developer(?: is|:)? ([A-Z][A-Za-z0-9&.,' -]+?)(?:,|\.| and )",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return None

    def _extract_operator_name(self, text: str) -> str | None:
        patterns = [
            r"operated by ([A-Z][A-Za-z0-9&.,' -]+?)(?:,|\.| is | will )",
            r"operator(?: is|:)? ([A-Z][A-Za-z0-9&.,' -]+?)(?:,|\.| and )",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return None

    def _extract_county(self, text: str) -> str | None:
        match = re.search(r"\b([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)*) County\b", text)
        return match.group(1).strip() if match else None

    def _extract_state(self, lowered_text: str) -> str | None:
        for state_name, code in STATE_NAME_TO_CODE.items():
            if state_name in lowered_text:
                return code
        match = re.search(r"\b(AL|AZ|CA|FL|GA|IL|NC|NJ|NV|OH|PA|TN|TX|VA|WA)\b", lowered_text.upper())
        return match.group(1) if match else None

    def _extract_named_match(self, text: str, choices: list[str]) -> str | None:
        for choice in choices:
            if choice.lower() in text.lower():
                return choice
        return None

    def _extract_load_claims(self, text: str) -> tuple[list[dict], list[str]]:
        claims: list[dict] = []
        warnings: list[str] = []
        for match in re.finditer(r"(?P<prefix>.{0,40}?)(?P<mw>\d{2,4}(?:\.\d+)?)\s*MW\b", text, re.IGNORECASE):
            mw = float(match.group("mw"))
            prefix = match.group("prefix").lower()
            if any(token in prefix for token in ["up to", "potential", "ultimately", "expand to", "expansion to"]):
                claims.append(
                    {
                        "claim_type": ClaimType.OPTIONAL_EXPANSION_MW,
                        "claim_value": {"optional_expansion_mw": mw},
                        "confidence": "medium",
                    }
                )
                warnings.append(f"Load value {mw:g} MW treated as optional expansion because language is non-firm")
            else:
                claims.append(
                    {
                        "claim_type": ClaimType.MODELED_LOAD_MW,
                        "claim_value": {"modeled_primary_load_mw": mw},
                        "confidence": "medium",
                    }
                )
        if not claims and "mw" in text.lower():
            warnings.append("Load language detected but no numeric MW value could be normalized")
        return claims, warnings

    def _extract_phase_name(self, text: str) -> str | None:
        match = re.search(r"\b(Phase\s+(?:[IVX]+|\d+|[A-Z]))\b", text)
        return match.group(1).strip() if match else None

    def _extract_target_energization_date(self, text: str) -> str | None:
        patterns = [
            r"(?:targeted for|planned for|expected by|service by)\s+([A-Z][a-z]+ \d{1,2}, \d{4})",
            r"(?:targeted for|planned for|expected by|service by)\s+([A-Z][a-z]+ \d{4})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            raw = match.group(1)
            for fmt in ("%B %d, %Y", "%B %Y"):
                try:
                    parsed_dt = datetime.strptime(raw, fmt)
                except ValueError:
                    continue
                if fmt == "%B %Y":
                    return parsed_dt.date().replace(day=1).isoformat()
                return parsed_dt.date().isoformat()
        return None

    def _extract_timeline_disruption(self, text: str) -> str | None:
        disruption_terms = ["delay", "delayed", "slip", "slipped", "postponed", "deferred"]
        lowered = text.lower()
        if any(term in lowered for term in disruption_terms):
            sentences = re.split(r"(?<=[.!?])\s+", text)
            for sentence in sentences:
                if any(term in sentence.lower() for term in disruption_terms):
                    return sentence.strip()
            return "Timeline disruption language detected in evidence text"
        return None

    def _dedupe_claims(self, claims: list[dict]) -> list[dict]:
        seen: set[tuple[str, str]] = set()
        deduped: list[dict] = []
        for claim in claims:
            key = (str(claim["claim_type"]), str(claim["claim_value"]))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(claim)
        return deduped

    def _dedupe_strings(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            output.append(item)
        return output

    def _build_link_suggestions(
        self,
        *,
        project: Project,
        phases: list,
        claims_payload: EvidenceClaimsCreateRequest,
    ) -> tuple[list[SuggestedLinkTarget], list[str], list[str]]:
        suggestions: list[SuggestedLinkTarget] = []
        warnings: list[str] = []
        uncertainties: list[str] = []

        single_phase = phases[0] if len(phases) == 1 else None

        for claim in claims_payload.claims:
            if claim.claim_type in PROJECT_LEVEL_CLAIM_TYPES:
                suggestions.append(
                    SuggestedLinkTarget(
                        claim_type=claim.claim_type,
                        suggested_entity_type="project",
                        suggested_entity_id=project.id,
                        suggested_entity_label=project.canonical_name,
                        reason="project_id was provided and this is a project-level claim type",
                    )
                )
                continue

            if claim.claim_type in PHASE_LEVEL_CLAIM_TYPES:
                matched_phase = None
                if claim.claim_type == ClaimType.PHASE_NAME_MENTION:
                    phase_name = claim.claim_value.phase_name.strip().lower()
                    matched_phase = next(
                        (row.phase for row in phases if row.phase.phase_name.strip().lower() == phase_name),
                        None,
                    )
                    if matched_phase is None:
                        uncertainties.append(
                            f"Phase claim '{claim.claim_value.phase_name}' did not match an existing phase for the provided project"
                        )
                elif single_phase is not None:
                    matched_phase = single_phase.phase

                if matched_phase is not None:
                    suggestions.append(
                        SuggestedLinkTarget(
                            claim_type=claim.claim_type,
                            suggested_entity_type="phase",
                            suggested_entity_id=matched_phase.id,
                            suggested_entity_label=matched_phase.phase_name,
                            reason="phase match is explicit" if claim.claim_type == ClaimType.PHASE_NAME_MENTION else "project has exactly one phase",
                        )
                    )
                else:
                    warnings.append(
                        f"No deterministic phase link target suggested for claim type '{claim.claim_type.value}'"
                    )

        return suggestions, warnings, uncertainties

    def _build_next_steps(self, *, has_project_id: bool) -> list[str]:
        steps = [
            "1. Review evidence_payload and adjust source metadata if needed.",
            "2. POST evidence_payload to /evidence and save the returned evidence_id.",
            "3. POST claims_payload to /evidence/{evidence_id}/claims.",
        ]
        if has_project_id:
            steps.extend(
                [
                    "4. Use suggested_link_targets to link safe project- or phase-level claims via /claims/{claim_id}/link.",
                    "5. Review linked claims manually via /claims/{claim_id}/review before any acceptance.",
                ]
            )
        else:
            steps.extend(
                [
                    "4. Manually identify the correct project and phase before linking any claims.",
                    "5. Link claims via /claims/{claim_id}/link only after confirming the correct target.",
                ]
            )
        steps.append("6. Accept only reviewed, non-contradictory claims via /claims/{claim_id}/accept when appropriate.")
        return steps
