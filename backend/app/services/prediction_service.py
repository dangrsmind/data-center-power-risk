from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.prediction import ProjectPrediction
from app.models.project import Project
from app.schemas.analyst import PredictionDriver, ProjectPredictionResponse


MODEL_NAME = "baseline_power_delay"
MODEL_VERSION = "baseline_power_delay_v0_2"
PREDICTION_TYPE = "power_delivery_delay"


@dataclass
class PredictionInputs:
    project: Project
    load_mw: float | None
    load_bucket: str | None
    utility: str | None
    iso_region: str | None
    expected_online_date: date | None
    source_url: str | None
    source_title: str | None
    source_type: str | None
    evidence_excerpt: str | None


class PredictionService:
    def __init__(self, db: Session):
        self.db = db

    def get_project_prediction(self, project_id: uuid.UUID) -> ProjectPredictionResponse:
        project = self.db.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        stored = self.get_stored_prediction(project_id)
        if stored is not None:
            return self._response_from_stored(stored)
        return self.compute_project_prediction(project)

    def get_stored_prediction(self, project_id: uuid.UUID) -> ProjectPrediction | None:
        return self.db.scalar(
            select(ProjectPrediction)
            .where(
                ProjectPrediction.project_id == project_id,
                ProjectPrediction.model_name == MODEL_NAME,
                ProjectPrediction.model_version == MODEL_VERSION,
            )
            .order_by(ProjectPrediction.created_at.desc())
        )

    def upsert_project_prediction(self, project: Project) -> tuple[ProjectPrediction, str]:
        response = self.compute_project_prediction(project)
        stored = self.get_stored_prediction(project.id)
        drivers_json = [driver.model_dump() for driver in response.drivers]

        if stored is None:
            stored = ProjectPrediction(
                project_id=project.id,
                model_name=response.model_name,
                model_version=response.model_version,
                p_delay_6mo=response.p_delay_6mo,
                p_delay_12mo=response.p_delay_12mo,
                p_delay_18mo=response.p_delay_18mo,
                risk_tier=response.risk_tier,
                confidence=response.confidence,
                drivers_json=drivers_json,
            )
            self.db.add(stored)
            self.db.flush()
            return stored, "created"

        changed = False
        for attr, value in [
            ("p_delay_6mo", response.p_delay_6mo),
            ("p_delay_12mo", response.p_delay_12mo),
            ("p_delay_18mo", response.p_delay_18mo),
            ("risk_tier", response.risk_tier),
            ("confidence", response.confidence),
            ("drivers_json", drivers_json),
        ]:
            if getattr(stored, attr) != value:
                setattr(stored, attr, value)
                changed = True

        if changed:
            self.db.flush()
            return stored, "updated"
        return stored, "skipped"

    def compute_project_prediction(self, project: Project) -> ProjectPredictionResponse:
        inputs = self._build_inputs(project)
        score, drivers, missing_inputs = self._score(inputs)
        p6 = round(self._clamp(score * 0.58), 3)
        p12 = round(self._clamp(score * 0.82), 3)
        p18 = round(self._clamp(score), 3)
        p6, p12, p18 = sorted([p6, p12, p18])

        return ProjectPredictionResponse(
            model_name=MODEL_NAME,
            model_version=MODEL_VERSION,
            prediction_type=PREDICTION_TYPE,
            p_delay_6mo=p6,
            p_delay_12mo=p12,
            p_delay_18mo=p18,
            risk_tier=self._tier(p18),
            confidence=self._confidence(missing_inputs),
            drivers=drivers,
            missing_inputs=missing_inputs,
            method_note="This is a deterministic demo baseline using project fields and curated metadata; it is not a trained ML model.",
        )

    def _build_inputs(self, project: Project) -> PredictionInputs:
        metadata = project.candidate_metadata_json if isinstance(project.candidate_metadata_json, dict) else {}
        return PredictionInputs(
            project=project,
            load_mw=self._metadata_float(metadata, "load_mw"),
            load_bucket=self._metadata_string(metadata, "load_bucket"),
            utility=self._metadata_string(metadata, "utility"),
            iso_region=self._metadata_string(metadata, "iso_region"),
            expected_online_date=self._metadata_date(metadata, "expected_online_date"),
            source_url=self._metadata_string(metadata, "source_url"),
            source_title=self._metadata_string(metadata, "source_title"),
            source_type=self._metadata_string(metadata, "source_type"),
            evidence_excerpt=self._metadata_string(metadata, "evidence_excerpt"),
        )

    def _score(self, inputs: PredictionInputs) -> tuple[float, list[PredictionDriver], list[str]]:
        score = 0.14
        drivers = [
            self._driver(
                "Deterministic demo prior",
                "increases",
                0.14,
                "Fixed transparent prior for the reproducible demo path.",
            )
        ]
        missing_inputs: list[str] = []

        if inputs.load_mw is None:
            missing_inputs.append("load_mw")
            drivers.append(self._missing_driver("Load size unknown"))
        elif inputs.load_mw >= 800:
            score += 0.24
            drivers.append(self._driver("Large load size", "increases", 0.24, f"Curated load is {inputs.load_mw:g} MW."))
        elif inputs.load_mw >= 300:
            score += 0.14
            drivers.append(self._driver("Moderate load size", "increases", 0.14, f"Curated load is {inputs.load_mw:g} MW."))
        elif inputs.load_mw > 0:
            score += 0.06
            drivers.append(self._driver("Known load size", "increases", 0.06, f"Curated load is {inputs.load_mw:g} MW."))

        if not inputs.load_bucket:
            missing_inputs.append("load_bucket")
        elif "900" in inputs.load_bucket or "800" in inputs.load_bucket or "large" in inputs.load_bucket.lower():
            score += 0.04
            drivers.append(self._driver("Large load bucket", "increases", 0.04, f"Load bucket is {inputs.load_bucket}."))

        if not inputs.utility:
            missing_inputs.append("utility")
            drivers.append(self._missing_driver("Utility not confirmed"))
        else:
            drivers.append(self._driver("Utility confirmed", "decreases", -0.03, f"Utility is {inputs.utility}."))
            score -= 0.03

        if not inputs.iso_region:
            missing_inputs.append("iso_region")
            drivers.append(self._missing_driver("ISO/RTO region not confirmed"))
        else:
            drivers.append(self._driver("ISO/RTO region available", "decreases", -0.02, f"Region is {inputs.iso_region}."))
            score -= 0.02

        lifecycle_state = self._enum_value(inputs.project.lifecycle_state)
        if lifecycle_state == "candidate_unverified":
            score += 0.08
            drivers.append(self._driver("Lifecycle state is candidate_unverified", "increases", 0.08, "Early candidate records have less resolved power-path evidence."))
        elif lifecycle_state in {"monitoring_ready", "production_ready"}:
            score -= 0.05
            drivers.append(self._driver("Lifecycle state is mature", "decreases", -0.05, f"Lifecycle state is {lifecycle_state}."))

        coordinate_status = inputs.project.coordinate_status
        if not coordinate_status:
            missing_inputs.append("coordinate_status")
            drivers.append(self._missing_driver("Coordinate status unknown"))
        elif coordinate_status == "verified":
            score -= 0.03
            drivers.append(self._driver("Coordinate status is verified", "decreases", -0.03, "Verified coordinates reduce siting uncertainty."))
        elif coordinate_status == "unverified":
            score += 0.04
            drivers.append(self._driver("Coordinate status is unverified", "increases", 0.04, "Unverified coordinates keep site-level power-path uncertainty open."))
        elif coordinate_status in {"missing", "needs_review"}:
            score += 0.06
            drivers.append(self._driver(f"Coordinate status is {coordinate_status}", "increases", 0.06, "Missing or review-needed coordinates reduce demo confidence."))

        coordinate_precision = inputs.project.coordinate_precision
        if not coordinate_precision:
            missing_inputs.append("coordinate_precision")
            drivers.append(self._missing_driver("Coordinate precision unknown"))
        elif coordinate_precision in {"approximate", "county", "city"}:
            score += 0.03
            drivers.append(self._driver("Only approximate coordinate precision", "increases", 0.03, f"Coordinate precision is {coordinate_precision}."))
        elif coordinate_precision == "exact_site":
            score -= 0.02
            drivers.append(self._driver("Exact site coordinate precision", "decreases", -0.02, "Exact site coordinates reduce uncertainty."))

        if inputs.expected_online_date is None:
            missing_inputs.append("expected_online_date")
            drivers.append(self._missing_driver("No expected online date available"))
        else:
            months = self._months_to_target(inputs.expected_online_date)
            if months is not None and months <= 18:
                score += 0.10
                drivers.append(
                    self._driver(
                        "Near-term expected online date",
                        "increases",
                        0.10,
                        f"Expected online date is {inputs.expected_online_date.isoformat()}.",
                    )
                )

        if not inputs.source_url:
            missing_inputs.append("source_url")
            drivers.append(self._missing_driver("No source URL available"))
        if not inputs.evidence_excerpt:
            missing_inputs.append("evidence_excerpt")
            drivers.append(self._missing_driver("No source evidence excerpt available"))
        elif len(inputs.evidence_excerpt) >= 40:
            score -= 0.02
            drivers.append(self._driver("Source evidence excerpt available", "decreases", -0.02, "Curated source excerpt supports the record."))

        return self._clamp(score), drivers, missing_inputs

    def _response_from_stored(self, stored: ProjectPrediction) -> ProjectPredictionResponse:
        raw_drivers = stored.drivers_json if isinstance(stored.drivers_json, list) else []
        drivers = [PredictionDriver(**driver) for driver in raw_drivers if isinstance(driver, dict)]
        if not drivers:
            drivers = [self._missing_driver("Stored prediction has no driver details")]
        return ProjectPredictionResponse(
            model_name=stored.model_name,
            model_version=stored.model_version,
            prediction_type=PREDICTION_TYPE,
            p_delay_6mo=stored.p_delay_6mo,
            p_delay_12mo=stored.p_delay_12mo,
            p_delay_18mo=stored.p_delay_18mo,
            risk_tier=stored.risk_tier,
            confidence=stored.confidence,
            drivers=drivers,
            missing_inputs=[],
            method_note="Stored deterministic demo prediction.",
        )

    def _metadata_string(self, metadata: dict[str, Any], key: str) -> str | None:
        value = metadata.get(key)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _metadata_float(self, metadata: dict[str, Any], key: str) -> float | None:
        value = metadata.get(key)
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _metadata_date(self, metadata: dict[str, Any], key: str) -> date | None:
        value = self._metadata_string(metadata, key)
        if value is None:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _months_to_target(self, target: date) -> int:
        today = date.today()
        return (target.year - today.year) * 12 + (target.month - today.month)

    def _confidence(self, missing_inputs: list[str]) -> str:
        if len(missing_inputs) >= 5:
            return "low"
        if len(missing_inputs) <= 2:
            return "high"
        return "medium"

    def _tier(self, p_delay_18mo: float) -> str:
        if p_delay_18mo >= 0.55:
            return "high"
        if p_delay_18mo >= 0.25:
            return "moderate"
        return "low"

    def _driver(self, driver: str, direction: str, weight: float, evidence: str) -> PredictionDriver:
        return PredictionDriver(driver=driver, direction=direction, weight=round(weight, 3), evidence=evidence)

    def _missing_driver(self, driver: str) -> PredictionDriver:
        return self._driver(driver, "unknown", 0.0, "Missing input lowers confidence but does not increase risk by itself.")

    def _clamp(self, value: float) -> float:
        return max(0.01, min(0.95, value))

    def _enum_value(self, value: Any) -> str:
        return getattr(value, "value", str(value))
