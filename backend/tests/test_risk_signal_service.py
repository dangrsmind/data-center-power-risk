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
from app.services.risk_signal_service import RiskSignalService  # noqa: E402


class RiskSignalServiceTest(unittest.TestCase):
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

    def test_candidate_project_with_little_evidence_scores_as_underresolved(self) -> None:
        db = self.SessionLocal()
        try:
            project = Project(
                canonical_name="Thin Evidence Campus",
                state="VA",
                county="Caroline",
                lifecycle_state=LifecycleState.CANDIDATE_UNVERIFIED,
            )
            db.add(project)
            db.commit()

            response = RiskSignalService(db).get_project_risk_signal(project.id)

            self.assertEqual(response.evidence_summary.evidence_count, 0)
            self.assertIn("utility_named", response.missing_fields)
            self.assertIn("power_path_support", response.missing_fields)
            self.assertEqual(response.risk_signal, "power_path_underresolved")
            self.assertEqual(response.risk_signal_tier, "high")
        finally:
            db.close()

    def test_identity_fields_present_but_missing_utility_and_power_path(self) -> None:
        db = self.SessionLocal()
        try:
            region = Region(name="PJM", region_type="rto", code="PJM", state="VA")
            db.add(region)
            db.flush()

            project = Project(
                canonical_name="AVAIO Prince Edward",
                state="VA",
                county="Prince Edward",
                lifecycle_state=LifecycleState.NAMED_VERIFIED,
                region_id=region.id,
            )
            db.add(project)
            db.flush()

            phase = Phase(project_id=project.id, phase_name="Phase I", phase_order=1, target_energization_date=date(2027, 12, 1))
            db.add(phase)
            db.flush()

            db.add(
                PhaseLoad(
                    phase_id=phase.id,
                    load_kind=LoadKind.MODELED_PRIMARY,
                    load_mw=300,
                    load_basis_type="modeled_primary_load_mw",
                    load_source="accepted_claim",
                    is_optional_expansion=False,
                    is_firm=True,
                )
            )

            evidence = Evidence(
                source_type=SourceType.DEVELOPER_STATEMENT,
                source_date=date(2026, 4, 27),
                title="AVAIO update",
                extracted_text="AVAIO Prince Edward is planned in Virginia",
                reviewer_status=ReviewerStatus.REVIEWED,
            )
            db.add(evidence)
            db.flush()

            accepted_claims = [
                Claim(
                    evidence_id=evidence.id,
                    entity_type=ClaimEntityType.PROJECT,
                    entity_id=project.id,
                    claim_type=ClaimType.PROJECT_NAME_MENTION,
                    claim_value_json={"project_name": "AVAIO Prince Edward"},
                    confidence="high",
                    review_status=ClaimReviewStatus.ACCEPTED,
                ),
                Claim(
                    evidence_id=evidence.id,
                    entity_type=ClaimEntityType.PROJECT,
                    entity_id=project.id,
                    claim_type=ClaimType.REGION_OR_RTO_NAMED,
                    claim_value_json={"region_name": "PJM"},
                    confidence="high",
                    review_status=ClaimReviewStatus.ACCEPTED,
                ),
                Claim(
                    evidence_id=evidence.id,
                    entity_type=ClaimEntityType.PHASE,
                    entity_id=phase.id,
                    claim_type=ClaimType.TARGET_ENERGIZATION_DATE,
                    claim_value_json={"target_energization_date": "2027-12-01"},
                    confidence="medium",
                    review_status=ClaimReviewStatus.ACCEPTED,
                ),
                Claim(
                    evidence_id=evidence.id,
                    entity_type=ClaimEntityType.PHASE,
                    entity_id=phase.id,
                    claim_type=ClaimType.MODELED_LOAD_MW,
                    claim_value_json={"modeled_primary_load_mw": 300.0},
                    confidence="medium",
                    review_status=ClaimReviewStatus.ACCEPTED,
                ),
            ]
            db.add_all(accepted_claims)
            db.flush()

            db.add_all(
                [
                    FieldProvenance(
                        entity_type=ClaimEntityType.PROJECT,
                        entity_id=project.id,
                        field_name="canonical_name",
                        evidence_id=evidence.id,
                        claim_id=accepted_claims[0].id,
                    ),
                    FieldProvenance(
                        entity_type=ClaimEntityType.PROJECT,
                        entity_id=project.id,
                        field_name="region_id",
                        evidence_id=evidence.id,
                        claim_id=accepted_claims[1].id,
                    ),
                    FieldProvenance(
                        entity_type=ClaimEntityType.PHASE,
                        entity_id=phase.id,
                        field_name="target_energization_date",
                        evidence_id=evidence.id,
                        claim_id=accepted_claims[2].id,
                    ),
                    FieldProvenance(
                        entity_type=ClaimEntityType.PHASE,
                        entity_id=phase.id,
                        field_name="modeled_primary_load_mw",
                        evidence_id=evidence.id,
                        claim_id=accepted_claims[3].id,
                    ),
                ]
            )
            db.commit()

            response = RiskSignalService(db).get_project_risk_signal(project.id)

            self.assertIn("utility_named", response.missing_fields)
            self.assertIn("power_path_support", response.missing_fields)
            self.assertNotIn("region_or_rto_named", response.missing_fields)
            self.assertEqual(response.risk_signal, "power_path_underresolved")
            self.assertGreaterEqual(response.risk_signal_score, 0.55)
        finally:
            db.close()

    def test_higher_load_project_produces_higher_score(self) -> None:
        db = self.SessionLocal()
        try:
            region = Region(name="ERCOT", region_type="rto", code="ERCOT", state="TX")
            utility = Utility(name="Oncor Electric Delivery", code="ONCOR", region_id=None)
            db.add_all([region, utility])
            db.flush()
            utility.region_id = region.id

            low_project = Project(
                canonical_name="CleanArc 300",
                state="TX",
                county="Ellis",
                lifecycle_state=LifecycleState.NAMED_VERIFIED,
                region_id=region.id,
                utility_id=utility.id,
            )
            high_project = Project(
                canonical_name="CleanArc 900",
                state="TX",
                county="Ellis",
                lifecycle_state=LifecycleState.NAMED_VERIFIED,
                region_id=region.id,
                utility_id=utility.id,
            )
            db.add_all([low_project, high_project])
            db.flush()

            low_phase = Phase(project_id=low_project.id, phase_name="Phase I", phase_order=1, target_energization_date=date(2027, 12, 1))
            high_phase = Phase(project_id=high_project.id, phase_name="Phase I", phase_order=1, target_energization_date=date(2027, 12, 1))
            db.add_all([low_phase, high_phase])
            db.flush()

            db.add_all(
                [
                    PhaseLoad(
                        phase_id=low_phase.id,
                        load_kind=LoadKind.MODELED_PRIMARY,
                        load_mw=300,
                        load_basis_type="modeled_primary_load_mw",
                        load_source="accepted_claim",
                        is_optional_expansion=False,
                        is_firm=True,
                    ),
                    PhaseLoad(
                        phase_id=high_phase.id,
                        load_kind=LoadKind.MODELED_PRIMARY,
                        load_mw=900,
                        load_basis_type="modeled_primary_load_mw",
                        load_source="accepted_claim",
                        is_optional_expansion=False,
                        is_firm=True,
                    ),
                ]
            )

            low_evidence = Evidence(
                source_type=SourceType.DEVELOPER_STATEMENT,
                title="Low load project",
                reviewer_status=ReviewerStatus.REVIEWED,
            )
            high_evidence = Evidence(
                source_type=SourceType.DEVELOPER_STATEMENT,
                title="High load project",
                reviewer_status=ReviewerStatus.REVIEWED,
            )
            db.add_all([low_evidence, high_evidence])
            db.flush()

            for project, phase, evidence, mw in [
                (low_project, low_phase, low_evidence, 300.0),
                (high_project, high_phase, high_evidence, 900.0),
            ]:
                claims = [
                    Claim(
                        evidence_id=evidence.id,
                        entity_type=ClaimEntityType.PROJECT,
                        entity_id=project.id,
                        claim_type=ClaimType.UTILITY_NAMED,
                        claim_value_json={"utility_name": "Oncor Electric Delivery"},
                        confidence="high",
                        review_status=ClaimReviewStatus.ACCEPTED,
                    ),
                    Claim(
                        evidence_id=evidence.id,
                        entity_type=ClaimEntityType.PROJECT,
                        entity_id=project.id,
                        claim_type=ClaimType.REGION_OR_RTO_NAMED,
                        claim_value_json={"region_name": "ERCOT"},
                        confidence="high",
                        review_status=ClaimReviewStatus.ACCEPTED,
                    ),
                    Claim(
                        evidence_id=evidence.id,
                        entity_type=ClaimEntityType.PHASE,
                        entity_id=phase.id,
                        claim_type=ClaimType.TARGET_ENERGIZATION_DATE,
                        claim_value_json={"target_energization_date": "2027-12-01"},
                        confidence="high",
                        review_status=ClaimReviewStatus.ACCEPTED,
                    ),
                    Claim(
                        evidence_id=evidence.id,
                        entity_type=ClaimEntityType.PHASE,
                        entity_id=phase.id,
                        claim_type=ClaimType.MODELED_LOAD_MW,
                        claim_value_json={"modeled_primary_load_mw": mw},
                        confidence="high",
                        review_status=ClaimReviewStatus.ACCEPTED,
                    ),
                    Claim(
                        evidence_id=evidence.id,
                        entity_type=ClaimEntityType.PHASE,
                        entity_id=phase.id,
                        claim_type=ClaimType.POWER_PATH_IDENTIFIED_FLAG,
                        claim_value_json={"value": True},
                        confidence="medium",
                        review_status=ClaimReviewStatus.ACCEPTED,
                    ),
                ]
                db.add_all(claims)
                db.flush()
                db.add_all(
                    [
                        FieldProvenance(
                            entity_type=ClaimEntityType.PROJECT,
                            entity_id=project.id,
                            field_name="utility_id",
                            evidence_id=evidence.id,
                            claim_id=claims[0].id,
                        ),
                        FieldProvenance(
                            entity_type=ClaimEntityType.PROJECT,
                            entity_id=project.id,
                            field_name="region_id",
                            evidence_id=evidence.id,
                            claim_id=claims[1].id,
                        ),
                        FieldProvenance(
                            entity_type=ClaimEntityType.PHASE,
                            entity_id=phase.id,
                            field_name="target_energization_date",
                            evidence_id=evidence.id,
                            claim_id=claims[2].id,
                        ),
                        FieldProvenance(
                            entity_type=ClaimEntityType.PHASE,
                            entity_id=phase.id,
                            field_name="modeled_primary_load_mw",
                            evidence_id=evidence.id,
                            claim_id=claims[3].id,
                        ),
                    ]
                )

            db.commit()

            low_response = RiskSignalService(db).get_project_risk_signal(low_project.id)
            high_response = RiskSignalService(db).get_project_risk_signal(high_project.id)

            self.assertGreater(high_response.risk_signal_score, low_response.risk_signal_score)
            self.assertTrue(any("900 MW" in driver for driver in high_response.drivers))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
