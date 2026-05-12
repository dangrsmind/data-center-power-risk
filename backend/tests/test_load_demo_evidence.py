from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from app.core.enums import ClaimEntityType, ClaimReviewStatus, LifecycleState, ReviewerStatus  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.evidence import Claim, Evidence, FieldProvenance  # noqa: E402
from app.models.project import Project  # noqa: E402
from load_demo_evidence import LoadSummary, load_demo_evidence, load_rows  # noqa: E402


VALID_CSV = """canonical_name,state,evidence_type,source_url,source_title,source_publisher,published_date,evidence_excerpt,claim_type,claim_value,confidence,notes
Demo Campus,VA,developer_statement,https://example.test/source,Demo source,Demo Publisher,2026-01-01,Demo source excerpt.,developer_named,Demo Developer,0.8,Curated demo evidence.
"""


class DemoEvidenceLoaderTest(unittest.TestCase):
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

    def _write_csv(self, payload: str) -> Path:
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", suffix=".csv", delete=False)
        with handle:
            handle.write(payload)
        self.addCleanup(lambda: os.path.exists(handle.name) and os.remove(handle.name))
        return Path(handle.name)

    def _project(self, db) -> Project:
        project = Project(
            canonical_name="Demo Campus",
            developer=None,
            state="VA",
            county="Demo County",
            lifecycle_state=LifecycleState.CANDIDATE_UNVERIFIED,
            candidate_metadata_json={"demo_dataset_id": "demo_projects_v0_1"},
        )
        db.add(project)
        db.flush()
        return project

    def test_loader_creates_linked_evidence_claim_and_provenance(self) -> None:
        summary = LoadSummary()
        rows = load_rows(self._write_csv(VALID_CSV), summary)

        db = self.SessionLocal()
        try:
            project = self._project(db)
            summary = load_demo_evidence(db, rows, summary)

            evidence = db.scalar(select(Evidence))
            claim = db.scalar(select(Claim))
            provenance = db.scalar(select(FieldProvenance))

            self.assertEqual(summary.rows_read, 1)
            self.assertEqual(summary.evidence_created, 1)
            self.assertIsNotNone(evidence)
            assert evidence is not None
            self.assertEqual(evidence.reviewer_status, ReviewerStatus.REVIEWED)
            self.assertEqual(evidence.source_url, "https://example.test/source")
            self.assertIsNotNone(claim)
            assert claim is not None
            self.assertEqual(claim.entity_type, ClaimEntityType.PROJECT)
            self.assertEqual(claim.entity_id, project.id)
            self.assertEqual(claim.review_status, ClaimReviewStatus.ACCEPTED)
            self.assertEqual(claim.claim_value_json, {"developer_name": "Demo Developer"})
            self.assertIsNotNone(provenance)
            assert provenance is not None
            self.assertEqual(provenance.field_name, "developer")
            self.assertEqual(provenance.claim_id, claim.id)
        finally:
            db.close()

    def test_repeated_loader_run_updates_without_duplicates(self) -> None:
        rows = load_rows(self._write_csv(VALID_CSV), LoadSummary())

        db = self.SessionLocal()
        try:
            self._project(db)
            first = load_demo_evidence(db, rows, LoadSummary())
            second = load_demo_evidence(db, rows, LoadSummary())

            self.assertEqual(first.evidence_created, 1)
            self.assertEqual(second.evidence_created, 0)
            self.assertEqual(second.rows_skipped, 1)
            self.assertEqual(len(db.scalars(select(Evidence)).all()), 1)
            self.assertEqual(len(db.scalars(select(Claim)).all()), 1)
            self.assertEqual(len(db.scalars(select(FieldProvenance)).all()), 1)
        finally:
            db.close()

    def test_unmatched_project_is_skipped_and_reported(self) -> None:
        rows = load_rows(self._write_csv(VALID_CSV), LoadSummary())

        db = self.SessionLocal()
        try:
            summary = load_demo_evidence(db, rows, LoadSummary())

            self.assertEqual(summary.evidence_created, 0)
            self.assertEqual(summary.rows_skipped, 1)
            self.assertEqual(len(summary.validation_errors), 1)
            self.assertIn("no matching project", summary.validation_errors[0].reason)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
