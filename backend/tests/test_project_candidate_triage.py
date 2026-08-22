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


if __name__ == "__main__":
    unittest.main()
