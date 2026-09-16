from __future__ import annotations

import unittest

from app.models.discovered_source import DiscoveredSourceRecord
from app.services.discovered_source_service import DiscoveredSourceService, is_weak_scc_public_comment_form, review_priority


class DiscoveredSourceServiceTest(unittest.TestCase):
    def test_review_noops_preserve_audit_timestamp(self) -> None:
        from datetime import datetime, timezone
        stamp = datetime(2020, 1, 1, tzinfo=timezone.utc)
        record = DiscoveredSourceRecord(review_status="unreviewed", review_notes="Notes", reviewed_by="Analyst", reviewed_at=stamp)
        for fields in ({}, {"review_status": None}, {"review_status": "unreviewed"},
                       {"review_notes": " Notes "}, {"reviewed_by": " Analyst "},
                       {"note_mode": "append", "review_notes": " "}):
            DiscoveredSourceService._apply_review_update(record, **fields)
            self.assertEqual(record.reviewed_at, stamp)
            self.assertEqual(record.review_notes, "Notes")
            self.assertEqual(record.reviewed_by, "Analyst")
        DiscoveredSourceService._apply_review_update(record, review_notes=None)
        self.assertIsNone(record.review_notes)
        self.assertGreater(record.reviewed_at, stamp)

    def test_weak_scc_public_comment_form_detection(self) -> None:
        self.assertTrue(
            is_weak_scc_public_comment_form(
                {
                    "source_url": (
                        "https://www.scc.virginia.gov/case-information/submit-public-comments/"
                        "cases/pur-2026-00050.html"
                    ),
                    "source_title": "Case Comments for PUR-2026-00050",
                    "raw_metadata_json": {"source_url_quality": "public_comment_form"},
                }
            )
        )

    def test_non_scc_primary_evidence_is_not_weak_public_comment_form(self) -> None:
        self.assertFalse(
            is_weak_scc_public_comment_form(
                {
                    "source_url": "https://www.scc.virginia.gov/docketsearch#/caseDetails/144/345",
                    "source_title": "PUR-2026-00050 electric service agreement",
                    "raw_metadata_json": {"source_url_quality": "docket_case_detail"},
                }
            )
        )

    def test_review_priority_scores_official_filings_above_generic_pages(self) -> None:
        official = DiscoveredSourceRecord(
            source_url="https://www.scc.virginia.gov/docketsearch#/caseDetails/144/345",
            source_title="PUR-2026-00050 data center large load hearing",
            source_type="state_regulatory_dockets",
            publisher="Virginia SCC",
            geography="Virginia",
            discovery_method="searchstax_query",
            search_term="data center large load docket",
            snippet="State regulatory docket for a data center large load interconnection hearing.",
            source_registry_id="virginia_scc_data_center_large_load_dockets",
            adapter_id="virginia_scc",
            discovery_run_id="20260828T193254Z",
            raw_metadata_json={"source_url_quality": "docket_case_detail"},
            status="discovered",
        )
        generic = DiscoveredSourceRecord(
            source_url="https://example.com/",
            source_title="Home",
            source_type="press",
            publisher="Example",
            geography="unknown",
            discovery_method="web_search_pattern",
            search_term="homepage",
            snippet="Short.",
            source_registry_id="unknown",
            adapter_id="unknown",
            discovery_run_id="unknown",
            raw_metadata_json={},
            status="discovered",
        )

        self.assertGreater(review_priority(official).score, review_priority(generic).score)
        self.assertEqual(review_priority(official).bucket, "high_signal_official")
        self.assertEqual(review_priority(generic).bucket, "likely_noise")


if __name__ == "__main__":
    unittest.main()
