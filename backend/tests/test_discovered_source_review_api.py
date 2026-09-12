from __future__ import annotations

import os
import tempfile
import unittest
import uuid

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.api.routes.discovered_sources import (
    bulk_update_discovered_source_review,
    get_discovered_source,
    list_discovered_sources,
    summarize_discovered_sources,
    update_discovered_source_review,
)
from app.schemas.discovered_source import DiscoveredSourceReviewBulkUpdate, DiscoveredSourceReviewUpdate
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
                        review_status="useful",
                        review_notes="Good planning source",
                        reviewed_by="analyst@example.com",
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
                    DiscoveredSourceRecord(
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

        self.assertEqual(response.total, 4)
        self.assertEqual(response.limit, 50)
        self.assertEqual(response.offset, 0)
        self.assertFalse(hasattr(response.items[0], "raw_metadata_json"))
        weak = next(item for item in response.items if item.source_url_quality == "public_comment_form")
        self.assertEqual(weak.source_query, "Virginia data center large load SCC")
        self.assertEqual(weak.url_quality_warning, "weak public-comment fallback")
        self.assertEqual(weak.alternate_urls, ["https://www.scc.virginia.gov/docketsearch#/caseDetails/1"])
        self.assertEqual(weak.review_status, "unreviewed")
        self.assertIsNone(weak.review_notes)
        self.assertIsInstance(weak.review_priority_score, int)
        self.assertEqual(weak.review_priority_bucket, "weak_url_review")
        self.assertTrue(any("weak URL quality" in reason for reason in weak.review_priority_reasons))
        useful = next(item for item in response.items if item.review_status == "useful")
        self.assertEqual(useful.review_notes, "Good planning source")
        self.assertEqual(useful.reviewed_by, "analyst@example.com")
        noisy = next(item for item in response.items if item.source_title == "Home")
        self.assertGreater(useful.review_priority_score, noisy.review_priority_score)

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
        self.assertEqual(summary.total, 4)
        self.assertEqual(summary.weak_url_quality_count, 2)
        self.assertEqual(len(summary.weak_url_quality_examples), 2)
        self.assertEqual(summary.counts_by_status, {"candidate": 1, "discovered": 3})
        self.assertEqual(summary.counts_by_discovery_run_id, {"run-a": 1, "run-b": 1, "run-c": 1, "unknown": 1})
        self.assertEqual(summary.counts_by_review_status, {"unreviewed": 3, "useful": 1})
        self.assertEqual(summary.counts_by_review_priority_bucket["weak_url_review"], 2)
        self.assertEqual(summary.counts_by_review_priority_bucket["likely_noise"], 1)
        self.assertEqual(len(summary.top_review_queue_examples), 3)
        self.assertLessEqual(len(summary.top_review_queue_examples), 10)
        self.assertEqual(
            [item.review_priority_score for item in summary.top_review_queue_examples],
            sorted([item.review_priority_score for item in summary.top_review_queue_examples], reverse=True),
        )
        self.assertEqual(summary.reviewed_count, 1)
        self.assertEqual(summary.unreviewed_count, 3)
        self.assertEqual(summary.useful_count, 1)
        self.assertEqual(summary.maybe_count, 0)
        self.assertEqual(summary.noisy_count, 0)
        self.assertEqual(summary.weak_count, 0)
        self.assertEqual(summary.rejected_count, 0)

    def test_review_filters_are_applied(self) -> None:
        db = self.SessionLocal()
        try:
            useful_response = list_discovered_sources(review_status="useful", limit=50, offset=0, db=db)
            notes_response = list_discovered_sources(has_review_notes=True, limit=50, offset=0, db=db)
            no_notes_response = list_discovered_sources(has_review_notes=False, limit=50, offset=0, db=db)
        finally:
            db.close()

        self.assertEqual(useful_response.total, 1)
        self.assertEqual(useful_response.items[0].review_status, "useful")
        self.assertEqual(notes_response.total, 1)
        self.assertEqual(no_notes_response.total, 3)

    def test_priority_filters_and_sort_are_applied(self) -> None:
        db = self.SessionLocal()
        try:
            high_response = list_discovered_sources(priority_bucket="high_signal_official", limit=50, offset=0, db=db)
            min_score_response = list_discovered_sources(min_priority_score=60, limit=50, offset=0, db=db)
            sorted_response = list_discovered_sources(sort="priority_desc", limit=50, offset=0, db=db)
        finally:
            db.close()

        self.assertEqual(high_response.total, 1)
        self.assertEqual(high_response.items[0].source_title, "Planning agenda for data center substation")
        self.assertTrue(all(item.review_priority_score >= 60 for item in min_score_response.items))
        self.assertEqual(
            [item.review_priority_score for item in sorted_response.items],
            sorted([item.review_priority_score for item in sorted_response.items], reverse=True),
        )
        self.assertLess(
            next(item.review_priority_score for item in sorted_response.items if item.source_title == "Home"),
            next(
                item.review_priority_score
                for item in sorted_response.items
                if item.source_title == "Planning agenda for data center substation"
            ),
        )

    def test_priority_reasons_include_unknown_provenance_penalty(self) -> None:
        db = self.SessionLocal()
        try:
            response = list_discovered_sources(q="homepage", limit=50, offset=0, db=db)
        finally:
            db.close()

        self.assertEqual(response.total, 1)
        self.assertEqual(response.items[0].review_priority_bucket, "likely_noise")
        self.assertTrue(
            any("unknown provenance" in reason for reason in response.items[0].review_priority_reasons)
        )

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

    def test_patch_updates_only_triage_fields_and_preserves_provenance(self) -> None:
        before_counts = self._counts()
        db = self.SessionLocal()
        try:
            listed = list_discovered_sources(source_url_quality="public_comment_form", limit=50, offset=0, db=db)
            source_id = listed.items[0].id
            before = get_discovered_source(source_id, db=db)
            response = update_discovered_source_review(
                source_id,
                DiscoveredSourceReviewUpdate(
                    review_status="weak",
                    review_notes="Weak source, keep only as fallback.",
                    reviewed_by="Analyst",
                ),
                db=db,
            )
            after = get_discovered_source(source_id, db=db)
        finally:
            db.close()

        self.assertEqual(response.review_status, "weak")
        self.assertEqual(response.review_notes, "Weak source, keep only as fallback.")
        self.assertEqual(response.reviewed_by, "Analyst")
        self.assertIsNotNone(response.reviewed_at)
        self.assertEqual(after.source_url, before.source_url)
        self.assertEqual(after.source_title, before.source_title)
        self.assertEqual(after.source_type, before.source_type)
        self.assertEqual(after.geography, before.geography)
        self.assertEqual(after.source_registry_id, before.source_registry_id)
        self.assertEqual(after.adapter_id, before.adapter_id)
        self.assertEqual(after.discovery_run_id, before.discovery_run_id)
        self.assertEqual(after.status, before.status)
        self.assertEqual(after.raw_metadata_json, before.raw_metadata_json)
        self.assertEqual(after.source_url_quality, "public_comment_form")
        self.assertEqual(after.review_status, "weak")
        self.assertEqual(self._counts(), before_counts)

    def test_bulk_patch_updates_multiple_sources_and_reports_items(self) -> None:
        before_counts = self._counts()
        db = self.SessionLocal()
        try:
            listed = list_discovered_sources(review_status="unreviewed", sort="priority_desc", limit=50, offset=0, db=db)
            source_ids = [item.id for item in listed.items[:2]]
            response = bulk_update_discovered_source_review(
                DiscoveredSourceReviewBulkUpdate(
                    source_ids=source_ids,
                    review_status="maybe",
                    review_notes="Bulk triage note",
                    reviewed_by="bulk analyst",
                ),
                db=db,
            )
            refreshed = list_discovered_sources(review_status="maybe", limit=50, offset=0, db=db)
        finally:
            db.close()

        self.assertEqual(response.requested_count, 2)
        self.assertEqual(response.updated_count, 2)
        self.assertEqual(response.missing_ids, [])
        self.assertEqual({item.id for item in response.items}, set(source_ids))
        self.assertTrue(all(item.review_status == "maybe" for item in response.items))
        self.assertTrue(all(item.review_notes == "Bulk triage note" for item in response.items))
        self.assertTrue(all(item.reviewed_by == "bulk analyst" for item in response.items))
        self.assertTrue(all(item.reviewed_at is not None for item in response.items))
        self.assertTrue(all(isinstance(item.review_priority_score, int) for item in response.items))
        self.assertGreaterEqual(refreshed.total, 2)
        self.assertEqual(self._counts(), before_counts)

    def test_bulk_patch_validates_review_status(self) -> None:
        db = self.SessionLocal()
        try:
            source_id = list_discovered_sources(limit=1, offset=0, db=db).items[0].id
            request = DiscoveredSourceReviewBulkUpdate.model_construct(
                source_ids=[source_id],
                review_status="bad_status",
                review_notes=None,
                reviewed_by=None,
                note_mode="replace",
            )
            with self.assertRaisesRegex(Exception, "422"):
                bulk_update_discovered_source_review(request, db=db)
        finally:
            db.close()

    def test_bulk_patch_enforces_max_source_ids_limit(self) -> None:
        with self.assertRaises(Exception):
            DiscoveredSourceReviewBulkUpdate(
                source_ids=[uuid.uuid4() for _ in range(201)],
                review_status="useful",
            )

    def test_bulk_patch_reports_missing_ids(self) -> None:
        missing_id = uuid.uuid4()
        db = self.SessionLocal()
        try:
            source_id = list_discovered_sources(limit=1, offset=0, db=db).items[0].id
            response = bulk_update_discovered_source_review(
                DiscoveredSourceReviewBulkUpdate(
                    source_ids=[source_id, missing_id],
                    review_status="weak",
                    reviewed_by="bulk analyst",
                ),
                db=db,
            )
        finally:
            db.close()

        self.assertEqual(response.requested_count, 2)
        self.assertEqual(response.updated_count, 1)
        self.assertEqual(response.missing_ids, [missing_id])
        self.assertEqual(response.items[0].review_status, "weak")

    def test_bulk_patch_modifies_only_triage_fields_and_preserves_quality_metadata(self) -> None:
        before_counts = self._counts()
        db = self.SessionLocal()
        try:
            source_id = list_discovered_sources(source_url_quality="public_comment_form", limit=50, offset=0, db=db).items[0].id
            before = get_discovered_source(source_id, db=db)
            response = bulk_update_discovered_source_review(
                DiscoveredSourceReviewBulkUpdate(
                    source_ids=[source_id],
                    review_status="useful",
                    review_notes="Keep as fallback context.",
                    reviewed_by="bulk analyst",
                ),
                db=db,
            )
            after = get_discovered_source(source_id, db=db)
        finally:
            db.close()

        self.assertEqual(response.updated_count, 1)
        self.assertEqual(after.review_status, "useful")
        self.assertEqual(after.source_url, before.source_url)
        self.assertEqual(after.source_title, before.source_title)
        self.assertEqual(after.source_type, before.source_type)
        self.assertEqual(after.geography, before.geography)
        self.assertEqual(after.publisher, before.publisher)
        self.assertEqual(after.source_registry_id, before.source_registry_id)
        self.assertEqual(after.adapter_id, before.adapter_id)
        self.assertEqual(after.discovery_run_id, before.discovery_run_id)
        self.assertEqual(after.discovery_method, before.discovery_method)
        self.assertEqual(after.source_query, before.source_query)
        self.assertEqual(after.snippet, before.snippet)
        self.assertEqual(after.status, before.status)
        self.assertEqual(after.raw_metadata_json, before.raw_metadata_json)
        self.assertEqual(after.source_url_quality, "public_comment_form")
        self.assertEqual(self._counts(), before_counts)

    def test_bulk_patch_note_replace_and_append_modes(self) -> None:
        db = self.SessionLocal()
        try:
            source_id = list_discovered_sources(review_status="useful", limit=50, offset=0, db=db).items[0].id
            replaced = bulk_update_discovered_source_review(
                DiscoveredSourceReviewBulkUpdate(
                    source_ids=[source_id],
                    review_notes="Replacement note",
                    note_mode="replace",
                ),
                db=db,
            )
            appended = bulk_update_discovered_source_review(
                DiscoveredSourceReviewBulkUpdate(
                    source_ids=[source_id],
                    review_notes="Appended note",
                    note_mode="append",
                ),
                db=db,
            )
        finally:
            db.close()

        self.assertEqual(replaced.items[0].review_notes, "Replacement note")
        self.assertEqual(appended.items[0].review_notes, "Replacement note\n\nAppended note")

    def test_bulk_patch_blank_notes_and_reviewer_normalize_to_null(self) -> None:
        db = self.SessionLocal()
        try:
            source_id = list_discovered_sources(review_status="useful", limit=50, offset=0, db=db).items[0].id
            response = bulk_update_discovered_source_review(
                DiscoveredSourceReviewBulkUpdate(
                    source_ids=[source_id],
                    review_notes=" ",
                    reviewed_by=" ",
                ),
                db=db,
            )
        finally:
            db.close()

        self.assertIsNone(response.items[0].review_notes)
        self.assertIsNone(response.items[0].reviewed_by)
        self.assertIsNotNone(response.items[0].reviewed_at)

    def test_bulk_patch_unreviewed_matches_single_row_behavior(self) -> None:
        db = self.SessionLocal()
        try:
            source_id = list_discovered_sources(review_status="useful", limit=50, offset=0, db=db).items[0].id
            response = bulk_update_discovered_source_review(
                DiscoveredSourceReviewBulkUpdate(source_ids=[source_id], review_status="unreviewed"),
                db=db,
            )
            stored = db.get(DiscoveredSourceRecord, source_id)
        finally:
            db.close()

        self.assertEqual(response.items[0].review_status, "unreviewed")
        self.assertIsNone(stored.review_status)
        self.assertIsNotNone(response.items[0].reviewed_at)

    def test_bulk_patch_keeps_computed_priority_read_only(self) -> None:
        db = self.SessionLocal()
        try:
            source_id = list_discovered_sources(q="homepage", limit=50, offset=0, db=db).items[0].id
            before = get_discovered_source(source_id, db=db)
            response = bulk_update_discovered_source_review(
                DiscoveredSourceReviewBulkUpdate(source_ids=[source_id], review_status="noisy"),
                db=db,
            )
            after = get_discovered_source(source_id, db=db)
        finally:
            db.close()

        self.assertEqual(response.items[0].review_priority_score, before.review_priority_score)
        self.assertEqual(after.review_priority_bucket, before.review_priority_bucket)
        self.assertNotIn("review_priority_score", after.raw_metadata_json)

    def test_computed_priority_does_not_mutate_source_rows(self) -> None:
        db = self.SessionLocal()
        try:
            source_id = list_discovered_sources(q="homepage", limit=50, offset=0, db=db).items[0].id
            before = get_discovered_source(source_id, db=db)
            summarize_discovered_sources(sort="priority_desc", db=db)
            after = get_discovered_source(source_id, db=db)
            self.assertFalse(db.dirty)
        finally:
            db.close()

        self.assertEqual(after.raw_metadata_json, before.raw_metadata_json)
        self.assertEqual(after.review_status, before.review_status)
        self.assertEqual(after.status, before.status)

    def test_patch_normalizes_blank_review_fields_and_clears_to_unreviewed(self) -> None:
        db = self.SessionLocal()
        try:
            listed = list_discovered_sources(review_status="useful", limit=50, offset=0, db=db)
            source_id = listed.items[0].id
            response = update_discovered_source_review(
                source_id,
                DiscoveredSourceReviewUpdate(review_status=" ", review_notes=" ", reviewed_by=" "),
                db=db,
            )
        finally:
            db.close()

        self.assertEqual(response.review_status, "unreviewed")
        self.assertIsNone(response.review_notes)
        self.assertIsNone(response.reviewed_by)
        self.assertIsNotNone(response.reviewed_at)

    def test_invalid_review_status_returns_clean_4xx(self) -> None:
        db = self.SessionLocal()
        try:
            listed = list_discovered_sources(limit=50, offset=0, db=db)
            request = DiscoveredSourceReviewUpdate.model_construct(
                review_status="bad_status",
                review_notes=None,
                reviewed_by=None,
            )
            with self.assertRaisesRegex(Exception, "422"):
                update_discovered_source_review(listed.items[0].id, request, db=db)
        finally:
            db.close()

    def test_patch_missing_source_returns_404(self) -> None:
        import uuid

        db = self.SessionLocal()
        try:
            with self.assertRaisesRegex(Exception, "404"):
                update_discovered_source_review(
                    uuid.uuid4(),
                    DiscoveredSourceReviewUpdate(review_status="maybe"),
                    db=db,
                )
        finally:
            db.close()

    def test_weak_url_quality_is_independent_from_analyst_review_status(self) -> None:
        db = self.SessionLocal()
        try:
            listed = list_discovered_sources(source_url_quality="public_comment_form", limit=50, offset=0, db=db)
            response = update_discovered_source_review(
                listed.items[0].id,
                DiscoveredSourceReviewUpdate(review_status="useful"),
                db=db,
            )
        finally:
            db.close()

        self.assertEqual(response.source_url_quality, "public_comment_form")
        self.assertEqual(response.review_status, "useful")

    def test_bulk_weak_url_quality_is_independent_from_analyst_review_status(self) -> None:
        db = self.SessionLocal()
        try:
            listed = list_discovered_sources(source_url_quality="public_comment_form", limit=50, offset=0, db=db)
            response = bulk_update_discovered_source_review(
                DiscoveredSourceReviewBulkUpdate(source_ids=[listed.items[0].id], review_status="rejected"),
                db=db,
            )
        finally:
            db.close()

        self.assertEqual(response.items[0].source_url_quality, "public_comment_form")
        self.assertEqual(response.items[0].review_status, "rejected")

    def test_review_endpoints_do_not_create_downstream_records(self) -> None:
        before = self._counts()

        db = self.SessionLocal()
        try:
            list_discovered_sources(limit=50, offset=0, db=db)
            summarize_discovered_sources(db=db)
            source_ids = [item.id for item in list_discovered_sources(limit=2, offset=0, db=db).items]
            bulk_update_discovered_source_review(
                DiscoveredSourceReviewBulkUpdate(source_ids=source_ids, review_status="maybe"),
                db=db,
            )
        finally:
            db.close()

        self.assertEqual(self._counts(), before)
        self.assertEqual(before["sources"], 4)
        self.assertEqual({key: value for key, value in before.items() if key != "sources"}, {
            "projects": 0,
            "evidence": 0,
            "claims": 0,
            "discovered_source_claims": 0,
            "project_candidates": 0,
        })


if __name__ == "__main__":
    unittest.main()
