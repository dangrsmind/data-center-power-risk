from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = BACKEND_DIR / "tests" / "fixtures"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

from app.models import Base  # noqa: E402
from app.models.discovered_source import DiscoveredSourceRecord  # noqa: E402
from app.services.discovered_source_service import (  # noqa: E402
    DiscoveredSourceService,
    validate_discovered_source_row,
)
from discovery_healthcheck import run_healthcheck  # noqa: E402
from ingest_public_discovered_sources import load_discovered_source_rows  # noqa: E402


class PublicDiscoveredSourceIngestionTest(unittest.TestCase):
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

    def _rows(self) -> list[dict]:
        return json.loads((FIXTURES_DIR / "public_discovered_sources.json").read_text())

    def test_discovered_source_validation_preserves_unknown_fields(self) -> None:
        validated = validate_discovered_source_row(self._rows()[0], row_number=1, discovery_run_id="run-fixture")

        self.assertEqual(validated.source_url, self._rows()[0]["source_url"])
        self.assertEqual(validated.search_term, "data center")
        self.assertEqual(validated.discovery_run_id, "run-fixture")
        self.assertEqual(validated.raw_metadata_json["extra_fixture_field"], "preserved")

    def test_invalid_url_and_confidence_are_reported_not_raised_by_ingest(self) -> None:
        rows = [
            {"source_url": "not-a-url", "source_type": "state_regulatory_dockets"},
            {"source_url": "https://example.test/source", "source_type": "state_regulatory_dockets", "confidence": 1.5},
        ]
        db = self.SessionLocal()
        try:
            summary = DiscoveredSourceService(db).ingest_rows(rows)
            db.commit()
        finally:
            db.close()

        self.assertEqual(summary.rows_read, 2)
        self.assertEqual(summary.sources_created, 0)
        self.assertEqual(summary.rows_skipped, 2)
        self.assertEqual(len(summary.validation_errors), 2)

    def test_upsert_idempotency_skips_existing_without_duplicates(self) -> None:
        db = self.SessionLocal()
        try:
            service = DiscoveredSourceService(db)
            first = service.ingest_rows(self._rows())
            db.commit()
            second = service.ingest_rows(self._rows())
            db.commit()
            count = db.scalar(select(func.count()).select_from(DiscoveredSourceRecord))
        finally:
            db.close()

        self.assertEqual(first.sources_created, 2)
        self.assertEqual(second.sources_created, 0)
        self.assertEqual(second.rows_skipped, 2)
        self.assertEqual(count, 2)

    def test_allow_existing_updates_existing_row(self) -> None:
        rows = self._rows()
        db = self.SessionLocal()
        try:
            service = DiscoveredSourceService(db)
            service.ingest_rows(rows)
            db.commit()
            rows[0]["source_title"] = "Updated title"
            summary = service.ingest_rows(rows[:1], allow_existing=True)
            db.commit()
            record = db.scalar(select(DiscoveredSourceRecord).where(DiscoveredSourceRecord.source_url == rows[0]["source_url"]))
        finally:
            db.close()

        self.assertEqual(summary.sources_updated, 1)
        self.assertIsNotNone(record)
        self.assertEqual(record.source_title, "Updated title")

    def test_load_discovered_source_rows_fixture(self) -> None:
        rows, context = load_discovered_source_rows(FIXTURES_DIR / "public_discovered_sources.json")

        self.assertEqual(len(rows), 2)
        self.assertEqual(context["adapter_id"], None)

    def test_discovery_healthcheck_counts_rows(self) -> None:
        import discovery_healthcheck

        original_session = discovery_healthcheck.SessionLocal
        original_create = discovery_healthcheck.create_db_and_tables
        discovery_healthcheck.SessionLocal = self.SessionLocal
        discovery_healthcheck.create_db_and_tables = lambda: Base.metadata.create_all(bind=self.engine)
        db = self.SessionLocal()
        try:
            DiscoveredSourceService(db).ingest_rows(self._rows())
            db.commit()
            payload = run_healthcheck()
        finally:
            db.close()
            discovery_healthcheck.SessionLocal = original_session
            discovery_healthcheck.create_db_and_tables = original_create

        self.assertEqual(payload["discovered_sources_checked"], 2)
        self.assertEqual(payload["errors"], [])


if __name__ == "__main__":
    unittest.main()
