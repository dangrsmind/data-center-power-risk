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

from app.models import Base  # noqa: E402
from app.models.project import Project  # noqa: E402
from load_demo_dataset import LoadSummary, load_demo_dataset, load_rows  # noqa: E402


VALID_CSV = """canonical_name,developer,project_type,city,county,state,utility,iso_region,load_mw,load_bucket,announced_date,expected_online_date,lifecycle_state,source_url,source_title,source_type,evidence_excerpt,latitude,longitude,coordinate_status,coordinate_precision,coordinate_source,coordinate_confidence,coordinate_notes
Demo Campus,Demo Developer,data_center,Demo City,Demo County,VA,,PJM,100,100 MW,2026-01-01,,candidate_unverified,https://example.test/source,Demo source,developer_statement,Demo excerpt,37.1,-78.2,unverified,approximate,manual_capture,0.6,Reviewed manually
"""


class DemoDatasetLoaderTest(unittest.TestCase):
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

    def test_loader_creates_projects_and_preserves_coordinate_metadata(self) -> None:
        summary = LoadSummary()
        rows = load_rows(self._write_csv(VALID_CSV), summary)

        db = self.SessionLocal()
        try:
            load_demo_dataset(db, rows, summary)

            self.assertEqual(summary.rows_read, 1)
            self.assertEqual(summary.projects_created, 1)
            project = db.scalar(select(Project).where(Project.canonical_name == "Demo Campus"))
            self.assertIsNotNone(project)
            assert project is not None
            self.assertEqual(project.latitude, 37.1)
            self.assertEqual(project.longitude, -78.2)
            self.assertEqual(project.coordinate_status, "unverified")
            self.assertEqual(project.coordinate_precision, "approximate")
            self.assertEqual(project.coordinate_source, "manual_review")
            self.assertEqual(project.coordinate_confidence, 0.6)
            self.assertEqual(project.candidate_metadata_json["demo_dataset_id"], "demo_projects_v0_1")
        finally:
            db.close()

    def test_repeated_loader_run_does_not_duplicate_projects(self) -> None:
        rows = load_rows(self._write_csv(VALID_CSV), LoadSummary())

        db = self.SessionLocal()
        try:
            first = load_demo_dataset(db, rows, LoadSummary())
            second = load_demo_dataset(db, rows, LoadSummary())

            self.assertEqual(first.projects_created, 1)
            self.assertEqual(second.projects_created, 0)
            self.assertEqual(second.rows_skipped, 1)
            projects = db.scalars(select(Project).where(Project.canonical_name == "Demo Campus")).all()
            self.assertEqual(len(projects), 1)
        finally:
            db.close()

    def test_invalid_latitude_is_skipped(self) -> None:
        invalid_csv = VALID_CSV.replace("37.1,-78.2", "91,-78.2")
        summary = LoadSummary()
        rows = load_rows(self._write_csv(invalid_csv), summary)

        db = self.SessionLocal()
        try:
            load_demo_dataset(db, rows, summary)

            self.assertEqual(len(rows), 0)
            self.assertEqual(summary.rows_read, 1)
            self.assertEqual(summary.rows_skipped, 1)
            self.assertEqual(len(summary.validation_errors), 1)
            self.assertEqual(db.scalars(select(Project)).all(), [])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
