from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import uuid

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

from app.models import Base  # noqa: E402
from app.models.discovered_source import DiscoveredSourceClaim, DiscoveredSourceRecord  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.project_candidate import ProjectCandidate  # noqa: E402
from app.services.project_candidate_verifier import AUTO_ADMIT_ELIGIBLE, NEEDS_REVIEW, QUARANTINED, ProjectCandidateVerifier  # noqa: E402
import auto_admit_project_candidates  # noqa: E402
import discovery_healthcheck  # noqa: E402
import verify_project_candidates  # noqa: E402


class ProjectCandidateVerifierTest(unittest.TestCase):
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
        source_suffix = kwargs.pop("source_suffix", str(uuid.uuid4()))
        defaults = {
            "source_url": f"https://www.scc.virginia.gov/case/{source_suffix}",
            "source_title": "Virginia SCC official case",
            "source_type": "state_regulatory_dockets",
            "publisher": "Virginia State Corporation Commission",
            "geography": "Virginia",
            "discovery_method": "searchstax_query",
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
            "confidence": 0.9,
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

    def test_official_complete_candidate_is_auto_admit_eligible(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(db)
            db.commit()
            result = ProjectCandidateVerifier(db).verify(candidate)
        finally:
            db.close()

        self.assertEqual(result.decision, AUTO_ADMIT_ELIGIBLE)
        self.assertTrue(result.evidence_requirements_met["official_or_high_trust_source"])

    def test_unresolved_candidate_needs_review(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(db, candidate_name="Unresolved Virginia SCC candidate abc123")
            db.commit()
            result = ProjectCandidateVerifier(db).verify(candidate)
        finally:
            db.close()

        self.assertEqual(result.decision, NEEDS_REVIEW)
        self.assertIn("unresolved_candidate_name", result.warnings)

    def test_missing_source_url_is_quarantined(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(db, primary_source_url=None)
            db.commit()
            result = ProjectCandidateVerifier(db).verify(candidate)
        finally:
            db.close()

        self.assertEqual(result.decision, QUARANTINED)
        self.assertIn("missing_or_invalid_primary_source_url", result.blocking_errors)

    def test_context_only_source_is_quarantined(self) -> None:
        db = self.SessionLocal()
        try:
            source = self._source(
                db,
                source_type="grid_context",
                publisher="EIA",
                source_url="https://www.eia.gov/example",
            )
            candidate = self._candidate(db, source=source)
            db.commit()
            result = ProjectCandidateVerifier(db).verify(candidate)
        finally:
            db.close()

        self.assertEqual(result.decision, QUARANTINED)
        self.assertIn("context_only_or_missing_source", result.blocking_errors)

    def test_low_confidence_candidate_is_not_eligible(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(db, confidence=0.49)
            db.commit()
            result = ProjectCandidateVerifier(db).verify(candidate)
        finally:
            db.close()

        self.assertEqual(result.decision, QUARANTINED)
        self.assertIn("candidate_confidence_too_low", result.blocking_errors)

    def test_verifier_dry_run_does_not_write(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(db)
            db.commit()
            ProjectCandidateVerifier(db).verify(candidate)
            db.refresh(candidate)
        finally:
            db.close()

        self.assertIsNone(candidate.verification_status)
        self.assertFalse(candidate.auto_admit_eligible)

    def test_verify_confirm_updates_verification_fields(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(db)
            db.commit()
            ProjectCandidateVerifier(db).verify(candidate, persist=True)
            db.commit()
            db.refresh(candidate)
        finally:
            db.close()

        self.assertEqual(candidate.verification_status, AUTO_ADMIT_ELIGIBLE)
        self.assertTrue(candidate.auto_admit_eligible)
        self.assertIsNotNone(candidate.verified_at)

    def test_verify_script_confirm_updates_fields(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(db)
            db.commit()
        finally:
            db.close()

        with patch.object(verify_project_candidates, "SessionLocal", self.SessionLocal):
            with patch("sys.argv", ["verify_project_candidates.py", "--confirm"]):
                verify_project_candidates.main()

        db = self.SessionLocal()
        try:
            candidate = db.get(ProjectCandidate, candidate.id)
        finally:
            db.close()

        self.assertEqual(candidate.verification_status, AUTO_ADMIT_ELIGIBLE)

    def test_auto_admit_dry_run_does_not_promote(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(db)
            db.commit()
        finally:
            db.close()

        with patch.object(auto_admit_project_candidates, "SessionLocal", self.SessionLocal):
            with patch("sys.argv", ["auto_admit_project_candidates.py"]):
                auto_admit_project_candidates.main()

        db = self.SessionLocal()
        try:
            candidate = db.get(ProjectCandidate, candidate.id)
            project_count = db.scalar(select(func.count()).select_from(Project))
        finally:
            db.close()

        self.assertEqual(candidate.status, "candidate")
        self.assertIsNone(candidate.promoted_project_id)
        self.assertEqual(project_count, 0)

    def test_auto_admit_confirm_promotes_only_eligible_candidates(self) -> None:
        db = self.SessionLocal()
        try:
            eligible = self._candidate(db, candidate_key="eligible")
            unresolved = self._candidate(
                db,
                candidate_key="unresolved",
                candidate_name="Unresolved Virginia SCC candidate abc123",
            )
            db.commit()
        finally:
            db.close()

        with patch.object(auto_admit_project_candidates, "SessionLocal", self.SessionLocal):
            with patch("sys.argv", ["auto_admit_project_candidates.py", "--confirm"]):
                auto_admit_project_candidates.main()

        db = self.SessionLocal()
        try:
            eligible = db.get(ProjectCandidate, eligible.id)
            unresolved = db.get(ProjectCandidate, unresolved.id)
            project_count = db.scalar(select(func.count()).select_from(Project))
        finally:
            db.close()

        self.assertEqual(eligible.status, "promoted")
        self.assertIsNotNone(eligible.promoted_project_id)
        self.assertEqual(unresolved.status, "candidate")
        self.assertIsNone(unresolved.promoted_project_id)
        self.assertEqual(project_count, 1)

    def test_auto_admit_never_allows_unresolved_or_incomplete_overrides(self) -> None:
        db = self.SessionLocal()
        try:
            self._candidate(db, candidate_name="Unresolved Virginia SCC candidate abc123")
            self._candidate(db, candidate_key="missing-state", state=None)
            db.commit()
        finally:
            db.close()

        with patch.object(auto_admit_project_candidates, "SessionLocal", self.SessionLocal):
            with patch("sys.argv", ["auto_admit_project_candidates.py", "--confirm"]):
                auto_admit_project_candidates.main()

        db = self.SessionLocal()
        try:
            project_count = db.scalar(select(func.count()).select_from(Project))
        finally:
            db.close()

        self.assertEqual(project_count, 0)

    def test_healthcheck_catches_invalid_verification_states(self) -> None:
        original_session = discovery_healthcheck.SessionLocal
        discovery_healthcheck.SessionLocal = self.SessionLocal
        db = self.SessionLocal()
        try:
            candidate = self._candidate(db)
            db.commit()
            db.execute(text("PRAGMA ignore_check_constraints = ON"))
            candidate.verification_status = "mystery"
            candidate.auto_admit_eligible = True
            db.commit()
            payload = discovery_healthcheck.run_healthcheck()
        finally:
            db.close()
            discovery_healthcheck.SessionLocal = original_session

        self.assertTrue(any("invalid verification_status" in error for error in payload["errors"]))
        self.assertTrue(any("auto_admit_eligible without eligible" in error for error in payload["errors"]))


if __name__ == "__main__":
    unittest.main()
