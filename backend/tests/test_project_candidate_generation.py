from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

from app.models import Base  # noqa: E402
from app.models.discovered_source import DiscoveredSourceClaim, DiscoveredSourceRecord  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.project_candidate import ProjectCandidate  # noqa: E402
from app.services.project_candidate_generator import ProjectCandidateGenerator  # noqa: E402
import discovery_healthcheck  # noqa: E402


class ProjectCandidateGenerationTest(unittest.TestCase):
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

    def _source(self, **kwargs) -> DiscoveredSourceRecord:
        defaults = {
            "source_url": "https://www.scc.virginia.gov/case-information/submit-public-comments/cases/pur-2026-00022.html",
            "source_title": "Virginia SCC case for data center service",
            "source_type": "state_regulatory_dockets",
            "publisher": "Virginia State Corporation Commission",
            "geography": "Virginia",
            "discovery_method": "searchstax_query",
            "status": "discovered",
        }
        defaults.update(kwargs)
        return DiscoveredSourceRecord(**defaults)

    def _claim(self, source: DiscoveredSourceRecord, claim_type: str, claim_value: str, confidence: float = 0.8):
        return DiscoveredSourceClaim(
            discovered_source_id=source.id,
            source_url=source.source_url,
            claim_type=claim_type,
            claim_value=claim_value,
            claim_unit="MW" if claim_type == "load_mw" else None,
            evidence_excerpt=f"{claim_type}: {claim_value}",
            confidence=confidence,
            extractor_name="test",
            extractor_version="0",
            status="extracted",
            claim_fingerprint=f"{source.id}:{claim_type}:{claim_value}",
        )

    def _seed_explicit_claims(self, db):
        source = self._source()
        db.add(source)
        db.flush()
        db.add_all(
            [
                self._claim(source, "possible_project_name", "Example Data Center Campus", 0.75),
                self._claim(source, "developer", "Example Developer", 0.7),
                self._claim(source, "state", "Virginia", 0.85),
                self._claim(source, "load_mw", "300", 0.65),
                self._claim(source, "general_relevance", "data center", 0.7),
            ]
        )
        db.commit()
        return source

    def test_candidate_generation_from_explicit_claims(self) -> None:
        db = self.SessionLocal()
        try:
            self._seed_explicit_claims(db)
            summary = ProjectCandidateGenerator(db).generate()
            db.commit()
            candidate = db.scalar(select(ProjectCandidate))
        finally:
            db.close()

        self.assertEqual(summary.candidates_created, 1)
        self.assertEqual(candidate.candidate_name, "Example Data Center Campus")
        self.assertEqual(candidate.developer, "Example Developer")
        self.assertEqual(candidate.state, "Virginia")
        self.assertEqual(candidate.load_mw, 300)
        self.assertGreaterEqual(candidate.confidence, 0)
        self.assertLessEqual(candidate.confidence, 1)

    def test_unresolved_candidate_gets_cautious_name(self) -> None:
        db = self.SessionLocal()
        try:
            source = self._source()
            db.add(source)
            db.flush()
            db.add_all([self._claim(source, "state", "Virginia"), self._claim(source, "general_relevance", "large load")])
            db.commit()
            ProjectCandidateGenerator(db).generate()
            db.commit()
            candidate = db.scalar(select(ProjectCandidate))
        finally:
            db.close()

        self.assertTrue(candidate.candidate_name.startswith("Unresolved Virginia SCC candidate"))
        self.assertEqual(candidate.status, "needs_review")

    def test_no_final_project_records_and_idempotent_generation(self) -> None:
        db = self.SessionLocal()
        try:
            self._seed_explicit_claims(db)
            first = ProjectCandidateGenerator(db).generate()
            db.commit()
            second = ProjectCandidateGenerator(db).generate()
            db.commit()
            candidate_count = db.scalar(select(func.count()).select_from(ProjectCandidate))
            project_count = db.scalar(select(func.count()).select_from(Project))
        finally:
            db.close()

        self.assertEqual(first.candidates_created, 1)
        self.assertEqual(second.candidates_created, 0)
        self.assertEqual(second.candidates_updated, 1)
        self.assertEqual(candidate_count, 1)
        self.assertEqual(project_count, 0)

    def test_dry_run_does_not_write(self) -> None:
        db = self.SessionLocal()
        try:
            self._seed_explicit_claims(db)
            summary = ProjectCandidateGenerator(db).generate(dry_run=True)
            candidate_count = db.scalar(select(func.count()).select_from(ProjectCandidate))
        finally:
            db.close()

        self.assertEqual(summary.candidates_created, 1)
        self.assertEqual(candidate_count, 0)

    def test_missing_weak_claims_do_not_crash(self) -> None:
        db = self.SessionLocal()
        try:
            summary = ProjectCandidateGenerator(db).generate()
        finally:
            db.close()

        self.assertEqual(summary.candidates_created, 0)
        self.assertIn("no_extracted_claims_available", summary.warnings)

    def test_healthcheck_catches_invalid_candidate_status(self) -> None:
        original_session = discovery_healthcheck.SessionLocal
        discovery_healthcheck.SessionLocal = self.SessionLocal
        db = self.SessionLocal()
        try:
            self._seed_explicit_claims(db)
            ProjectCandidateGenerator(db).generate()
            db.commit()
            db.execute(text("PRAGMA ignore_check_constraints = ON"))
            candidate = db.scalar(select(ProjectCandidate))
            candidate.status = "bad_status"
            db.commit()
            payload = discovery_healthcheck.run_healthcheck()
        finally:
            db.close()
            discovery_healthcheck.SessionLocal = original_session

        self.assertTrue(any("invalid status" in error for error in payload["errors"]))


if __name__ == "__main__":
    unittest.main()
