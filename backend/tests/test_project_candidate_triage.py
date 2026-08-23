from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

from app.api.routes.project_candidates import list_project_candidates  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.discovered_source import DiscoveredSourceClaim, DiscoveredSourceRecord  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.project_candidate import ProjectCandidate  # noqa: E402
from app.services.project_candidate_triage import ProjectCandidateTriageService  # noqa: E402
import triage_project_candidates  # noqa: E402


class ProjectCandidateTriageTest(unittest.TestCase):
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

    def _source(self, db, **kwargs) -> DiscoveredSourceRecord:
        suffix = kwargs.pop("source_suffix", str(uuid.uuid4()))
        defaults = {
            "source_url": f"https://county.example.gov/planning/{suffix}",
            "source_title": "Planning Commission data center agenda",
            "source_type": "county_city_planning",
            "publisher": "Example County Planning",
            "geography": "Virginia",
            "discovery_method": "web_search_pattern",
            "status": "discovered",
        }
        defaults.update(kwargs)
        source = DiscoveredSourceRecord(**defaults)
        db.add(source)
        db.flush()
        return source

    def _claim(self, db, source: DiscoveredSourceRecord, claim_type: str, claim_value: str, confidence: float = 0.9):
        claim = DiscoveredSourceClaim(
            discovered_source_id=source.id,
            source_url=source.source_url,
            claim_type=claim_type,
            claim_value=claim_value,
            evidence_excerpt=f"{claim_type}: {claim_value}",
            confidence=confidence,
            extractor_name="test",
            extractor_version="0",
            status="extracted",
            claim_fingerprint=f"{source.id}:{claim_type}:{claim_value}",
        )
        db.add(claim)
        db.flush()
        return claim

    def _build_constraint_candidate(self, db, excerpt: str) -> ProjectCandidate:
        source = self._source(
            db,
            source_url=f"https://www.example.gov/planning/{uuid.uuid4()}",
            publisher="Example County .gov",
            source_title="Planning Commission data center permit agenda",
            snippet=excerpt,
        )
        claims = [
            self._claim(db, source, "possible_project_name", "Example Data Center Campus"),
            self._claim(db, source, "state", "Virginia"),
            self._claim(db, source, "developer", "Example Developer"),
            self._claim(db, source, "general_relevance", excerpt),
        ]
        return self._candidate(
            db,
            source=source,
            claims=claims,
            evidence_excerpt=excerpt,
        )

    def _candidate(self, db, **kwargs) -> ProjectCandidate:
        source = kwargs.pop("source", None) or self._source(db, source_suffix=kwargs.get("candidate_key"))
        claims = kwargs.pop("claims", None)
        if claims is None:
            claims = [
                self._claim(db, source, "possible_project_name", "Example Data Center Campus"),
                self._claim(db, source, "state", "Virginia"),
                self._claim(db, source, "developer", "Example Developer"),
            ]
        defaults = {
            "candidate_key": f"candidate-{source.id}",
            "candidate_name": "Example Data Center Campus",
            "developer": "Example Developer",
            "state": "Virginia",
            "county": "Example County",
            "city": None,
            "utility": None,
            "load_mw": None,
            "lifecycle_state": "candidate_unverified",
            "confidence": 0.86,
            "status": "candidate",
            "source_count": 1,
            "claim_count": len(claims),
            "primary_source_url": source.source_url,
            "discovered_source_ids_json": [str(source.id)],
            "discovered_source_claim_ids_json": [str(claim.id) for claim in claims],
            "evidence_excerpt": "Official source names Example Data Center Campus.",
            "raw_metadata_json": {"source_titles": [source.source_title]},
        }
        defaults.update(kwargs)
        candidate = ProjectCandidate(**defaults)
        db.add(candidate)
        db.flush()
        return candidate

    def test_high_quality_official_project_specific_candidate_scores_high(self) -> None:
        db = self.SessionLocal()
        try:
            source = self._source(db, source_url="https://www.example.gov/agendas/data-center", publisher="Example County .gov")
            claims = [
                self._claim(db, source, "possible_project_name", "Example Data Center Campus"),
                self._claim(db, source, "state", "Virginia"),
                self._claim(db, source, "developer", "Example Developer"),
                self._claim(db, source, "load_mw", "300"),
            ]
            candidate = self._candidate(db, source=source, claims=claims, load_mw=300)
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        self.assertEqual(result.triage_tier, "high")
        self.assertEqual(result.recommended_action, "review_for_promotion")
        self.assertGreaterEqual(result.triage_score, 0.7)
        self.assertIn("official_or_high_trust_source", result.triage_reasons)

    def test_unresolved_or_missing_location_candidate_scores_lower(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(
                db,
                candidate_name="Unresolved Virginia SCC candidate abc123",
                state=None,
                confidence=0.62,
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        self.assertLess(result.triage_score, 0.7)
        self.assertEqual(result.recommended_action, "needs_project_name")
        self.assertIn("unresolved_candidate_name", result.triage_warnings)
        self.assertIn("missing_state", result.triage_warnings)

    def test_context_only_candidate_scores_low_and_defers(self) -> None:
        db = self.SessionLocal()
        try:
            source = self._source(
                db,
                source_type="grid_context",
                publisher="EIA",
                source_url="https://www.eia.gov/example",
            )
            claims = [self._claim(db, source, "general_relevance", "data center")]
            candidate = self._candidate(
                db,
                source=source,
                claims=claims,
                candidate_name="Unresolved context candidate",
                state=None,
                developer=None,
                confidence=0.45,
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        self.assertEqual(result.triage_tier, "low")
        self.assertEqual(result.recommended_action, "likely_context_only")
        self.assertIn("context_only_source", result.triage_warnings)

    def test_triage_detects_broader_build_constraint_signals(self) -> None:
        cases = {
            "community_opposition": "Residents oppose the proposed data center after a public hearing opposition campaign.",
            "litigation_or_legal": "A lawsuit and legal challenge were filed over the project approval.",
            "permitting_or_regulatory": "The site plan approval and air permit application remain under regulatory review.",
            "onsite_generation": "The applicant describes behind-the-meter onsite generation and a dedicated power plant.",
            "diesel_generation": "The permit lists emergency generators and diesel generators for backup power.",
            "gas_turbine_generation": "The campus may use natural gas generation with combustion turbines.",
            "nuclear_or_smr": "The developer is evaluating small modular reactors and advanced nuclear power.",
            "air_emissions": "The proposal requires an air quality permit for NOx emissions.",
            "water_cooling": "Cooling towers would increase water withdrawal for cooling water.",
            "cost_financing": "The filing cites capital cost pressure and bond financing.",
        }
        for signal, excerpt in cases.items():
            with self.subTest(signal=signal):
                db = self.SessionLocal()
                try:
                    candidate = self._build_constraint_candidate(db, excerpt)
                    db.commit()
                    result = ProjectCandidateTriageService(db).triage(candidate)
                finally:
                    db.close()

                self.assertIn(f"build_constraint_signal_{signal}", result.triage_reasons)

    def test_triage_constraint_signals_do_not_auto_promote_or_auto_admit(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._build_constraint_candidate(
                db,
                "Residents oppose onsite generation, air emissions, water use, and project financing.",
            )
            candidate.review_decision = "keep_under_review"
            candidate.review_notes = "Preserve analyst note"
            candidate.reviewed_by = "analyst-a"
            db.commit()

            ProjectCandidateTriageService(db).triage(candidate, persist=True)
            db.commit()

            refreshed = db.get(ProjectCandidate, candidate.id)
            project_count = db.scalar(select(func.count()).select_from(Project))
        finally:
            db.close()

        self.assertIsNotNone(refreshed)
        self.assertEqual(project_count, 0)
        self.assertIsNone(refreshed.promoted_project_id)
        self.assertNotEqual(refreshed.status, "promoted")
        self.assertFalse(refreshed.auto_admit_eligible)
        self.assertIsNone(refreshed.verification_status)
        self.assertEqual(refreshed.review_decision, "keep_under_review")
        self.assertEqual(refreshed.review_notes, "Preserve analyst note")
        self.assertEqual(refreshed.reviewed_by, "analyst-a")

    def test_energy_strategy_unknown_without_explicit_energy_signal(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(db)
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate, persist=True)
            db.commit()
            refreshed = db.get(ProjectCandidate, candidate.id)
        finally:
            db.close()

        self.assertEqual(result.energy_strategy_classification["energy_strategy"], "unknown")
        self.assertIn("energy_strategy_unknown", result.triage_reasons)
        self.assertEqual(refreshed.raw_metadata_json["energy_strategy_classification"]["energy_strategy"], "unknown")

    def test_energy_strategy_grid_interconnection_does_not_imply_onsite_generation(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._build_constraint_candidate(
                db,
                "The campus requires a substation, transmission upgrades, and utility interconnection study.",
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        classification = result.energy_strategy_classification
        self.assertEqual(classification["energy_strategy"], "unknown")
        self.assertIn("substation", classification["energy_risk_tags"])
        self.assertIn("transmission", classification["energy_risk_tags"])
        self.assertIn("grid_or_interconnection_only_not_onsite_generation", classification["energy_strategy_warnings"])
        self.assertNotIn("energy_strategy_onsite_generation", result.triage_reasons)

    def test_energy_strategy_diesel_generator_farm_is_diesel_generation(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._build_constraint_candidate(
                db,
                "The filing describes a dedicated onsite diesel generator farm with an air permit for emissions.",
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        classification = result.energy_strategy_classification
        self.assertEqual(classification["energy_strategy"], "diesel_generation")
        self.assertIn("diesel", classification["energy_risk_tags"])
        self.assertIn("air_permit", classification["energy_risk_tags"])
        self.assertIn("emissions", classification["energy_risk_tags"])
        self.assertIn("energy_strategy_diesel", result.triage_reasons)
        self.assertIn("air_emissions_review_needed", result.triage_warnings)

    def test_energy_strategy_backup_generators_are_grid_plus_backup(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._build_constraint_candidate(
                db,
                "The project lists emergency backup diesel generators for outage support.",
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        classification = result.energy_strategy_classification
        self.assertEqual(classification["energy_strategy"], "grid_plus_backup")
        self.assertIn("diesel", classification["energy_risk_tags"])
        self.assertIn("backup_generation_not_primary_power", result.triage_warnings)
        self.assertNotIn("energy_strategy_onsite_generation", result.triage_reasons)

    def test_energy_strategy_gas_turbine_classification_depends_on_wording(self) -> None:
        cases = [
            (
                "The developer proposes a dedicated power plant with natural gas generation and combustion turbines.",
                "dedicated_gas_generation",
            ),
            (
                "The campus may add onsite generation using gas turbines alongside utility service.",
                "grid_plus_onsite",
            ),
        ]
        for excerpt, expected in cases:
            with self.subTest(expected=expected):
                db = self.SessionLocal()
                try:
                    candidate = self._build_constraint_candidate(db, excerpt)
                    db.commit()
                    result = ProjectCandidateTriageService(db).triage(candidate)
                finally:
                    db.close()

                classification = result.energy_strategy_classification
                self.assertEqual(classification["energy_strategy"], expected)
                self.assertIn("gas_turbine", classification["energy_risk_tags"])
                self.assertIn("fuel_supply", classification["energy_risk_tags"])

    def test_energy_strategy_nuclear_smr_is_uncertain(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._build_constraint_candidate(
                db,
                "The developer is evaluating small modular reactors as a future power option.",
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        classification = result.energy_strategy_classification
        self.assertEqual(classification["energy_strategy"], "nuclear_or_smr")
        self.assertIn("nuclear", classification["energy_risk_tags"])
        self.assertIn("nuclear_strategy_uncertain", classification["energy_strategy_warnings"])
        self.assertIn("nuclear_strategy_uncertain", result.triage_warnings)

    def test_energy_strategy_fuel_cell_is_distinct(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._build_constraint_candidate(
                db,
                "The campus will use onsite fuel cells for power.",
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        classification = result.energy_strategy_classification
        self.assertEqual(classification["energy_strategy"], "fuel_cell")
        self.assertIn("fuel_cell", classification["energy_risk_tags"])
        self.assertNotIn("gas_turbine", classification["energy_risk_tags"])

    def test_energy_strategy_multiple_signals_are_hybrid(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._build_constraint_candidate(
                db,
                "The plan combines gas turbines, fuel cells, and battery storage for a hybrid campus power system.",
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        classification = result.energy_strategy_classification
        self.assertEqual(classification["energy_strategy"], "hybrid_power")
        self.assertIn("gas_turbine", classification["energy_risk_tags"])
        self.assertIn("fuel_cell", classification["energy_risk_tags"])
        self.assertIn("battery_storage", classification["energy_risk_tags"])
        self.assertIn("energy_strategy_hybrid_power", result.triage_reasons)

    def test_csv_metadata_energy_text_can_be_classified(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(
                db,
                evidence_excerpt=None,
                raw_metadata_json={
                    "provenance": "dataset_import",
                    "raw_row": {
                        "Power Source": "Fuel cell array with utility interconnection",
                        "Notes": "Imported fixture row",
                    },
                },
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        self.assertEqual(result.energy_strategy_classification["energy_strategy"], "fuel_cell")

    def test_siting_friction_unknown_without_explicit_signal(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(db)
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate, persist=True)
            db.commit()
            refreshed = db.get(ProjectCandidate, candidate.id)
        finally:
            db.close()

        self.assertEqual(result.siting_friction_classification["siting_friction_categories"], ["unknown"])
        self.assertIn("no_explicit_siting_friction_signal", result.siting_friction_classification["siting_friction_reasons"])
        self.assertEqual(
            refreshed.raw_metadata_json["siting_friction_classification"]["siting_friction_categories"],
            ["unknown"],
        )

    def test_siting_public_hearing_is_review_signal_not_opposition(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._build_constraint_candidate(
                db,
                "The county scheduled a public hearing and public meeting for the data center application.",
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        categories = result.siting_friction_classification["siting_friction_categories"]
        self.assertIn("public_hearing", categories)
        self.assertNotIn("community_opposition", categories)
        self.assertIn("siting_public_hearing", result.triage_reasons)
        self.assertIn("public_hearing_not_opposition", result.triage_warnings)

    def test_siting_detects_community_opposition_language(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._build_constraint_candidate(
                db,
                "Residents oppose the proposed data center and filed a petition against the rezoning.",
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        categories = result.siting_friction_classification["siting_friction_categories"]
        self.assertIn("community_opposition", categories)
        self.assertIn("zoning_land_use", categories)
        self.assertIn("siting_community_opposition", result.triage_reasons)

    def test_siting_detects_lawsuit_and_legal_challenge_language(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._build_constraint_candidate(
                db,
                "A lawsuit and legal challenge were filed in court over the site approval.",
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        self.assertIn("litigation", result.siting_friction_classification["siting_friction_categories"])
        self.assertIn("siting_litigation", result.triage_reasons)
        self.assertIn("litigation_requires_source_review", result.triage_warnings)

    def test_siting_detects_moratorium_and_pause_language(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._build_constraint_candidate(
                db,
                "The board adopted a moratorium and permit freeze for new data center approvals.",
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        self.assertIn("moratorium", result.siting_friction_classification["siting_friction_categories"])

    def test_siting_detects_zoning_land_use_language(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._build_constraint_candidate(
                db,
                "The application requests rezoning and a special use permit for land use approval.",
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        self.assertIn("zoning_land_use", result.siting_friction_classification["siting_friction_categories"])
        self.assertIn("siting_zoning_land_use", result.triage_reasons)

    def test_siting_detects_permit_delay_and_regulatory_language(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._build_constraint_candidate(
                db,
                "The filing describes a permitting delay after regulatory review delayed approval.",
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        self.assertIn("permit_delay", result.siting_friction_classification["siting_friction_categories"])
        self.assertIn("siting_permit_delay", result.triage_reasons)

    def test_siting_air_emissions_requires_explicit_signal(self) -> None:
        cases = [
            ("The project requests 600 MW of electricity demand from the utility.", False),
            ("The project requires an air permit for diesel generators and NOx emissions.", True),
        ]
        for excerpt, expected in cases:
            with self.subTest(expected=expected):
                db = self.SessionLocal()
                try:
                    candidate = self._build_constraint_candidate(db, excerpt)
                    db.commit()
                    result = ProjectCandidateTriageService(db).triage(candidate)
                finally:
                    db.close()

                categories = result.siting_friction_classification["siting_friction_categories"]
                if expected:
                    self.assertIn("air_permitting", categories)
                    self.assertIn("emissions_concern", categories)
                    self.assertIn("siting_air_emissions", result.triage_reasons)
                    self.assertIn("air_emissions_requires_permit_review", result.triage_warnings)
                else:
                    self.assertNotIn("air_permitting", categories)
                    self.assertNotIn("emissions_concern", categories)

    def test_siting_water_cooling_requires_water_signal(self) -> None:
        cases = [
            ("The project includes a cooling system for the data hall.", False),
            ("Cooling water and water withdrawal from the river remain under review.", True),
        ]
        for excerpt, expected in cases:
            with self.subTest(expected=expected):
                db = self.SessionLocal()
                try:
                    candidate = self._build_constraint_candidate(db, excerpt)
                    db.commit()
                    result = ProjectCandidateTriageService(db).triage(candidate)
                finally:
                    db.close()

                categories = result.siting_friction_classification["siting_friction_categories"]
                if expected:
                    self.assertIn("water_cooling", categories)
                    self.assertIn("siting_water_cooling", result.triage_reasons)
                    self.assertIn("water_risk_requires_source_review", result.triage_warnings)
                else:
                    self.assertNotIn("water_cooling", categories)

    def test_siting_detects_cost_financing_as_review_signal(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._build_constraint_candidate(
                db,
                "The filing cites capital cost pressure, a funding gap, and bond financing needs.",
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        self.assertIn("cost_financing", result.siting_friction_classification["siting_friction_categories"])
        self.assertIn("siting_cost_financing", result.triage_reasons)
        self.assertIn("cost_signal_not_delay_proof", result.triage_warnings)

    def test_siting_detects_political_opposition(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._build_constraint_candidate(
                db,
                "Council opposed the data center after political opposition from local officials.",
            )
            db.commit()
            result = ProjectCandidateTriageService(db).triage(candidate)
        finally:
            db.close()

        self.assertIn("political_opposition", result.siting_friction_classification["siting_friction_categories"])
        self.assertIn("siting_political_opposition", result.triage_reasons)

    def test_siting_signals_do_not_promote_auto_admit_or_overwrite_review(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._build_constraint_candidate(
                db,
                "Residents oppose the rezoning and filed a lawsuit after a public hearing.",
            )
            candidate.review_decision = "keep_under_review"
            candidate.review_notes = "Preserve siting review note"
            candidate.reviewed_by = "analyst-b"
            db.commit()

            ProjectCandidateTriageService(db).triage(candidate, persist=True)
            db.commit()

            refreshed = db.get(ProjectCandidate, candidate.id)
            project_count = db.scalar(select(func.count()).select_from(Project))
        finally:
            db.close()

        self.assertEqual(project_count, 0)
        self.assertIsNone(refreshed.promoted_project_id)
        self.assertNotEqual(refreshed.status, "promoted")
        self.assertFalse(refreshed.auto_admit_eligible)
        self.assertEqual(refreshed.review_decision, "keep_under_review")
        self.assertEqual(refreshed.review_notes, "Preserve siting review note")
        self.assertEqual(refreshed.reviewed_by, "analyst-b")

    def test_triage_cli_dry_run_does_not_write(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(db)
            db.commit()
        finally:
            db.close()

        with patch.object(triage_project_candidates, "SessionLocal", self.SessionLocal):
            with patch("sys.argv", ["triage_project_candidates.py"]):
                triage_project_candidates.main()

        db = self.SessionLocal()
        try:
            candidate = db.get(ProjectCandidate, candidate.id)
        finally:
            db.close()

        self.assertIsNone(candidate.triage_score)
        self.assertIsNone(candidate.triage_tier)

    def test_triage_cli_confirm_updates_fields_without_projects_or_promotions(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(db)
            db.commit()
        finally:
            db.close()

        with patch.object(triage_project_candidates, "SessionLocal", self.SessionLocal):
            with patch("sys.argv", ["triage_project_candidates.py", "--confirm"]):
                triage_project_candidates.main()

        db = self.SessionLocal()
        try:
            candidate = db.get(ProjectCandidate, candidate.id)
            project_count = db.scalar(select(func.count()).select_from(Project))
        finally:
            db.close()

        self.assertIsNotNone(candidate.triage_score)
        self.assertEqual(candidate.triage_tier, "high")
        self.assertEqual(candidate.recommended_action, "review_for_promotion")
        self.assertIsNone(candidate.promoted_project_id)
        self.assertNotEqual(candidate.status, "promoted")
        self.assertEqual(project_count, 0)

    def test_api_response_includes_triage_fields_and_filters(self) -> None:
        db = self.SessionLocal()
        try:
            high = self._candidate(db, candidate_key="high")
            low = self._candidate(
                db,
                candidate_key="low",
                candidate_name="Unresolved low candidate",
                state=None,
                confidence=0.4,
            )
            db.commit()
            ProjectCandidateTriageService(db).triage(high, persist=True)
            ProjectCandidateTriageService(db).triage(low, persist=True)
            db.commit()

            response = list_project_candidates(triage_tier="high", min_triage_score=0.7, limit=100, db=db)
        finally:
            db.close()

        self.assertEqual(len(response.items), 1)
        item = response.items[0]
        self.assertEqual(item.id, high.id)
        self.assertEqual(item.triage_tier, "high")
        self.assertIsNotNone(item.triage_score)
        self.assertEqual(item.recommended_action, "review_for_promotion")
        self.assertEqual(item.energy_strategy, "unknown")
        self.assertIsNotNone(item.energy_strategy_confidence)
        self.assertIn("no_explicit_energy_strategy_signal", item.energy_strategy_reasons)
        self.assertEqual(item.siting_friction_categories, ["unknown"])
        self.assertIsNotNone(item.siting_friction_confidence)
        self.assertIn("no_explicit_siting_friction_signal", item.siting_friction_reasons)


if __name__ == "__main__":
    unittest.main()
