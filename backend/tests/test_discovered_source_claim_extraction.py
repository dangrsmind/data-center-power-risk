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

from app.models import Base  # noqa: E402
from app.models.discovered_source import DiscoveredSourceClaim, DiscoveredSourceRecord  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.services.discovered_source_claim_extractor import (  # noqa: E402
    DiscoveredSourceClaimExtractor,
    DiscoveredSourceClaimService,
)


class DiscoveredSourceClaimExtractionTest(unittest.TestCase):
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
            "source_title": "Case title: Application for 300 MW data center electric service agreement",
            "source_type": "state_regulatory_dockets",
            "publisher": "Virginia State Corporation Commission",
            "geography": "Virginia",
            "discovery_method": "searchstax_query",
            "confidence": "candidate_discovered",
            "search_term": "data center",
            "snippet": "Case No. PUR-2026-00022 concerns a clear 300 MW large load request.",
            "case_number": "PUR-2026-00022",
            "document_type": "case",
            "status": "discovered",
        }
        defaults.update(kwargs)
        return DiscoveredSourceRecord(**defaults)

    def test_rule_based_extraction_from_title_and_snippet(self) -> None:
        db = self.SessionLocal()
        try:
            source = self._source()
            db.add(source)
            db.flush()

            claims = DiscoveredSourceClaimExtractor().extract(source)
            by_type = {claim.claim_type: claim for claim in claims}
        finally:
            db.close()

        self.assertEqual(by_type["case_number"].claim_value, "PUR-2026-00022")
        self.assertEqual(by_type["document_type"].claim_value, "case")
        self.assertEqual(by_type["state"].claim_value, "Virginia")
        self.assertEqual(by_type["load_mw"].claim_value, "300")
        self.assertEqual(by_type["load_mw"].claim_unit, "MW")
        self.assertIn("general_relevance", by_type)

    def test_mw_extraction_only_when_pattern_is_clear(self) -> None:
        db = self.SessionLocal()
        try:
            vague = self._source(
                source_url="https://www.scc.virginia.gov/example/vague",
                source_title="Data center load growth discussion",
                snippet="The filing discusses 300 customers and significant load.",
                case_number=None,
                document_type=None,
            )
            db.add(vague)
            db.flush()

            claims = DiscoveredSourceClaimExtractor().extract(vague)
        finally:
            db.close()

        self.assertNotIn("load_mw", {claim.claim_type for claim in claims})

    def test_no_project_creation_and_idempotent_repeated_extraction(self) -> None:
        db = self.SessionLocal()
        try:
            db.add(self._source())
            db.commit()

            service = DiscoveredSourceClaimService(db)
            first = service.extract_claims()
            db.commit()
            second = service.extract_claims()
            db.commit()
            project_count = db.scalar(select(func.count()).select_from(Project))
            claim_count = db.scalar(select(func.count()).select_from(DiscoveredSourceClaim))
        finally:
            db.close()

        self.assertGreater(first.claims_created, 0)
        self.assertEqual(second.claims_created, 0)
        self.assertEqual(second.claims_updated, claim_count)
        self.assertEqual(project_count, 0)

    def test_dry_run_does_not_write(self) -> None:
        db = self.SessionLocal()
        try:
            db.add(self._source())
            db.commit()

            summary = DiscoveredSourceClaimService(db).extract_claims(dry_run=True)
            db.commit()
            claim_count = db.scalar(select(func.count()).select_from(DiscoveredSourceClaim))
        finally:
            db.close()

        self.assertGreater(summary.claims_created, 0)
        self.assertEqual(claim_count, 0)

    def test_low_information_source_warns_without_crashing(self) -> None:
        db = self.SessionLocal()
        try:
            db.add(
                self._source(
                    source_url="https://example.test/about",
                    source_title="About",
                    snippet=None,
                    publisher=None,
                    geography=None,
                    search_term=None,
                    case_number=None,
                    document_type=None,
                )
            )
            db.commit()

            summary = DiscoveredSourceClaimService(db).extract_claims()
        finally:
            db.close()

        self.assertEqual(summary.claims_created, 0)
        self.assertTrue(any("no_claims_extracted" in warning for warning in summary.warnings))


if __name__ == "__main__":
    unittest.main()
