from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.enums import ClaimEntityType, ReviewerStatus  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.evidence import Evidence, FieldProvenance  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.project_candidate import ProjectCandidate  # noqa: E402
from app.services.project_candidate_promotion import ProjectCandidatePromotionService  # noqa: E402


class ProjectCandidatePromotionTest(unittest.TestCase):
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

    def _candidate(self, **kwargs) -> ProjectCandidate:
        defaults = {
            "candidate_key": "candidate-key-1",
            "candidate_name": "Example Data Center Campus",
            "developer": "Example Developer",
            "state": "Virginia",
            "county": "Example County",
            "city": "Example City",
            "utility": "Example Utility",
            "load_mw": 300.0,
            "lifecycle_state": "candidate_unverified",
            "confidence": 0.8,
            "status": "candidate",
            "source_count": 1,
            "claim_count": 4,
            "primary_source_url": "https://www.scc.virginia.gov/case/example",
            "discovered_source_ids_json": ["00000000-0000-0000-0000-000000000001"],
            "discovered_source_claim_ids_json": ["00000000-0000-0000-0000-000000000002"],
            "evidence_excerpt": "Explicit source-backed evidence excerpt.",
            "raw_metadata_json": {"source_titles": ["Virginia SCC example docket"]},
        }
        defaults.update(kwargs)
        return ProjectCandidate(**defaults)

    def test_dry_run_creates_no_project(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate()
            db.add(candidate)
            db.commit()
            summary = ProjectCandidatePromotionService(db).promote(candidate.id)
            project_count = db.scalar(select(func.count()).select_from(Project))
        finally:
            db.close()

        self.assertTrue(summary.dry_run)
        self.assertTrue(summary.promoted)
        self.assertEqual(project_count, 0)

    def test_confirm_promotes_one_candidate_with_evidence(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate()
            db.add(candidate)
            db.commit()
            summary = ProjectCandidatePromotionService(db).promote(candidate.id, confirm=True)
            db.commit()
            project = db.scalar(select(Project))
            evidence = db.scalar(select(Evidence))
            provenance = db.scalar(select(FieldProvenance))
            db.refresh(candidate)
        finally:
            db.close()

        self.assertTrue(summary.promoted)
        self.assertTrue(summary.project_created)
        self.assertEqual(summary.evidence_created, 1)
        self.assertEqual(candidate.status, "promoted")
        self.assertEqual(candidate.promoted_project_id, project.id)
        self.assertEqual(project.canonical_name, "Example Data Center Campus")
        self.assertEqual(project.state, "VA")
        self.assertEqual(project.county, "Example County")
        self.assertEqual(project.candidate_metadata_json["utility"], "Example Utility")
        self.assertEqual(project.candidate_metadata_json["load_mw"], 300.0)
        self.assertEqual(evidence.reviewer_status, ReviewerStatus.REVIEWED)
        self.assertEqual(evidence.source_url, "https://www.scc.virginia.gov/case/example")
        self.assertEqual(provenance.entity_type, ClaimEntityType.PROJECT)
        self.assertEqual(provenance.entity_id, project.id)

    def test_repeated_promotion_does_not_duplicate_projects(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate()
            db.add(candidate)
            db.commit()
            first = ProjectCandidatePromotionService(db).promote(candidate.id, confirm=True)
            db.commit()
            second = ProjectCandidatePromotionService(db).promote(candidate.id, confirm=True)
            db.commit()
            project_count = db.scalar(select(func.count()).select_from(Project))
            evidence_count = db.scalar(select(func.count()).select_from(Evidence))
        finally:
            db.close()

        self.assertTrue(first.project_created)
        self.assertIn("candidate_already_promoted", second.warnings)
        self.assertEqual(project_count, 1)
        self.assertEqual(evidence_count, 1)

    def test_missing_source_url_blocks_promotion(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(primary_source_url=None)
            db.add(candidate)
            db.commit()
            summary = ProjectCandidatePromotionService(db).promote(candidate.id, confirm=True)
            project_count = db.scalar(select(func.count()).select_from(Project))
        finally:
            db.close()

        self.assertIn("candidate_missing_primary_source_url", summary.errors)
        self.assertEqual(project_count, 0)

    def test_unresolved_name_blocks_unless_override_is_set(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(candidate_name="Unresolved Virginia SCC candidate abc123")
            db.add(candidate)
            db.commit()
            blocked = ProjectCandidatePromotionService(db).promote(candidate.id, confirm=True)
            allowed = ProjectCandidatePromotionService(db).promote(
                candidate.id,
                confirm=True,
                allow_unresolved_name=True,
            )
            db.commit()
            project_count = db.scalar(select(func.count()).select_from(Project))
        finally:
            db.close()

        self.assertIn("candidate_name_unresolved", blocked.errors)
        self.assertTrue(allowed.promoted)
        self.assertEqual(project_count, 1)

    def test_missing_state_blocks_unless_incomplete_override_is_set(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self._candidate(state=None)
            db.add(candidate)
            db.commit()
            blocked = ProjectCandidatePromotionService(db).promote(candidate.id, confirm=True)
            allowed = ProjectCandidatePromotionService(db).promote(
                candidate.id,
                confirm=True,
                allow_incomplete=True,
            )
            db.commit()
        finally:
            db.close()

        self.assertIn("candidate_missing_state", blocked.errors)
        self.assertTrue(allowed.promoted)


if __name__ == "__main__":
    unittest.main()
