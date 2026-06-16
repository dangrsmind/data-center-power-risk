from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.api.routes.project_candidates import (  # noqa: E402
    create_project_candidate_source_attachment,
    list_project_candidates,
    list_project_candidate_source_attachments,
    update_project_candidate_review_decision,
)
from app.models import Base  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.project_candidate import ProjectCandidate, ProjectCandidateSourceAttachment  # noqa: E402
from app.schemas.project_candidate import (  # noqa: E402
    ProjectCandidateReviewDecisionRequest,
    ProjectCandidateSourceAttachmentRequest,
)
from app.services.project_candidate_generator import CandidateDraft, update_project_candidate  # noqa: E402
from app.services.project_candidate_triage import ProjectCandidateTriageService  # noqa: E402


class ProjectCandidateReviewDecisionTest(unittest.TestCase):
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

    def candidate(self, db, **kwargs) -> ProjectCandidate:
        defaults = {
            "candidate_key": kwargs.pop("candidate_key", "review-candidate"),
            "candidate_name": kwargs.pop("candidate_name", "Review Campus"),
            "developer": "Review Developer",
            "state": "VA",
            "county": "Loudoun",
            "city": None,
            "utility": None,
            "load_mw": 120,
            "lifecycle_state": "candidate_unverified",
            "confidence": 0.65,
            "status": "needs_review",
            "source_count": 1,
            "claim_count": 0,
            "primary_source_url": "https://example.com/source",
            "discovered_source_ids_json": [],
            "discovered_source_claim_ids_json": [],
            "evidence_excerpt": "Review source excerpt",
            "raw_metadata_json": {},
            "verification_status": "needs_review",
            "auto_admit_eligible": True,
        }
        defaults.update(kwargs)
        candidate = ProjectCandidate(**defaults)
        db.add(candidate)
        db.flush()
        return candidate

    def test_valid_review_decision_update_sets_review_fields_only(self) -> None:
        db = self.SessionLocal()
        try:
            project = Project(canonical_name="Existing Project", state="VA", lifecycle_state="candidate_unverified")
            db.add(project)
            db.flush()
            candidate = self.candidate(db, promoted_project_id=project.id)
            db.commit()

            response = update_project_candidate_review_decision(
                candidate.id,
                ProjectCandidateReviewDecisionRequest(
                    review_decision="needs_source",
                    review_notes=" Need official utility interconnection or permit source. ",
                    reviewed_by=" analyst ",
                ),
                db=db,
            )
            db.refresh(candidate)

            self.assertEqual(response.review_decision, "needs_source")
            self.assertEqual(response.review_notes, "Need official utility interconnection or permit source.")
            self.assertEqual(response.reviewed_by, "analyst")
            self.assertIsNotNone(response.reviewed_at)
            self.assertEqual(candidate.status, "needs_review")
            self.assertEqual(candidate.verification_status, "needs_review")
            self.assertTrue(candidate.auto_admit_eligible)
            self.assertEqual(candidate.promoted_project_id, project.id)
        finally:
            db.close()

    def test_clear_review_decision_clears_reviewed_at(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self.candidate(db)
            db.commit()
            update_project_candidate_review_decision(
                candidate.id,
                ProjectCandidateReviewDecisionRequest(review_decision="keep_under_review"),
                db=db,
            )
            db.refresh(candidate)
            self.assertIsNotNone(candidate.reviewed_at)

            response = update_project_candidate_review_decision(
                candidate.id,
                ProjectCandidateReviewDecisionRequest(review_decision=None, review_notes=None, reviewed_by=None),
                db=db,
            )
            db.refresh(candidate)

            self.assertIsNone(response.review_decision)
            self.assertIsNone(response.reviewed_at)
            self.assertIsNone(candidate.reviewed_at)
        finally:
            db.close()

    def test_empty_string_review_decision_clears_review_fields(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self.candidate(
                db,
                review_decision="needs_source",
                review_notes="Needs source",
                reviewed_by="analyst",
                reviewed_at=datetime.now(timezone.utc),
            )
            db.commit()

            response = update_project_candidate_review_decision(
                candidate.id,
                ProjectCandidateReviewDecisionRequest(
                    review_decision="   ",
                    review_notes="   ",
                    reviewed_by="   ",
                ),
                db=db,
            )
            db.refresh(candidate)

            self.assertIsNone(response.review_decision)
            self.assertIsNone(response.review_notes)
            self.assertIsNone(response.reviewed_by)
            self.assertIsNone(response.reviewed_at)
            self.assertIn("review_decision", response.model_dump())
            self.assertIn("review_notes", response.model_dump())
            self.assertIn("reviewed_by", response.model_dump())
            self.assertIn("reviewed_at", response.model_dump())
        finally:
            db.close()

    def test_invalid_review_decision_and_length_validation(self) -> None:
        with self.assertRaises(ValidationError):
            ProjectCandidateReviewDecisionRequest(review_decision="promote_now")
        with self.assertRaises(ValidationError):
            ProjectCandidateReviewDecisionRequest(review_decision="needs_source", review_notes="x" * 2001)
        with self.assertRaises(ValidationError):
            ProjectCandidateReviewDecisionRequest(review_decision="needs_source", reviewed_by="x" * 256)

    def test_candidate_not_found_returns_404(self) -> None:
        db = self.SessionLocal()
        try:
            with self.assertRaises(HTTPException) as ctx:
                update_project_candidate_review_decision(
                    uuid.UUID("11111111-1111-1111-1111-111111111111"),
                    ProjectCandidateReviewDecisionRequest(review_decision="needs_source"),
                    db=db,
                )
        finally:
            db.close()
        self.assertEqual(ctx.exception.status_code, 404)

    def test_list_filters_by_review_decision(self) -> None:
        db = self.SessionLocal()
        try:
            needs_source = self.candidate(db, candidate_key="needs-source", candidate_name="Needs Source")
            no_decision = self.candidate(db, candidate_key="no-decision", candidate_name="No Decision")
            needs_source.review_decision = "needs_source"
            db.commit()

            matching = list_project_candidates(review_decision="needs_source", min_triage_score=None, limit=100, db=db)
            reviewed = list_project_candidates(has_review_decision=True, min_triage_score=None, limit=100, db=db)
            unreviewed = list_project_candidates(has_review_decision=False, min_triage_score=None, limit=100, db=db)
        finally:
            db.close()

        self.assertEqual([item.id for item in matching.items], [needs_source.id])
        self.assertEqual([item.id for item in reviewed.items], [needs_source.id])
        self.assertEqual([item.id for item in unreviewed.items], [no_decision.id])

    def test_review_decision_filter_composes_with_existing_filters(self) -> None:
        db = self.SessionLocal()
        try:
            matching = self.candidate(
                db,
                candidate_key="matching",
                candidate_name="Matching",
                state="VA",
                status="needs_review",
                triage_tier="high",
                recommended_action="review_for_promotion",
                triage_score=0.84,
                review_decision="ready_for_verification",
            )
            self.candidate(
                db,
                candidate_key="wrong-state",
                candidate_name="Wrong State",
                state="TX",
                status="needs_review",
                triage_tier="high",
                recommended_action="review_for_promotion",
                triage_score=0.86,
                review_decision="ready_for_verification",
            )
            self.candidate(
                db,
                candidate_key="wrong-action",
                candidate_name="Wrong Action",
                state="VA",
                status="needs_review",
                triage_tier="high",
                recommended_action="needs_source_detail",
                triage_score=0.88,
                review_decision="ready_for_verification",
            )
            db.commit()

            response = list_project_candidates(
                status="needs_review",
                state="VA",
                triage_tier="high",
                recommended_action="review_for_promotion",
                review_decision="ready_for_verification",
                has_review_decision=True,
                min_triage_score=0.8,
                limit=100,
                db=db,
            )
        finally:
            db.close()

        self.assertEqual([item.id for item in response.items], [matching.id])

    def test_invalid_review_decision_filter_rejected(self) -> None:
        db = self.SessionLocal()
        try:
            with self.assertRaises(HTTPException) as ctx:
                list_project_candidates(review_decision="promote_now", db=db)
        finally:
            db.close()
        self.assertEqual(ctx.exception.status_code, 422)

    def test_triage_does_not_overwrite_review_decision_or_notes(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self.candidate(
                db,
                review_decision="likely_duplicate",
                review_notes="Looks like a duplicate of an existing candidate.",
                reviewed_by="analyst",
            )
            db.commit()
            ProjectCandidateTriageService(db).triage(candidate, persist=True)
            db.commit()
            db.refresh(candidate)

            self.assertEqual(candidate.review_decision, "likely_duplicate")
            self.assertEqual(candidate.review_notes, "Looks like a duplicate of an existing candidate.")
            self.assertEqual(candidate.reviewed_by, "analyst")
        finally:
            db.close()

    def test_generator_update_preserves_review_metadata(self) -> None:
        db = self.SessionLocal()
        try:
            reviewed_at = datetime.now(timezone.utc)
            candidate = self.candidate(
                db,
                review_decision="likely_duplicate",
                review_notes="Looks like an existing row.",
                reviewed_by="analyst",
                reviewed_at=reviewed_at,
            )
            draft = CandidateDraft(
                candidate_key=candidate.candidate_key,
                candidate_name="Updated Candidate Name",
                developer="Updated Developer",
                state="VA",
                county="Loudoun",
                city="Ashburn",
                utility="Dominion",
                load_mw=320,
                lifecycle_state="candidate_unverified",
                confidence=0.8,
                status="candidate",
                source_count=2,
                claim_count=3,
                primary_source_url="https://example.com/updated",
                discovered_source_ids_json=[],
                discovered_source_claim_ids_json=[],
                evidence_excerpt="Updated excerpt",
                raw_metadata_json={"group_key": "updated"},
            )

            update_project_candidate(candidate, draft)

            self.assertEqual(candidate.candidate_name, "Updated Candidate Name")
            self.assertEqual(candidate.review_decision, "likely_duplicate")
            self.assertEqual(candidate.review_notes, "Looks like an existing row.")
            self.assertEqual(candidate.reviewed_by, "analyst")
            self.assertEqual(candidate.reviewed_at, reviewed_at)
        finally:
            db.close()

    def test_source_attachment_model_table_exists(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self.candidate(db)
            attachment = ProjectCandidateSourceAttachment(
                project_candidate_id=candidate.id,
                source_url="https://example.gov/permit-page",
                source_title="County permit agenda",
                source_type="permit",
                source_excerpt="Agenda item references data center substation request.",
                analyst_notes="Potential official source for candidate.",
                attached_by="analyst",
                attached_at=datetime.now(timezone.utc),
            )
            db.add(attachment)
            db.commit()

            self.assertEqual(db.query(ProjectCandidateSourceAttachment).count(), 1)
        finally:
            db.close()

    def test_create_source_attachment_and_summary_do_not_mutate_candidate_state(self) -> None:
        db = self.SessionLocal()
        try:
            project = Project(canonical_name="Existing Project", state="VA", lifecycle_state="candidate_unverified")
            db.add(project)
            db.flush()
            candidate = self.candidate(
                db,
                promoted_project_id=project.id,
                verification_status="needs_review",
                auto_admit_eligible=True,
            )
            db.commit()

            response = create_project_candidate_source_attachment(
                candidate.id,
                ProjectCandidateSourceAttachmentRequest(
                    source_url=" https://example.gov/permit-page ",
                    source_title=" County permit agenda ",
                    source_type="permit",
                    source_excerpt=" Agenda item references data center substation request. ",
                    analyst_notes=" Potential official source for candidate. ",
                    attached_by=" analyst ",
                ),
                db=db,
            )
            db.refresh(candidate)
            listed = list_project_candidate_source_attachments(candidate.id, db=db)
            candidate_response = list_project_candidates(review_decision=None, min_triage_score=None, limit=100, db=db)
            matching = [item for item in candidate_response.items if item.id == candidate.id][0]

            self.assertEqual(response.source_url, "https://example.gov/permit-page")
            self.assertEqual(response.source_title, "County permit agenda")
            self.assertEqual(response.source_type, "permit")
            self.assertEqual(response.source_excerpt, "Agenda item references data center substation request.")
            self.assertEqual(response.analyst_notes, "Potential official source for candidate.")
            self.assertEqual(response.attached_by, "analyst")
            self.assertIsNotNone(response.attached_at)
            self.assertEqual(len(listed.items), 1)
            self.assertEqual(listed.items[0].id, response.id)
            self.assertEqual(matching.source_attachment_count, 1)
            self.assertIsNotNone(matching.latest_source_attachment_at)
            self.assertEqual(matching.source_attachment_types, ["permit"])
            self.assertEqual(candidate.status, "needs_review")
            self.assertEqual(candidate.verification_status, "needs_review")
            self.assertTrue(candidate.auto_admit_eligible)
            self.assertEqual(candidate.promoted_project_id, project.id)
        finally:
            db.close()

    def test_source_attachment_candidate_not_found_returns_404(self) -> None:
        db = self.SessionLocal()
        try:
            with self.assertRaises(HTTPException) as ctx:
                create_project_candidate_source_attachment(
                    uuid.UUID("11111111-1111-1111-1111-111111111111"),
                    ProjectCandidateSourceAttachmentRequest(source_url="https://example.gov/permit-page"),
                    db=db,
                )
        finally:
            db.close()
        self.assertEqual(ctx.exception.status_code, 404)

    def test_invalid_source_attachment_request_validation(self) -> None:
        with self.assertRaises(ValidationError):
            ProjectCandidateSourceAttachmentRequest(source_url="ftp://example.gov/file")
        with self.assertRaises(ValidationError):
            ProjectCandidateSourceAttachmentRequest(source_url="https://example.gov", source_type="blog")
        with self.assertRaises(ValidationError):
            ProjectCandidateSourceAttachmentRequest(source_url="https://example.gov", source_title="x" * 501)
        with self.assertRaises(ValidationError):
            ProjectCandidateSourceAttachmentRequest(source_url="https://example.gov", source_excerpt="x" * 5001)
        with self.assertRaises(ValidationError):
            ProjectCandidateSourceAttachmentRequest(source_url="https://example.gov", analyst_notes="x" * 2001)
        with self.assertRaises(ValidationError):
            ProjectCandidateSourceAttachmentRequest(source_url="https://example.gov", attached_by="x" * 256)

    def test_duplicate_source_attachment_url_returns_existing_record(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self.candidate(db)
            db.commit()

            first = create_project_candidate_source_attachment(
                candidate.id,
                ProjectCandidateSourceAttachmentRequest(
                    source_url="https://example.gov/permit-page",
                    source_title="First title",
                    source_type="official",
                ),
                db=db,
            )
            duplicate = create_project_candidate_source_attachment(
                candidate.id,
                ProjectCandidateSourceAttachmentRequest(
                    source_url="https://example.gov/permit-page",
                    source_title="Second title",
                    source_type="media",
                ),
                db=db,
            )

            self.assertEqual(first.id, duplicate.id)
            self.assertEqual(duplicate.source_title, "First title")
            self.assertEqual(duplicate.source_type, "official")
            self.assertEqual(db.query(ProjectCandidateSourceAttachment).count(), 1)
        finally:
            db.close()

    def test_triage_uses_source_attachment_context_without_overwriting_review_fields(self) -> None:
        db = self.SessionLocal()
        try:
            candidate = self.candidate(
                db,
                review_decision="needs_source",
                review_notes="Existing analyst note.",
                reviewed_by="analyst",
            )
            create_project_candidate_source_attachment(
                candidate.id,
                ProjectCandidateSourceAttachmentRequest(source_url="https://example.gov/permit-page", source_type="permit"),
                db=db,
            )
            db.refresh(candidate)

            result = ProjectCandidateTriageService(db).triage(candidate, persist=True)
            db.commit()
            db.refresh(candidate)

            self.assertIn("analyst_source_attachment_present", result.triage_reasons)
            self.assertEqual(result.recommended_action, "ready_for_verification")
            self.assertEqual(candidate.review_decision, "needs_source")
            self.assertEqual(candidate.review_notes, "Existing analyst note.")
            self.assertEqual(candidate.reviewed_by, "analyst")
            self.assertTrue(candidate.auto_admit_eligible)
            self.assertIsNone(candidate.promoted_project_id)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
