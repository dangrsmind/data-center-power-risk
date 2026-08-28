from __future__ import annotations

import json
import os
import subprocess
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
from app.models.discovered_source import DiscoveredSourceClaim, DiscoveredSourceRecord  # noqa: E402
from app.models.evidence import Claim, Evidence  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.project_candidate import ProjectCandidate  # noqa: E402
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
        self.assertEqual(validated.source_registry_id, "virginia_scc_data_center_large_load_dockets")
        self.assertEqual(validated.adapter_id, "virginia_scc")
        self.assertEqual(validated.raw_metadata_json["extra_fixture_field"], "preserved")

    def test_invalid_url_confidence_and_missing_provenance_are_reported_not_raised_by_ingest(self) -> None:
        rows = [
            {"source_url": "not-a-url", "source_type": "state_regulatory_dockets"},
            {"source_url": "https://example.test/source", "source_type": "state_regulatory_dockets", "confidence": 1.5},
            {
                "source_url": "https://example.test/missing-provenance",
                "source_title": "Missing provenance",
                "source_type": "state_regulatory_dockets",
                "geography": "Virginia",
                "discovery_method": "searchstax_query",
            },
        ]
        db = self.SessionLocal()
        try:
            summary = DiscoveredSourceService(db).ingest_rows(rows)
            db.commit()
        finally:
            db.close()

        self.assertEqual(summary.rows_read, 3)
        self.assertEqual(summary.sources_created, 0)
        self.assertEqual(summary.rows_skipped, 3)
        self.assertEqual(len(summary.validation_errors), 3)
        self.assertTrue(any("source_registry_id" in error["message"] for error in summary.validation_errors))

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
        self.assertEqual(second.duplicate_existing_urls_skipped, 2)
        self.assertEqual(count, 2)

    def test_duplicate_source_urls_within_one_batch_are_skipped_before_insert(self) -> None:
        rows = self._rows()
        duplicate = dict(rows[0])
        duplicate["source_title"] = "Duplicate later title"
        db = self.SessionLocal()
        try:
            summary = DiscoveredSourceService(db).ingest_rows([rows[0], duplicate, rows[1]])
            db.commit()
            records = list(db.scalars(select(DiscoveredSourceRecord).order_by(DiscoveredSourceRecord.source_url)))
        finally:
            db.close()

        self.assertEqual(summary.rows_read, 3)
        self.assertEqual(summary.sources_created, 2)
        self.assertEqual(summary.rows_skipped, 1)
        self.assertEqual(summary.duplicate_input_urls_skipped, 1)
        self.assertEqual(summary.duplicate_existing_urls_skipped, 0)
        self.assertEqual(len(records), 2)
        self.assertTrue(any(record.source_title == rows[0]["source_title"] for record in records))
        self.assertFalse(any(record.source_title == "Duplicate later title" for record in records))

    def test_mixed_batch_with_existing_and_new_urls_creates_only_new_rows(self) -> None:
        rows = self._rows()
        new_row = dict(rows[0])
        new_row["source_url"] = "https://planning.example.gov/agendas/new-data-center.html"
        new_row["source_title"] = "New data center planning agenda"
        db = self.SessionLocal()
        try:
            service = DiscoveredSourceService(db)
            service.ingest_rows(rows[:1])
            db.commit()
            summary = service.ingest_rows([rows[0], new_row])
            db.commit()
            count = db.scalar(select(func.count()).select_from(DiscoveredSourceRecord))
            project_count = db.scalar(select(func.count()).select_from(Project))
        finally:
            db.close()

        self.assertEqual(summary.rows_read, 2)
        self.assertEqual(summary.sources_created, 1)
        self.assertEqual(summary.rows_skipped, 1)
        self.assertEqual(summary.duplicate_existing_urls_skipped, 1)
        self.assertEqual(count, 2)
        self.assertEqual(project_count, 0)

    def test_dry_run_ingest_reports_would_create_and_writes_nothing(self) -> None:
        db = self.SessionLocal()
        try:
            summary = DiscoveredSourceService(db).ingest_rows(self._rows(), dry_run=True)
            counts = {
                "sources": db.scalar(select(func.count()).select_from(DiscoveredSourceRecord)),
                "projects": db.scalar(select(func.count()).select_from(Project)),
                "evidence": db.scalar(select(func.count()).select_from(Evidence)),
                "claims": db.scalar(select(func.count()).select_from(Claim)),
                "discovered_source_claims": db.scalar(select(func.count()).select_from(DiscoveredSourceClaim)),
                "project_candidates": db.scalar(select(func.count()).select_from(ProjectCandidate)),
            }
        finally:
            db.close()

        payload = summary.to_dict()
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["would_create"], 2)
        self.assertEqual(summary.sources_created, 2)
        self.assertEqual(summary.weak_scc_public_comment_form_count, 1)
        self.assertTrue(summary.weak_scc_public_comment_form_rows)
        self.assertEqual(counts, {key: 0 for key in counts})

    def test_confirmed_ingest_writes_only_discovered_source_rows(self) -> None:
        db = self.SessionLocal()
        try:
            summary = DiscoveredSourceService(db).ingest_rows(self._rows())
            db.commit()
            counts = {
                "sources": db.scalar(select(func.count()).select_from(DiscoveredSourceRecord)),
                "projects": db.scalar(select(func.count()).select_from(Project)),
                "evidence": db.scalar(select(func.count()).select_from(Evidence)),
                "claims": db.scalar(select(func.count()).select_from(Claim)),
                "discovered_source_claims": db.scalar(select(func.count()).select_from(DiscoveredSourceClaim)),
                "project_candidates": db.scalar(select(func.count()).select_from(ProjectCandidate)),
            }
        finally:
            db.close()

        self.assertEqual(summary.sources_created, 2)
        self.assertEqual(counts["sources"], 2)
        self.assertEqual({key: value for key, value in counts.items() if key != "sources"}, {
            "projects": 0,
            "evidence": 0,
            "claims": 0,
            "discovered_source_claims": 0,
            "project_candidates": 0,
        })

    def test_dry_run_reports_existing_and_allow_existing_update_counts(self) -> None:
        rows = self._rows()
        db = self.SessionLocal()
        try:
            service = DiscoveredSourceService(db)
            service.ingest_rows(rows[:1])
            db.commit()
            default_summary = service.ingest_rows(rows, dry_run=True)
            update_summary = service.ingest_rows(rows[:1], dry_run=True, allow_existing=True)
            count = db.scalar(select(func.count()).select_from(DiscoveredSourceRecord))
        finally:
            db.close()

        self.assertEqual(default_summary.to_dict()["would_create"], 1)
        self.assertEqual(default_summary.to_dict()["would_skip_existing"], 1)
        self.assertEqual(default_summary.to_dict()["would_update_existing"], 0)
        self.assertEqual(update_summary.to_dict()["would_update_existing"], 1)
        self.assertEqual(count, 1)

    def test_cli_requires_dry_run_or_confirm_before_writing(self) -> None:
        env = dict(os.environ)
        env["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        result = subprocess.run(
            [
                sys.executable,
                "scripts/ingest_public_discovered_sources.py",
                "--input",
                str(FIXTURES_DIR / "public_discovered_sources.json"),
            ],
            cwd=BACKEND_DIR,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("requires --dry-run or explicit --confirm", result.stderr)

    def test_cli_dry_run_reports_weak_urls_and_writes_nothing(self) -> None:
        env = dict(os.environ)
        env["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        result = subprocess.run(
            [
                sys.executable,
                "scripts/ingest_public_discovered_sources.py",
                "--input",
                str(FIXTURES_DIR / "public_discovered_sources.json"),
                "--dry-run",
            ],
            cwd=BACKEND_DIR,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        db = self.SessionLocal()
        try:
            count = db.scalar(select(func.count()).select_from(DiscoveredSourceRecord))
        finally:
            db.close()

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["rows_read"], 2)
        self.assertEqual(payload["would_create"], 2)
        self.assertEqual(payload["weak_scc_public_comment_form_count"], 1)
        self.assertEqual(count, 0)

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

    def test_allow_existing_does_not_overwrite_existing_status(self) -> None:
        rows = self._rows()
        db = self.SessionLocal()
        try:
            service = DiscoveredSourceService(db)
            service.ingest_rows(rows[:1])
            db.commit()
            record = db.scalar(select(DiscoveredSourceRecord).where(DiscoveredSourceRecord.source_url == rows[0]["source_url"]))
            record.status = "rejected"
            db.commit()
            incoming = dict(rows[0])
            incoming["status"] = "discovered"
            incoming["source_title"] = "Safe metadata update"
            summary = service.ingest_rows([incoming], allow_existing=True)
            db.commit()
            db.refresh(record)
        finally:
            db.close()

        self.assertEqual(summary.sources_updated, 1)
        self.assertEqual(record.status, "rejected")
        self.assertEqual(record.source_title, "Safe metadata update")

    def test_load_discovered_source_rows_fixture(self) -> None:
        rows, context = load_discovered_source_rows(FIXTURES_DIR / "public_discovered_sources.json")

        self.assertEqual(len(rows), 2)
        self.assertEqual(context["adapter_id"], None)

    def test_discovery_healthcheck_counts_rows(self) -> None:
        import discovery_healthcheck

        original_session = discovery_healthcheck.SessionLocal
        discovery_healthcheck.SessionLocal = self.SessionLocal
        db = self.SessionLocal()
        try:
            DiscoveredSourceService(db).ingest_rows(self._rows())
            db.commit()
            payload = run_healthcheck()
        finally:
            db.close()
            discovery_healthcheck.SessionLocal = original_session

        self.assertEqual(payload["discovered_sources_checked"], 2)
        self.assertEqual(payload["errors"], [])


if __name__ == "__main__":
    unittest.main()
