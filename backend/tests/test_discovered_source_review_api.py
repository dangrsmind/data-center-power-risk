from __future__ import annotations

import os
import tempfile
import unittest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.api.routes.discovered_sources import (
    get_discovered_source,
    list_discovered_sources,
    summarize_discovered_sources,
)
from app.models import Base
from app.models.discovered_source import DiscoveredSourceClaim, DiscoveredSourceRecord
from app.models.evidence import Claim, Evidence
from app.models.project import Project
from app.models.project_candidate import ProjectCandidate


class DiscoveredSourceReviewApiTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)
        Base.metadata.create_all(bind=self.engine)
        self._seed_sources()

    def tearDown(self) -> None:
        self.engine.dispose()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _seed_sources(self) -> None:
        db = self.SessionLocal()
        try:
            db.add_all(
                [
                    DiscoveredSourceRecord(
                        source_url="https://www.scc.virginia.gov/case-information/submit-public-comments/cases/pur-2026-00050",
                        source_title="Case Comments for PUR-2026-00050",
                        source_type="state_regulatory_dockets",
                        publisher="Virginia SCC",
                        geography="Virginia",
                        discovery_method="searchstax_query",
                        search_term="Virginia data center large load SCC",
                        snippet="Public comment form retained as fallback reference.",
                        case_number="PUR-2026-00050",
                        source_registry_id="virginia_scc_data_center_large_load_dockets",
                        adapter_id="virginia_scc",
                        discovery_run_id="run-a",
                        raw_metadata_json={
                            "source_url_quality": "public_comment_form",
                            "url_quality_warning": "weak public-comment fallback",
                            "alternate_urls": ["https://www.scc.virginia.gov/docketsearch#/caseDetails/1"],
                        },
                        status="discovered",
                    ),
                    DiscoveredSourceRecord(
                        source_url="https://example.gov/planning/data-center-agenda",
                        source_title="Planning agenda for data center substation",
                        source_type="county_record",
                        publisher="Example County",
                        geography="Virginia",
                        discovery_method="web_search_pattern",
                        search_term="county data center substation agenda",
                        snippet="Agenda mentions substation review for a proposed data center.",
                        source_registry_id="county_planning_minutes",
                        adapter_id="generic_web_search",
                        discovery_run_id="run-b",
                        raw_metadata_json={"source_url_quality": "primary_source"},
                        status="candidate",
                    ),
                    DiscoveredSourceRecord(
                        source_url="https://example.gov/fallback/reference",
                        source_title="Fallback reference for utility large load",
                        source_type="utility_large_load_filings",
                        publisher="Example Utility",
                        geography="Texas",
                        discovery_method="web_search_pattern",
                        search_term="Texas utility large load filing data center",
                        snippet="Reference retained only as fallback provenance.",
                        source_registry_id="generic_utility_large_load_filing_search",
                        adapter_id="generic_web_search",
                        discovery_run_id="run-c",
                        raw_metadata_json={
                            "source_url_quality": "fallback_reference",
                            "url_quality_warning": "fallback URL needs analyst review",
                        },
                        status="discovered",
                    ),
                ]
            )
            db.commit()
        finally:
            db.close()

    def _counts(self) -> dict[str, int]:
        db = self.SessionLocal()
        try:
            return {
                "sources": db.scalar(select(func.count()).select_from(DiscoveredSourceRecord)),
                "projects": db.scalar(select(func.count()).select_from(Project)),
                "evidence": db.scalar(select(func.count()).select_from(Evidence)),
                "claims": db.scalar(select(func.count()).select_from(Claim)),
                "discovered_source_claims": db.scalar(select(func.count()).select_from(DiscoveredSourceClaim)),
                "project_candidates": db.scalar(select(func.count()).select_from(ProjectCandidate)),
            }
        finally:
            db.close()

    def test_list_endpoint_returns_bounded_review_items_without_raw_metadata(self) -> None:
        db = self.SessionLocal()
        try:
            response = list_discovered_sources(limit=50, offset=0, db=db)
        finally:
            db.close()

        self.assertEqual(response.total, 3)
        self.assertEqual(response.limit, 50)
        self.assertEqual(response.offset, 0)
        self.assertFalse(hasattr(response.items[0], "raw_metadata_json"))
        weak = next(item for item in response.items if item.source_url_quality == "public_comment_form")
        self.assertEqual(weak.source_query, "Virginia data center large load SCC")
        self.assertEqual(weak.url_quality_warning, "weak public-comment fallback")
        self.assertEqual(weak.alternate_urls, ["https://www.scc.virginia.gov/docketsearch#/caseDetails/1"])

    def test_filters_search_limit_and_offset_are_applied(self) -> None:
        db = self.SessionLocal()
        try:
            response = list_discovered_sources(
                adapter_id="generic_web_search",
                source_type="county_record",
                geography="Virginia",
                q="substation",
                limit=1,
                offset=0,
                db=db,
            )
        finally:
            db.close()

        self.assertEqual(response.total, 1)
        self.assertEqual(len(response.items), 1)
        self.assertEqual(response.items[0].adapter_id, "generic_web_search")
        self.assertEqual(response.applied_filters["q"], "substation")

    def test_quality_filters_and_summary_report_weak_sources(self) -> None:
        db = self.SessionLocal()
        try:
            weak_response = list_discovered_sources(has_weak_url_quality=True, limit=50, offset=0, db=db)
            quality_response = list_discovered_sources(source_url_quality="primary_source", limit=50, offset=0, db=db)
            summary = summarize_discovered_sources(db=db)
        finally:
            db.close()

        self.assertEqual(weak_response.total, 2)
        self.assertEqual(quality_response.total, 1)
        self.assertEqual(summary.total, 3)
        self.assertEqual(summary.weak_url_quality_count, 2)
        self.assertEqual(len(summary.weak_url_quality_examples), 2)
        self.assertEqual(summary.counts_by_status, {"candidate": 1, "discovered": 2})
        self.assertEqual(summary.counts_by_discovery_run_id, {"run-a": 1, "run-b": 1, "run-c": 1})

    def test_single_record_endpoint_includes_raw_metadata(self) -> None:
        db = self.SessionLocal()
        try:
            listed = list_discovered_sources(source_url_quality="public_comment_form", limit=50, offset=0, db=db)
            source_id = listed.items[0].id
            response = get_discovered_source(source_id, db=db)
        finally:
            db.close()

        self.assertEqual(response.id, source_id)
        self.assertEqual(response.raw_metadata_json["source_url_quality"], "public_comment_form")

    def test_review_endpoints_do_not_create_downstream_records(self) -> None:
        before = self._counts()

        db = self.SessionLocal()
        try:
            list_discovered_sources(limit=50, offset=0, db=db)
            summarize_discovered_sources(db=db)
        finally:
            db.close()

        self.assertEqual(self._counts(), before)
        self.assertEqual(before["sources"], 3)
        self.assertEqual({key: value for key, value in before.items() if key != "sources"}, {
            "projects": 0,
            "evidence": 0,
            "claims": 0,
            "discovered_source_claims": 0,
            "project_candidates": 0,
        })


if __name__ == "__main__":
    unittest.main()
