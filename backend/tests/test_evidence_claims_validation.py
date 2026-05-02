from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from app.api.routes.ingestion import create_evidence_claims  # noqa: E402
from app.core.enums import ClaimReviewStatus, LifecycleState, ReviewerStatus, SourceType  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.schemas.ingestion import (  # noqa: E402
    ClaimAcceptRequest,
    ClaimLinkRequest,
    ClaimReviewRequest,
    EvidenceClaimsCreateRequest,
    EvidenceReviewRequest,
    EvidenceCreateRequest,
    ProjectNameClaimCreate,
    ProjectNameClaimValue,
)
from app.services.ingestion_service import IngestionService  # noqa: E402


class EvidenceClaimsValidationTest(unittest.TestCase):
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

    def test_invalid_claim_payload_returns_clean_400_with_index_and_type(self) -> None:
        db = self.SessionLocal()
        try:
            evidence = IngestionService(db).create_evidence(
                EvidenceCreateRequest(
                    source_type=SourceType.DEVELOPER_STATEMENT,
                    title="Test evidence",
                    extracted_text="CleanArc VA1 source text",
                    reviewer_status=ReviewerStatus.PENDING,
                )
            )

            class FakeRequest:
                async def json(self_inner):
                    return {
                        "claims": [
                            {
                                "claim_type": "modeled_load_mw",
                                "claim_value": {"modeled_primary_load_mw": 300.0},
                                "confidence": "medium",
                            },
                            {
                                "claim_type": "phase_name_mention",
                                "claim_value": {
                                    "phase_name": "Phase I is targeted for December 2027 with an initial 300 MW phase"
                                },
                                "confidence": "medium",
                            },
                            {
                                "claim_type": "target_energization_date",
                                "claim_value": {"target_energization_date": "2027-12-01"},
                                "confidence": "medium",
                            },
                        ]
                    }

            with self.assertRaises(HTTPException) as exc_context:
                asyncio.run(
                    create_evidence_claims(
                        evidence_id=evidence.evidence_id,
                        request=FakeRequest(),
                        db=db,
                    )
                )

            exc = exc_context.exception
            self.assertEqual(exc.status_code, 400)
            detail = exc.detail
            self.assertEqual(detail["message"], "Invalid claims payload")
            self.assertTrue(detail["invalid_claims"])
            self.assertEqual(detail["invalid_claims"][0]["claim_index"], 1)
            self.assertEqual(detail["invalid_claims"][0]["claim_type"], "phase_name_mention")
            self.assertIn("pattern", detail["invalid_claims"][0]["message"].lower())
        finally:
            db.close()

    def test_accepting_claim_leaves_evidence_pending_until_explicit_review(self) -> None:
        db = self.SessionLocal()
        try:
            project = Project(
                canonical_name="Original Name",
                state="VA",
                county="Prince Edward",
                lifecycle_state=LifecycleState.CANDIDATE_UNVERIFIED,
            )
            db.add(project)
            db.commit()

            service = IngestionService(db)
            evidence = service.create_evidence(
                EvidenceCreateRequest(
                    source_type=SourceType.DEVELOPER_STATEMENT,
                    title="Project update",
                    extracted_text="The project is named CleanArc VA1.",
                    reviewer_status=ReviewerStatus.PENDING,
                )
            )
            claims_response = service.create_claims(
                evidence.evidence_id,
                EvidenceClaimsCreateRequest(
                    claims=[
                        ProjectNameClaimCreate(
                            claim_type="project_name_mention",
                            claim_value=ProjectNameClaimValue(project_name="CleanArc VA1"),
                            confidence="high",
                        )
                    ]
                ),
            )
            claim_id = claims_response.created_claims[0].claim_id

            service.link_claim(claim_id, ClaimLinkRequest(project_id=project.id))
            service.review_claim(
                claim_id,
                ClaimReviewRequest(
                    review_status=ClaimReviewStatus.ACCEPTED_CANDIDATE,
                    reviewer="user",
                ),
            )
            service.accept_claim(claim_id, ClaimAcceptRequest(accepted_by="user"))

            pending_detail = service.get_evidence_detail(evidence.evidence_id)
            self.assertEqual(pending_detail.evidence.reviewer_status, ReviewerStatus.PENDING)
            self.assertIsNone(pending_detail.evidence.reviewed_by)

            reviewed = service.review_evidence(
                evidence.evidence_id,
                EvidenceReviewRequest(
                    reviewer_status=ReviewerStatus.REVIEWED,
                    reviewed_by="user",
                    notes="Claim acceptance checked.",
                ),
            )

            self.assertEqual(reviewed.reviewer_status, ReviewerStatus.REVIEWED)
            self.assertEqual(reviewed.reviewed_by, "user")
            self.assertEqual(reviewed.review_notes, "Claim acceptance checked.")
            self.assertIsNotNone(reviewed.reviewed_at)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
