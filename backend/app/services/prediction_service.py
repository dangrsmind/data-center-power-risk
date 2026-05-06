from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.enums import ClaimEntityType, ClaimReviewStatus, ClaimType, ReviewerStatus
from app.models.enrichment import ProjectEnrichmentSnapshot
from app.models.evidence import Claim, Evidence
from app.models.project import Phase, Project
from app.schemas.analyst import PredictionDriver, ProjectPredictionResponse
from app.services.risk_signal_service import RiskSignalService


MODEL_VERSION = "baseline_power_delay_v0"
PREDICTION_TYPE = "power_delivery_delay"
POWER_PATH_CLAIM_TYPES = {
    ClaimType.POWER_PATH_IDENTIFIED_FLAG,
    ClaimType.NEW_SUBSTATION_REQUIRED_FLAG,
    ClaimType.NEW_TRANSMISSION_REQUIRED_FLAG,
}


@dataclass
class AcceptedInputs:
    project: Project
    accepted_claims: list[Claim]
    phase_ids: list[uuid.UUID]
    modeled_load_mw: float | None
    target_energization_date: date | None
    has_accepted_utility: bool
    has_accepted_region: bool
    has_power_path_support: bool
    has_substation_or_interconnection_detail: bool
    has_new_substation_or_transmission_required: bool
    has_regional_large_load_stress: bool
    reviewed_evidence_count: int
    evidence_count: int
    enrichment: ProjectEnrichmentSnapshot | None


class PredictionService:
    def __init__(self, db: Session):
        self.db = db

    def get_project_prediction(self, project_id: uuid.UUID) -> ProjectPredictionResponse:
        project = self.db.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        inputs = self._build_inputs(project)
        risk_signal = RiskSignalService(self.db).get_project_risk_signal(project_id)
        score, drivers, missing_inputs = self._score(inputs, risk_signal.risk_signal_tier, risk_signal.risk_signal_score)
        p6 = self._clamp(score * 0.55)
        p12 = self._clamp(score * 0.80)
        p18 = self._clamp(score)

        return ProjectPredictionResponse(
            model_version=MODEL_VERSION,
            prediction_type=PREDICTION_TYPE,
            p_delay_6mo=round(p6, 3),
            p_delay_12mo=round(p12, 3),
            p_delay_18mo=round(p18, 3),
            risk_tier=self._tier(p18),
            drivers=drivers,
            missing_inputs=missing_inputs,
            confidence=self._confidence(inputs, missing_inputs),
        )

    def _build_inputs(self, project: Project) -> AcceptedInputs:
        phases = list(self.db.execute(select(Phase).where(Phase.project_id == project.id)).scalars().all())
        phase_ids = [phase.id for phase in phases]
        accepted_claims = self._accepted_project_claims(project.id, phase_ids)
        evidence_ids = {claim.evidence_id for claim in accepted_claims if claim.evidence_id is not None}
        evidence_rows = []
        if evidence_ids:
            evidence_rows = list(self.db.execute(select(Evidence).where(Evidence.id.in_(evidence_ids))).scalars().all())

        modeled_load_mw = self._accepted_modeled_load(accepted_claims)
        target_energization_date = self._accepted_target_date(accepted_claims)
        has_accepted_utility = any(claim.claim_type == ClaimType.UTILITY_NAMED for claim in accepted_claims)
        has_accepted_region = any(claim.claim_type == ClaimType.REGION_OR_RTO_NAMED for claim in accepted_claims)
        has_power_path_support = any(
            claim.claim_type == ClaimType.POWER_PATH_IDENTIFIED_FLAG and self._claim_bool(claim) is True
            for claim in accepted_claims
        )
        has_substation_or_interconnection_detail = any(
            claim.claim_type in POWER_PATH_CLAIM_TYPES and self._claim_bool(claim) is True
            for claim in accepted_claims
        )
        has_new_substation_or_transmission_required = any(
            claim.claim_type in {ClaimType.NEW_SUBSTATION_REQUIRED_FLAG, ClaimType.NEW_TRANSMISSION_REQUIRED_FLAG}
            and self._claim_bool(claim) is True
            for claim in accepted_claims
        )
        has_regional_large_load_stress = any(
            claim.claim_type == ClaimType.EVENT_SUPPORT_E3
            or (
                claim.claim_type == ClaimType.TIMELINE_DISRUPTION_SIGNAL
                and "large_load" in str(claim.claim_value_json or {}).lower()
            )
            for claim in accepted_claims
        )
        enrichment = self.db.scalar(
            select(ProjectEnrichmentSnapshot)
            .where(ProjectEnrichmentSnapshot.project_id == project.id)
            .order_by(ProjectEnrichmentSnapshot.computed_at.desc())
        )

        return AcceptedInputs(
            project=project,
            accepted_claims=accepted_claims,
            phase_ids=phase_ids,
            modeled_load_mw=modeled_load_mw,
            target_energization_date=target_energization_date,
            has_accepted_utility=has_accepted_utility,
            has_accepted_region=has_accepted_region,
            has_power_path_support=has_power_path_support,
            has_substation_or_interconnection_detail=has_substation_or_interconnection_detail,
            has_new_substation_or_transmission_required=has_new_substation_or_transmission_required,
            has_regional_large_load_stress=has_regional_large_load_stress,
            reviewed_evidence_count=sum(1 for evidence in evidence_rows if evidence.reviewer_status == ReviewerStatus.REVIEWED),
            evidence_count=len(evidence_rows),
            enrichment=enrichment,
        )

    def _accepted_project_claims(self, project_id: uuid.UUID, phase_ids: list[uuid.UUID]) -> list[Claim]:
        filters = [and_(Claim.entity_type == ClaimEntityType.PROJECT, Claim.entity_id == project_id)]
        if phase_ids:
            filters.append(and_(Claim.entity_type == ClaimEntityType.PHASE, Claim.entity_id.in_(phase_ids)))
        stmt = (
            select(Claim)
            .where(or_(*filters), Claim.review_status == ClaimReviewStatus.ACCEPTED)
            .order_by(Claim.created_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def _score(self, inputs: AcceptedInputs, risk_tier: str, risk_score: float) -> tuple[float, list[PredictionDriver], list[str]]:
        score = 0.12
        drivers = [
            PredictionDriver(
                driver="baseline prior",
                direction="unknown",
                weight=0.12,
                evidence="Fixed prior for an evidence-backed deterministic baseline; not learned from data.",
            )
        ]
        missing_inputs = self._missing_inputs(inputs)

        if inputs.modeled_load_mw is not None:
            if inputs.modeled_load_mw > 800:
                score += 0.28
                drivers.append(self._driver("accepted load > 800 MW", "increases", 0.28, f"Accepted modeled load is {inputs.modeled_load_mw:g} MW."))
            elif inputs.modeled_load_mw > 300:
                score += 0.16
                drivers.append(self._driver("accepted load > 300 MW", "increases", 0.16, f"Accepted modeled load is {inputs.modeled_load_mw:g} MW."))

        if inputs.target_energization_date is not None:
            months = self._months_to_target(inputs.target_energization_date)
            if months is not None and months < 24 and not inputs.has_power_path_support:
                score += 0.18
                drivers.append(
                    self._driver(
                        "near-term target without accepted power-path evidence",
                        "increases",
                        0.18,
                        f"Accepted target energization date is {inputs.target_energization_date.isoformat()} ({months} months away).",
                    )
                )

        if inputs.has_new_substation_or_transmission_required:
            score += 0.12
            drivers.append(self._driver("accepted substation/transmission requirement", "increases", 0.12, "Accepted evidence indicates new substation or transmission work."))

        if inputs.has_regional_large_load_stress:
            score += 0.10
            drivers.append(self._driver("regional large-load stress evidence", "increases", 0.10, "Accepted E3 or large-load stress evidence is linked to the project."))

        if risk_tier == "high":
            score += 0.12
            drivers.append(self._driver("risk signal tier is high", "increases", 0.12, f"Evidence Signal returned {risk_tier} at score {risk_score:.3f}."))
        elif risk_tier == "moderate":
            score += 0.06
            drivers.append(self._driver("risk signal tier is moderate", "increases", 0.06, f"Evidence Signal returned {risk_tier} at score {risk_score:.3f}."))

        if inputs.has_power_path_support:
            score -= 0.08
            drivers.append(self._driver("accepted power-path support", "decreases", -0.08, "Accepted power-path evidence indicates an identified path."))

        if inputs.has_substation_or_interconnection_detail:
            score -= 0.04
            drivers.append(self._driver("accepted substation/interconnection detail", "decreases", -0.04, "Accepted power infrastructure detail reduces uncertainty."))

        if inputs.enrichment and inputs.enrichment.retail_utility_name and not inputs.has_accepted_utility:
            drivers.append(
                self._driver(
                    "enrichment utility context available",
                    "unknown",
                    0.0,
                    f"Enrichment suggests {inputs.enrichment.retail_utility_name}; not treated as accepted utility evidence.",
                )
            )

        for missing in missing_inputs:
            drivers.append(self._driver(f"missing {missing}", "unknown", 0.0, "Missing input lowers confidence but does not increase risk by itself."))

        return self._clamp(score), drivers, missing_inputs

    def _missing_inputs(self, inputs: AcceptedInputs) -> list[str]:
        missing = []
        if inputs.modeled_load_mw is None:
            missing.append("modeled_load_mw")
        if not inputs.has_accepted_utility:
            missing.append("utility_named")
        if not inputs.has_accepted_region:
            missing.append("region_or_rto_named")
        if inputs.target_energization_date is None:
            missing.append("target_energization_date")
        if not inputs.has_power_path_support:
            missing.append("power_path_support")
        return missing

    def _confidence(self, inputs: AcceptedInputs, missing_inputs: list[str]) -> str:
        if len(missing_inputs) >= 3 or inputs.reviewed_evidence_count == 0:
            return "low"
        if len(missing_inputs) <= 1 and inputs.reviewed_evidence_count >= 2 and len(inputs.accepted_claims) >= 4:
            return "high"
        return "medium"

    def _accepted_modeled_load(self, claims: list[Claim]) -> float | None:
        values = []
        for claim in claims:
            if claim.claim_type != ClaimType.MODELED_LOAD_MW:
                continue
            raw = (claim.claim_value_json or {}).get("modeled_primary_load_mw")
            if isinstance(raw, int | float):
                values.append(float(raw))
        return sum(values) if values else None

    def _accepted_target_date(self, claims: list[Claim]) -> date | None:
        dates = []
        for claim in claims:
            if claim.claim_type != ClaimType.TARGET_ENERGIZATION_DATE:
                continue
            raw = (claim.claim_value_json or {}).get("target_energization_date")
            if isinstance(raw, date):
                dates.append(raw)
            elif isinstance(raw, str):
                try:
                    dates.append(date.fromisoformat(raw))
                except ValueError:
                    continue
        return min(dates) if dates else None

    def _claim_bool(self, claim: Claim) -> bool | None:
        raw = (claim.claim_value_json or {}).get("value")
        return raw if isinstance(raw, bool) else None

    def _months_to_target(self, target: date) -> int:
        today = date.today()
        return (target.year - today.year) * 12 + (target.month - today.month)

    def _tier(self, p_delay_18mo: float) -> str:
        if p_delay_18mo >= 0.55:
            return "high"
        if p_delay_18mo >= 0.25:
            return "moderate"
        return "low"

    def _driver(self, driver: str, direction: str, weight: float, evidence: str) -> PredictionDriver:
        return PredictionDriver(driver=driver, direction=direction, weight=round(weight, 3), evidence=evidence)

    def _clamp(self, value: float) -> float:
        return max(0.01, min(0.95, value))
