from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.api.routes.project_candidates import get_project_candidate_constraint_summary  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.project_candidate import ProjectCandidate  # noqa: E402


class ProjectCandidateConstraintSummaryTest(unittest.TestCase):
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

    def candidate(self, db, **kwargs) -> ProjectCandidate:
        defaults = {
            "candidate_key": kwargs.get("candidate_name", "Example Candidate").lower().replace(" ", "-"),
            "candidate_name": "Example Candidate",
            "developer": "Example Developer",
            "state": "Virginia",
            "county": "Example County",
            "city": None,
            "utility": None,
            "load_mw": None,
            "lifecycle_state": "candidate_unverified",
            "confidence": 0.7,
            "status": "candidate",
            "source_count": 1,
            "claim_count": 1,
            "primary_source_url": "https://example.gov/source",
            "discovered_source_ids_json": ["11111111-1111-1111-1111-111111111111"],
            "discovered_source_claim_ids_json": ["22222222-2222-2222-2222-222222222222"],
            "evidence_excerpt": "Short public source excerpt.",
            "raw_metadata_json": {},
            "auto_admit_eligible": False,
        }
        defaults.update(kwargs)
        candidate = ProjectCandidate(**defaults)
        db.add(candidate)
        db.flush()
        return candidate

    def test_empty_database_returns_zero_counts(self) -> None:
        db = self.SessionLocal()
        try:
            response = get_project_candidate_constraint_summary(db=db)
        finally:
            db.close()

        self.assertEqual(response.total_candidates, 0)
        self.assertEqual(response.by_status, {})
        self.assertEqual(response.csv_backed_count, 0)
        self.assertEqual(response.top_review_priority_candidates, [])

    def test_summary_counts_and_top_fields_are_safe(self) -> None:
        db = self.SessionLocal()
        try:
            self.candidate(
                db,
                candidate_key="alpha",
                candidate_name="Alpha Campus",
                status="needs_review",
                triage_tier="high",
                triage_score=0.91,
                recommended_action="review_for_promotion",
                review_decision="ready_for_verification",
                verification_status="needs_review",
                raw_metadata_json={
                    "energy_strategy_classification": {
                        "energy_strategy": "diesel_generation",
                        "energy_strategy_confidence": 0.74,
                        "energy_strategy_reasons": ["explicit_diesel_generation_signal"],
                        "energy_risk_tags": ["diesel", "air_permit", "emissions"],
                        "energy_strategy_warnings": [],
                    },
                    "siting_friction_classification": {
                        "siting_friction_categories": ["community_opposition", "air_permitting"],
                        "siting_friction_confidence": 0.66,
                        "siting_friction_reasons": ["explicit_community_opposition_signal"],
                        "siting_friction_warnings": ["air_emissions_requires_permit_review"],
                    },
                },
            )
            self.candidate(
                db,
                candidate_key="beta",
                candidate_name="Beta Imported",
                status="needs_review",
                triage_tier="medium",
                triage_score=0.55,
                recommended_action="needs_source_detail",
                review_decision="likely_duplicate",
                verification_status=None,
                primary_source_url=None,
                discovered_source_ids_json=[],
                discovered_source_claim_ids_json=[],
                raw_metadata_json={
                    "provenance": "dataset_import",
                    "dataset_name": "test_dataset",
                    "duplicate_status": "possible_duplicate",
                    "imported_rows": [{"imported_row_id": "row-1"}],
                    "raw_row": {"large": "metadata should not appear"},
                    "energy_strategy_classification": {
                        "energy_strategy": "unknown",
                        "energy_strategy_confidence": 0.2,
                        "energy_strategy_reasons": ["no_explicit_energy_strategy_signal"],
                        "energy_risk_tags": [],
                        "energy_strategy_warnings": ["energy_strategy_unknown"],
                    },
                    "siting_friction_classification": {
                        "siting_friction_categories": ["unknown"],
                        "siting_friction_confidence": 0.2,
                        "siting_friction_reasons": ["no_explicit_siting_friction_signal"],
                        "siting_friction_warnings": ["siting_friction_unknown"],
                    },
                },
            )
            self.candidate(
                db,
                candidate_key="gamma",
                candidate_name="Gamma Rejected Dataset",
                status="rejected",
                triage_tier="low",
                triage_score=0.2,
                review_decision="rejected_dataset_only",
                raw_metadata_json={},
            )
            db.commit()

            response = get_project_candidate_constraint_summary(limit_top_candidates=2, db=db)
        finally:
            db.close()

        self.assertEqual(response.total_candidates, 3)
        self.assertEqual(response.by_status["needs_review"], 2)
        self.assertEqual(response.by_status["rejected"], 1)
        self.assertEqual(response.by_triage_tier["high"], 1)
        self.assertEqual(response.by_review_decision["ready_for_verification"], 1)
        self.assertEqual(response.csv_backed_count, 1)
        self.assertEqual(response.web_discovered_count, 2)
        self.assertEqual(response.by_energy_strategy["diesel_generation"], 1)
        self.assertEqual(response.by_energy_strategy["unknown"], 2)
        self.assertEqual(response.by_energy_risk_tag["diesel"], 1)
        self.assertEqual(response.by_energy_risk_tag["air_permit"], 1)
        self.assertEqual(response.with_siting_friction_count, 1)
        self.assertEqual(response.by_siting_friction_category["community_opposition"], 1)
        self.assertEqual(response.by_siting_friction_category["unknown"], 2)
        self.assertEqual(response.by_siting_friction_warning["air_emissions_requires_permit_review"], 1)
        self.assertEqual(response.high_priority_review_count, 1)
        self.assertEqual(response.needs_source_count, 1)
        self.assertEqual(response.ready_for_verification_count, 1)
        self.assertEqual(response.likely_duplicate_count, 1)
        self.assertEqual(response.dataset_only_rejected_count, 1)
        self.assertEqual(len(response.top_review_priority_candidates), 2)
        self.assertEqual(response.top_review_priority_candidates[0].candidate_name, "Alpha Campus")
        self.assertIsNotNone(response.top_review_priority_candidates[1].csv_provenance)
        payload = response.model_dump(mode="json")
        self.assertNotIn("raw_metadata_json", str(payload))
        self.assertNotIn("raw_row", str(payload))
        self.assertNotIn("metadata should not appear", str(payload))

    def test_filters_work_and_endpoint_does_not_mutate_candidates(self) -> None:
        db = self.SessionLocal()
        try:
            diesel = self.candidate(
                db,
                candidate_key="diesel",
                candidate_name="Diesel Candidate",
                status="needs_review",
                triage_tier="high",
                review_decision="keep_under_review",
                raw_metadata_json={
                    "energy_strategy_classification": {
                        "energy_strategy": "diesel_generation",
                        "energy_strategy_confidence": 0.74,
                        "energy_strategy_reasons": [],
                        "energy_risk_tags": ["diesel"],
                        "energy_strategy_warnings": [],
                    },
                    "siting_friction_classification": {
                        "siting_friction_categories": ["air_permitting"],
                        "siting_friction_confidence": 0.62,
                        "siting_friction_reasons": [],
                        "siting_friction_warnings": ["air_emissions_requires_permit_review"],
                    },
                },
            )
            self.candidate(
                db,
                candidate_key="fuel-cell",
                candidate_name="Fuel Cell Candidate",
                status="candidate",
                triage_tier="medium",
                raw_metadata_json={
                    "energy_strategy_classification": {
                        "energy_strategy": "fuel_cell",
                        "energy_strategy_confidence": 0.74,
                        "energy_strategy_reasons": [],
                        "energy_risk_tags": ["fuel_cell"],
                        "energy_strategy_warnings": [],
                    },
                    "siting_friction_classification": {
                        "siting_friction_categories": ["unknown"],
                        "siting_friction_confidence": 0.2,
                        "siting_friction_reasons": [],
                        "siting_friction_warnings": [],
                    },
                },
            )
            db.commit()
            before = {
                "status": diesel.status,
                "auto_admit_eligible": diesel.auto_admit_eligible,
                "review_decision": diesel.review_decision,
                "raw_metadata_json": diesel.raw_metadata_json,
            }

            response = get_project_candidate_constraint_summary(
                status="needs_review",
                energy_strategy="diesel_generation",
                siting_friction_category="air_permitting",
                limit_top_candidates=50,
                db=db,
            )
            refreshed = db.get(ProjectCandidate, diesel.id)
        finally:
            db.close()

        self.assertEqual(response.total_candidates, 1)
        self.assertEqual(response.top_review_priority_candidates[0].candidate_name, "Diesel Candidate")
        self.assertEqual(refreshed.status, before["status"])
        self.assertFalse(refreshed.auto_admit_eligible)
        self.assertEqual(refreshed.review_decision, before["review_decision"])
        self.assertEqual(refreshed.raw_metadata_json, before["raw_metadata_json"])


if __name__ == "__main__":
    unittest.main()
