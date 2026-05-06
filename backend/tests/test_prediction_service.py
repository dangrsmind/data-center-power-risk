from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.enums import (  # noqa: E402
    ClaimEntityType,
    ClaimReviewStatus,
    ClaimType,
    LifecycleState,
    LoadKind,
    ReviewerStatus,
    SourceType,
)
from app.models import Base  # noqa: E402
from app.models.evidence import Claim, Evidence, FieldProvenance  # noqa: E402
from app.models.project import Phase, PhaseLoad, Project  # noqa: E402
from app.models.reference import Region, Utility  # noqa: E402
from app.services.prediction_service import PredictionService  # noqa: E402


class PredictionServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)
        Base.metadata.create_all(bind=self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _project_with_phase(self, db, name: str) -> tuple[Project, Phase]:
        project = Project(
            canonical_name=name,
            state="VA",
            county="Caroline",
            lifecycle_state=LifecycleState.CANDIDATE_UNVERIFIED,
        )
        db.add(project)
        db.flush()
        phase = Phase(project_id=project.id, phase_name="Phase I", phase_order=1)
        db.add(phase)
        db.flush()
        return project, phase

    def _accepted_claim(
        self,
        db,
        *,
        evidence: Evidence,
        entity_type: ClaimEntityType,
        entity_id,
        claim_type: ClaimType,
        claim_value_json: dict,
        field_name: str | None = None,
    ) -> Claim:
        claim = Claim(
            evidence_id=evidence.id,
            entity_type=entity_type,
            entity_id=entity_id,
            claim_type=claim_type,
            claim_value_json=claim_value_json,
            confidence="high",
            review_status=ClaimReviewStatus.ACCEPTED,
        )
        db.add(claim)
        db.flush()
        if field_name:
            db.add(
                FieldProvenance(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    field_name=field_name,
                    evidence_id=evidence.id,
                    claim_id=claim.id,
                )
            )
        return claim

    def _reviewed_evidence(self, db, title: str) -> Evidence:
        evidence = Evidence(
            source_type=SourceType.DEVELOPER_STATEMENT,
            title=title,
            extracted_text=title,
            reviewer_status=ReviewerStatus.REVIEWED,
        )
        db.add(evidence)
        db.flush()
        return evidence

    def _target_next_year(self) -> date:
        today = date.today()
        return date(today.year + 1, today.month, 1)

    def test_missing_inputs_lower_confidence_without_forcing_high_risk(self) -> None:
        db = self.SessionLocal()
        try:
            project, _ = self._project_with_phase(db, "Thin Prediction Campus")
            db.commit()

            response = PredictionService(db).get_project_prediction(project.id)

            self.assertEqual(response.model_version, "baseline_power_delay_v0")
            self.assertEqual(response.prediction_type, "power_delivery_delay")
            self.assertEqual(response.confidence, "low")
            self.assertIn("modeled_load_mw", response.missing_inputs)
            self.assertIn("utility_named", response.missing_inputs)
            self.assertLess(response.p_delay_18mo, 0.55)
            self.assertTrue(any(driver.weight == 0 for driver in response.drivers if driver.direction == "unknown"))
        finally:
            db.close()

    def test_only_accepted_load_claims_affect_prediction(self) -> None:
        db = self.SessionLocal()
        try:
            project, phase = self._project_with_phase(db, "Accepted Claims Only Campus")
            evidence = self._reviewed_evidence(db, "Accepted source")
            db.add(
                Claim(
                    evidence_id=evidence.id,
                    entity_type=ClaimEntityType.PHASE,
                    entity_id=phase.id,
                    claim_type=ClaimType.MODELED_LOAD_MW,
                    claim_value_json={"modeled_primary_load_mw": 900.0},
                    confidence="high",
                    review_status=ClaimReviewStatus.UNREVIEWED,
                )
            )
            db.commit()

            response = PredictionService(db).get_project_prediction(project.id)

            self.assertIn("modeled_load_mw", response.missing_inputs)
            self.assertFalse(any("900" in driver.evidence for driver in response.drivers))
        finally:
            db.close()

    def test_large_load_and_near_term_target_increase_delay_probability(self) -> None:
        db = self.SessionLocal()
        try:
            region = Region(name="PJM", region_type="rto", code="PJM", state="VA")
            utility = Utility(name="Dominion Energy", code="DOM")
            db.add_all([region, utility])
            db.flush()

            project, phase = self._project_with_phase(db, "Large Load Campus")
            project.region_id = region.id
            project.utility_id = utility.id
            target_date = self._target_next_year()
            phase.target_energization_date = target_date
            db.add(
                PhaseLoad(
                    phase_id=phase.id,
                    load_kind=LoadKind.MODELED_PRIMARY,
                    load_mw=900,
                    load_basis_type="modeled_primary_load_mw",
                    load_source="accepted_claim",
                    is_optional_expansion=False,
                    is_firm=True,
                )
            )

            evidence = self._reviewed_evidence(db, "Large load source")
            self._accepted_claim(
                db,
                evidence=evidence,
                entity_type=ClaimEntityType.PHASE,
                entity_id=phase.id,
                claim_type=ClaimType.MODELED_LOAD_MW,
                claim_value_json={"modeled_primary_load_mw": 900.0},
                field_name="modeled_primary_load_mw",
            )
            self._accepted_claim(
                db,
                evidence=evidence,
                entity_type=ClaimEntityType.PHASE,
                entity_id=phase.id,
                claim_type=ClaimType.TARGET_ENERGIZATION_DATE,
                claim_value_json={"target_energization_date": target_date.isoformat()},
                field_name="target_energization_date",
            )
            self._accepted_claim(
                db,
                evidence=evidence,
                entity_type=ClaimEntityType.PROJECT,
                entity_id=project.id,
                claim_type=ClaimType.UTILITY_NAMED,
                claim_value_json={"utility_name": "Dominion Energy"},
                field_name="utility_id",
            )
            self._accepted_claim(
                db,
                evidence=evidence,
                entity_type=ClaimEntityType.PROJECT,
                entity_id=project.id,
                claim_type=ClaimType.REGION_OR_RTO_NAMED,
                claim_value_json={"region_name": "PJM"},
                field_name="region_id",
            )
            db.commit()

            response = PredictionService(db).get_project_prediction(project.id)

            self.assertEqual(response.risk_tier, "high")
            self.assertGreater(response.p_delay_18mo, 0.55)
            self.assertTrue(any(driver.driver == "accepted load > 800 MW" for driver in response.drivers))
            self.assertTrue(any("near-term target" in driver.driver for driver in response.drivers))
            self.assertIn("power_path_support", response.missing_inputs)
        finally:
            db.close()

    def test_power_path_support_decreases_prediction(self) -> None:
        db = self.SessionLocal()
        try:
            project, phase = self._project_with_phase(db, "Power Path Campus")
            phase.target_energization_date = self._target_next_year()
            evidence = self._reviewed_evidence(db, "Power path source")
            self._accepted_claim(
                db,
                evidence=evidence,
                entity_type=ClaimEntityType.PHASE,
                entity_id=phase.id,
                claim_type=ClaimType.MODELED_LOAD_MW,
                claim_value_json={"modeled_primary_load_mw": 300.0},
                field_name="modeled_primary_load_mw",
            )
            self._accepted_claim(
                db,
                evidence=evidence,
                entity_type=ClaimEntityType.PHASE,
                entity_id=phase.id,
                claim_type=ClaimType.POWER_PATH_IDENTIFIED_FLAG,
                claim_value_json={"value": True},
                field_name="power_path_identified",
            )
            db.commit()

            response = PredictionService(db).get_project_prediction(project.id)

            self.assertTrue(any(driver.driver == "accepted power-path support" and driver.weight < 0 for driver in response.drivers))
            self.assertNotIn("power_path_support", response.missing_inputs)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
