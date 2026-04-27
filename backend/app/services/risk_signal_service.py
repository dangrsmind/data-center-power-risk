from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.enums import ClaimReviewStatus, ClaimType
from app.models.project import Project
from app.repositories import PhaseRepository, ProjectRepository, RiskSignalRepository
from app.schemas.analyst import ProjectRiskSignalResponse, RiskSignalEvidenceSummary


RISK_SIGNAL_METHOD = "deterministic_evidence_backed_v1"
POWER_PATH_CLAIM_TYPES = {
    ClaimType.POWER_PATH_IDENTIFIED_FLAG,
    ClaimType.NEW_SUBSTATION_REQUIRED_FLAG,
    ClaimType.NEW_TRANSMISSION_REQUIRED_FLAG,
}
UNRESOLVED_STATUSES = {
    ClaimReviewStatus.UNREVIEWED,
    ClaimReviewStatus.LINKED,
    ClaimReviewStatus.ACCEPTED_CANDIDATE,
    ClaimReviewStatus.AMBIGUOUS,
    ClaimReviewStatus.NEEDS_MORE_REVIEW,
}


def _json_number(value: Decimal | int | float | None) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        normalized = value.normalize()
        if normalized == normalized.to_integral():
            return int(normalized)
        return float(value)
    return value


@dataclass
class ProjectRiskInputs:
    modeled_load_mw: float | None
    optional_expansion_mw: float | None
    has_target_energization_date: bool
    target_energization_date: date | None
    has_accepted_utility: bool
    has_accepted_region: bool
    has_power_path_claims: bool
    evidence_count: int
    accepted_claim_count: int
    unresolved_claim_count: int


class RiskSignalService:
    def __init__(self, db: Session):
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.phase_repo = PhaseRepository(db)
        self.risk_repo = RiskSignalRepository(db)

    def get_project_risk_signal(self, project_id: uuid.UUID) -> ProjectRiskSignalResponse:
        project = self.project_repo.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        inputs = self._build_inputs(project)
        score, drivers, missing_fields = self._score(inputs)
        tier = self._tier(score)
        signal = self._signal_name(inputs, score)

        return ProjectRiskSignalResponse(
            project_id=project.id,
            risk_signal=signal,
            risk_signal_score=round(score, 3),
            risk_signal_tier=tier,
            drivers=drivers,
            missing_fields=missing_fields,
            evidence_summary=RiskSignalEvidenceSummary(
                evidence_count=inputs.evidence_count,
                accepted_claim_count=inputs.accepted_claim_count,
                unresolved_claim_count=inputs.unresolved_claim_count,
            ),
            method=RISK_SIGNAL_METHOD,
        )

    def _build_inputs(self, project: Project) -> ProjectRiskInputs:
        phase_rows = self.phase_repo.list_by_project(project.id)
        phase_ids = [row.phase.id for row in phase_rows]
        claims = self.risk_repo.list_project_scope_claims(project.id, phase_ids)
        provenance_rows = self.risk_repo.list_project_scope_provenance(project.id, phase_ids)
        evidence_count = self.risk_repo.count_project_scope_evidence(project.id, phase_ids)

        modeled_load_mw = sum(
            float(value)
            for value in (_json_number(row.modeled_primary_load_mw) for row in phase_rows)
            if isinstance(value, (int, float))
        ) or None
        optional_expansion_mw = sum(
            float(value)
            for value in (_json_number(row.optional_expansion_mw) for row in phase_rows)
            if isinstance(value, (int, float))
        ) or None

        phase_target_dates = [row.phase.target_energization_date for row in phase_rows if row.phase.target_energization_date is not None]
        target_energization_date = min(phase_target_dates) if phase_target_dates else None

        provenance_field_names = {row.field_name for row in provenance_rows}
        has_accepted_utility = project.utility_id is not None and "utility_id" in provenance_field_names
        has_accepted_region = project.region_id is not None and "region_id" in provenance_field_names
        has_target_energization_date = target_energization_date is not None and "target_energization_date" in provenance_field_names
        has_power_path_claims = any(
            claim.claim_type in POWER_PATH_CLAIM_TYPES and claim.review_status != ClaimReviewStatus.REJECTED
            for claim in claims
        )

        accepted_claim_count = sum(1 for claim in claims if claim.review_status == ClaimReviewStatus.ACCEPTED)
        unresolved_claim_count = sum(1 for claim in claims if claim.review_status in UNRESOLVED_STATUSES)

        return ProjectRiskInputs(
            modeled_load_mw=modeled_load_mw,
            optional_expansion_mw=optional_expansion_mw,
            has_target_energization_date=has_target_energization_date,
            target_energization_date=target_energization_date,
            has_accepted_utility=has_accepted_utility,
            has_accepted_region=has_accepted_region,
            has_power_path_claims=has_power_path_claims,
            evidence_count=evidence_count,
            accepted_claim_count=accepted_claim_count,
            unresolved_claim_count=unresolved_claim_count,
        )

    def _score(self, inputs: ProjectRiskInputs) -> tuple[float, list[str], list[str]]:
        score = 0.0
        drivers: list[str] = []
        missing_fields: list[str] = []

        if inputs.modeled_load_mw is None:
            score += 0.10
            missing_fields.append("modeled_load_mw")
            drivers.append("Accepted modeled load is missing")
        elif inputs.modeled_load_mw >= 800:
            score += 0.25
            drivers.append(f"Accepted modeled load is {int(inputs.modeled_load_mw)} MW")
        elif inputs.modeled_load_mw >= 500:
            score += 0.18
            drivers.append(f"Accepted modeled load is {int(inputs.modeled_load_mw)} MW")
        elif inputs.modeled_load_mw >= 300:
            score += 0.10
            drivers.append(f"Accepted modeled load is {int(inputs.modeled_load_mw)} MW")

        if inputs.optional_expansion_mw:
            score += 0.05
            drivers.append(f"Accepted optional expansion adds {int(inputs.optional_expansion_mw)} MW")

        if not inputs.has_accepted_utility:
            score += 0.20
            missing_fields.append("utility_named")
            drivers.append("No accepted utility identified")

        if not inputs.has_accepted_region:
            score += 0.10
            missing_fields.append("region_or_rto_named")
            drivers.append("No accepted region or RTO identified")

        if not inputs.has_target_energization_date:
            score += 0.15
            missing_fields.append("target_energization_date")
            drivers.append("No accepted target energization date")

        if not inputs.has_power_path_claims:
            score += 0.20
            missing_fields.append("power_path_support")
            drivers.append("Accepted or active power-path claims are missing")

        if inputs.target_energization_date and inputs.modeled_load_mw:
            months_to_target = self._months_to_target(inputs.target_energization_date)
            if months_to_target is not None and months_to_target <= 24:
                if inputs.modeled_load_mw >= 800:
                    score += 0.20
                    drivers.append("Large accepted load is paired with a near-term energization target")
                elif inputs.modeled_load_mw >= 500:
                    score += 0.15
                    drivers.append("Accepted load and timing create moderate delivery pressure")
                elif inputs.modeled_load_mw >= 300:
                    score += 0.10
                    drivers.append("Accepted load and timing create some delivery pressure")

        if inputs.evidence_count <= 1:
            score += 0.15
            drivers.append(f"Only {inputs.evidence_count} linked evidence record is available" if inputs.evidence_count == 1 else "No linked evidence records are available")
        elif inputs.evidence_count == 2:
            score += 0.08
            drivers.append("Evidence base is still thin")

        if inputs.unresolved_claim_count > 0:
            unresolved_weight = min(0.15, inputs.unresolved_claim_count * 0.04)
            score += unresolved_weight
            drivers.append(f"{inputs.unresolved_claim_count} unresolved or ambiguous claims remain")

        score = max(0.0, min(1.0, score))
        return score, self._dedupe(drivers), self._dedupe(missing_fields)

    def _signal_name(self, inputs: ProjectRiskInputs, score: float) -> str:
        if (not inputs.has_accepted_utility or not inputs.has_power_path_claims) and score >= 0.55:
            return "power_path_underresolved"
        if (
            inputs.modeled_load_mw is not None
            and inputs.modeled_load_mw >= 500
            and inputs.target_energization_date is not None
            and self._months_to_target(inputs.target_energization_date) is not None
            and self._months_to_target(inputs.target_energization_date) <= 24
        ):
            return "capacity_timing_tension"
        if score >= 0.35 and (inputs.has_accepted_region or inputs.has_accepted_utility or inputs.has_power_path_claims):
            return "power_path_partially_resolved"
        return "power_path_more_resolved"

    def _tier(self, score: float) -> str:
        if score >= 0.55:
            return "high"
        if score >= 0.25:
            return "moderate"
        return "low"

    def _months_to_target(self, target: date) -> int | None:
        today = date.today()
        return (target.year - today.year) * 12 + (target.month - today.month)

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result
