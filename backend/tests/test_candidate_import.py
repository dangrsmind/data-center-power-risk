from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import Base  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.services.candidate_import_service import CandidateImportService  # noqa: E402


class CandidateImportServiceTest(unittest.TestCase):
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

    def test_csv_import_creates_and_rejects_rows(self) -> None:
        csv_payload = """candidate_id,canonical_name,developer,operator,state,county,region_hint,utility_hint,known_load_mw,load_note,priority_tier,source_1_url,source_1_type,notes
CAND_001,Example AI Campus,Example Dev,,TX,Ellis,ERCOT,Oncor,300,First tranche,A,https://example.com/source-1,developer_statement,High priority
CAND_002,,Missing Name Dev,,VA,Prince Edward,PJM,Dominion,300,Needs follow-up,B,https://example.com/source-2,county_record,Missing canonical name
"""
        db = self.SessionLocal()
        try:
            response = CandidateImportService(db).import_payload(csv_payload.encode("utf-8"), "text/csv")

            self.assertEqual(len(response.created), 1)
            self.assertEqual(len(response.rejected), 1)
            self.assertEqual(response.created[0].canonical_name, "Example AI Campus")
            self.assertEqual(response.rejected[0].message, "canonical_name and state are required")

            project = db.query(Project).filter(Project.canonical_name == "Example AI Campus").one()
            self.assertEqual(project.state, "TX")
            self.assertEqual(project.county, "Ellis")
            self.assertEqual(project.candidate_metadata_json["region_hint"], "ERCOT")
            self.assertEqual(project.candidate_metadata_json["known_load_mw"], 300.0)
            self.assertEqual(project.candidate_metadata_json["sources"][0]["source_type"], "developer_statement")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
