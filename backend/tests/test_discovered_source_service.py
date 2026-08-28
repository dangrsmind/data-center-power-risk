from __future__ import annotations

import unittest

from app.services.discovered_source_service import is_weak_scc_public_comment_form


class DiscoveredSourceServiceTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
