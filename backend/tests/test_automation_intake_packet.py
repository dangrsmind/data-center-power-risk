from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.enums import LifecycleState, SourceType  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.evidence import Claim, Evidence, FieldProvenance  # noqa: E402
from app.models.project import Phase, Project  # noqa: E402
from app.services.automation_service import AutomationService  # noqa: E402
from app.schemas.automation import IntakePacketRequest  # noqa: E402


class AutomationIntakePacketTest(unittest.TestCase):
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

    def test_intake_packet_returns_payloads_and_link_suggestions_without_writes(self) -> None:
        db = self.SessionLocal()
        try:
            project = Project(
                canonical_name="CleanArc VA1",
                state="VA",
                county="Caroline",
                lifecycle_state=LifecycleState.NAMED_VERIFIED,
            )
            db.add(project)
            db.flush()
            phase = Phase(project_id=project.id, phase_name="Phase I", phase_order=1)
            db.add(phase)
            db.commit()

            evidence_count_before = db.query(Evidence).count()
            claim_count_before = db.query(Claim).count()
            provenance_count_before = db.query(FieldProvenance).count()

            response = AutomationService(db).build_intake_packet(
                IntakePacketRequest(
                    source_url="https://example.com/cleanarc",
                    source_type=SourceType.DEVELOPER_STATEMENT,
                    source_date=date(2026, 4, 25),
                    title="CleanArc VA1 update",
                    evidence_text=(
                        "CleanArc VA1, developed by CleanArc Data Centers, is planned in Caroline County, Virginia. "
                        "Phase I is targeted for December 2027 with an initial 300 MW phase."
                    ),
                    project_id=project.id,
                )
            )

            self.assertEqual(response.evidence_payload.source_url, "https://example.com/cleanarc")
            self.assertEqual(response.evidence_payload.title, "CleanArc VA1 update")
            self.assertTrue(response.claims_payload.claims)
            self.assertTrue(response.exact_next_steps)
            self.assertTrue(any(target.suggested_entity_type == "project" for target in response.suggested_link_targets))
            self.assertTrue(any(target.suggested_entity_type == "phase" for target in response.suggested_link_targets))
            phase_claims = [
                claim for claim in response.claims_payload.claims if claim.claim_type.value == "phase_name_mention"
            ]
            self.assertEqual(len(phase_claims), 1)
            self.assertEqual(phase_claims[0].claim_value.phase_name, "Phase I")

            self.assertEqual(db.query(Evidence).count(), evidence_count_before)
            self.assertEqual(db.query(Claim).count(), claim_count_before)
            self.assertEqual(db.query(FieldProvenance).count(), provenance_count_before)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
