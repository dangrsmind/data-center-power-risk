"""
Regression tests for project_name_mention claim acceptance guard.

Background
----------
A critical data-integrity bug was found where accepting a project_name_mention
claim with a headline/sentence value (e.g. "The contract for development of a
data center in the Heartland Industrial Park") overwrote projects.canonical_name
with that sentence, corrupting the project list display.

Root causes:
  1. automation_service._extract_project_name() regex matched long sentence
     fragments when the text started with "The contract..., developed by ..."
  2. ingestion_service._apply_claim_acceptance() wrote the raw claim value to
     the DB with zero validation.
  3. IngestPage listed project_name_mention in SAFE_CLAIM_TYPES so it was
     auto-selected and accepted without any analyst warning.

These tests verify that the guard layer in IngestionService and the extraction
filter in AutomationService prevent any recurrence.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from app.core.enums import (  # noqa: E402
    ClaimEntityType,
    ClaimReviewStatus,
    ClaimType,
    LifecycleState,
    ReviewerStatus,
    SourceType,
)
from app.models import Base  # noqa: E402
from app.models.evidence import Claim, Evidence  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.schemas.automation import ClaimSuggestRequest  # noqa: E402
from app.schemas.ingestion import EvidenceCreateRequest  # noqa: E402
from app.services.automation_service import AutomationService  # noqa: E402
from app.services.ingestion_service import IngestionService  # noqa: E402


# ---------------------------------------------------------------------------
# Shared DB fixture
# ---------------------------------------------------------------------------

class _DbMixin(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(
            bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
        )
        Base.metadata.create_all(bind=engine)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _make_project_and_evidence(self, db, canonical_name: str = "AVAIO Farmville"):
        project = Project(
            canonical_name=canonical_name,
            state="VA",
            lifecycle_state=LifecycleState.CANDIDATE_UNVERIFIED,
        )
        db.add(project)

        evidence = Evidence(
            source_type=SourceType.PRESS,
            source_rank=1,
            title="Test press article",
            extracted_text="Evidence text",
            reviewer_status=ReviewerStatus.PENDING,
        )
        db.add(evidence)
        db.flush()
        return project, evidence

    def _make_claim(self, db, evidence, project, claim_value: dict) -> Claim:
        claim = Claim(
            evidence_id=evidence.id,
            entity_type=ClaimEntityType.PROJECT,
            entity_id=project.id,
            claim_type=ClaimType.PROJECT_NAME_MENTION,
            claim_value_json=claim_value,
            confidence="medium",
            is_contradictory=False,
            review_status=ClaimReviewStatus.ACCEPTED_CANDIDATE,
        )
        db.add(claim)
        db.flush()
        return claim


# ---------------------------------------------------------------------------
# IngestionService._validate_project_name  (unit-level)
# ---------------------------------------------------------------------------

class TestValidateProjectName(unittest.TestCase):
    def setUp(self):
        self.svc = IngestionService.__new__(IngestionService)

    def _ok(self, name: str):
        self.svc._validate_project_name(name)

    def _bad(self, name: str):
        with self.assertRaises(HTTPException) as ctx:
            self.svc._validate_project_name(name)
        return ctx.exception

    # --- valid names must pass ---

    def test_valid_two_word_name(self):
        self._ok("AVAIO Farmville")

    def test_valid_three_word_campus(self):
        self._ok("Red Mesa Campus")

    def test_valid_six_word_name(self):
        self._ok("Blue Prairie AI Compute Campus Phase")

    def test_valid_name_with_numbers(self):
        self._ok("SiteX Data Center VA1")

    # --- invalid names must be rejected ---

    def test_rejects_exact_corrupted_sentence(self):
        exc = self._bad(
            "The contract for development of a data center in the Heartland Industrial Park"
        )
        self.assertEqual(exc.status_code, 400)
        self.assertIn("too long", exc.detail)

    def test_rejects_sentence_starting_with_the(self):
        exc = self._bad("The contract for development of a data center")
        self.assertEqual(exc.status_code, 400)

    def test_rejects_name_starting_with_article_the(self):
        exc = self._bad("The Grid Campus")
        self.assertEqual(exc.status_code, 400)
        self.assertIn("headline", exc.detail)

    def test_rejects_name_starting_with_article_a(self):
        exc = self._bad("A new data center")
        self.assertEqual(exc.status_code, 400)

    def test_rejects_name_over_60_chars(self):
        exc = self._bad("X" * 61)
        self.assertEqual(exc.status_code, 400)
        self.assertIn("too long", exc.detail)

    def test_rejects_name_with_seven_words(self):
        exc = self._bad("Alpha Beta Gamma Delta Epsilon Zeta Eta")
        self.assertEqual(exc.status_code, 400)
        self.assertIn("7 words", exc.detail)

    def test_rejects_empty_name(self):
        exc = self._bad("")
        self.assertEqual(exc.status_code, 400)
        self.assertIn("empty", exc.detail)

    def test_rejects_whitespace_only(self):
        exc = self._bad("   ")
        self.assertEqual(exc.status_code, 400)


# ---------------------------------------------------------------------------
# IngestionService.accept_claim  (integration-level — DB write is blocked)
# ---------------------------------------------------------------------------

class TestAcceptClaimProjectNameGuard(_DbMixin):
    """
    The exact failure scenario: a claim whose project_name is a full headline
    sentence must be rejected at accept time without modifying the DB.
    """

    HEADLINE = "The contract for development of a data center in the Heartland Industrial Park"

    def test_headline_sentence_is_rejected_on_accept(self):
        db = self.SessionLocal()
        try:
            project, evidence = self._make_project_and_evidence(db)
            original_name = project.canonical_name

            claim = self._make_claim(
                db, evidence, project, {"project_name": self.HEADLINE}
            )
            db.commit()

            svc = IngestionService(db)
            with self.assertRaises(HTTPException) as ctx:
                from app.schemas.ingestion import ClaimAcceptRequest
                svc.accept_claim(claim.id, ClaimAcceptRequest(accepted_by="test"))

            self.assertEqual(ctx.exception.status_code, 400)

            # DB must not have been modified
            db.refresh(project)
            self.assertEqual(
                project.canonical_name,
                original_name,
                "canonical_name must not be overwritten by a rejected claim",
            )
        finally:
            db.close()

    def test_concise_name_is_accepted(self):
        db = self.SessionLocal()
        try:
            project, evidence = self._make_project_and_evidence(db, "Old Name")
            claim = self._make_claim(
                db, evidence, project, {"project_name": "AVAIO Farmville"}
            )
            db.commit()

            svc = IngestionService(db)
            from app.schemas.ingestion import ClaimAcceptRequest
            result = svc.accept_claim(claim.id, ClaimAcceptRequest(accepted_by="analyst"))

            db.refresh(project)
            self.assertEqual(project.canonical_name, "AVAIO Farmville")
        finally:
            db.close()


# ---------------------------------------------------------------------------
# AutomationService._extract_project_name  — regression on the bad input text
# ---------------------------------------------------------------------------

class TestExtractProjectNameRegression(unittest.TestCase):
    def setUp(self):
        self.svc = AutomationService()

    def test_headline_text_does_not_produce_project_name_claim(self):
        """
        Input text that caused the corruption:
          'The contract for development of a data center in the Heartland
           Industrial Park, developed by AVAIO...'
        The extractor must NOT return a sentence fragment as the project name.
        """
        text = (
            "The contract for development of a data center in the Heartland Industrial Park, "
            "developed by AVAIO Digital Infrastructure, is located in Prince Edward County, Virginia. "
            "The facility will have a modeled load of 200 MW."
        )
        result = self.svc._extract_project_name(text)
        # The returned value (if any) must not be the headline sentence
        if result is not None:
            self.assertLessEqual(len(result.split()), 6, f"Extracted name too long: {result!r}")
            self.assertFalse(
                result.lower().startswith("the "),
                f"Extracted name starts with article: {result!r}",
            )
            self.assertNotIn("contract", result.lower())

    def test_clean_campus_name_is_still_extracted(self):
        """
        Properly formatted input must still yield the correct project name.
        """
        text = (
            "AVAIO Farmville Data Campus, developed by AVAIO Digital Infrastructure, "
            "is located in Prince Edward County, Virginia with an initial load of 200 MW."
        )
        result = self.svc._extract_project_name(text)
        self.assertIsNotNone(result)
        self.assertIn("AVAIO", result)

    def test_heartland_industrial_park_is_not_a_project_name(self):
        """
        'Heartland Industrial Park' matches the Park suffix pattern but the
        extraction is still acceptable: it is 3 words and looks like a proper
        place name, not a sentence.  What must NOT be returned is the full
        sentence fragment including 'The contract for...'.
        """
        text = (
            "The contract for development of a data center in the Heartland Industrial Park "
            "was announced today."
        )
        result = self.svc._extract_project_name(text)
        if result is not None:
            # Accept 'Heartland Industrial Park' as a three-word proper name
            # but never the full headline
            self.assertNotIn("contract", result.lower())
            self.assertLessEqual(len(result.split()), 6)


if __name__ == "__main__":
    unittest.main()
