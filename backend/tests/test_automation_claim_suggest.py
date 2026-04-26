from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.enums import ClaimType, SourceType  # noqa: E402
from app.schemas.automation import ClaimSuggestRequest  # noqa: E402
from app.services.automation_service import AutomationService  # noqa: E402


class AutomationClaimSuggestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AutomationService()

    def test_suggests_allowed_claim_types_only(self) -> None:
        response = self.service.suggest_claims(
            ClaimSuggestRequest(
                evidence_text=(
                    "Project Falcon Data Campus, developed by Example Digital Infrastructure, "
                    "is planned in Ellis County, Texas. Initial phase load is 300 MW. "
                    "Service is targeted for December 2027 in ERCOT with Oncor Electric Delivery."
                ),
                source_type=SourceType.DEVELOPER_STATEMENT,
            )
        )

        allowed_claim_types = {claim_type for claim_type in ClaimType}
        returned_claim_types = {claim.claim_type for claim in response.claims_payload.claims}

        self.assertTrue(returned_claim_types)
        self.assertTrue(returned_claim_types.issubset(allowed_claim_types))

    def test_ambiguous_text_produces_warnings(self) -> None:
        response = self.service.suggest_claims(
            ClaimSuggestRequest(
                evidence_text=(
                    "Example Compute Campus could expand up to 600 MW. "
                    "The project may be served by a utility in Virginia."
                )
            )
        )

        self.assertTrue(any("optional expansion" in warning.lower() for warning in response.warnings))
        self.assertTrue(any("utility" in item.lower() for item in response.uncertainties))

    def test_extracts_leading_project_name_before_developed_by_phrase(self) -> None:
        response = self.service.suggest_claims(
            ClaimSuggestRequest(
                evidence_text=(
                    "CleanArc VA1, developed by CleanArc Data Centers, is planned in Caroline County, Virginia "
                    "with an initial 300 MW phase."
                ),
                source_type=SourceType.DEVELOPER_STATEMENT,
            )
        )

        project_name_claims = [
            claim for claim in response.claims_payload.claims if claim.claim_type == ClaimType.PROJECT_NAME_MENTION
        ]

        self.assertEqual(len(project_name_claims), 1)
        self.assertEqual(project_name_claims[0].claim_value.project_name, "CleanArc VA1")

    def test_no_linked_reviewed_or_accepted_state_is_created(self) -> None:
        response = self.service.suggest_claims(
            ClaimSuggestRequest(
                evidence_text="Example Compute Campus in Texas is planned for 300 MW."
            )
        )

        dumped = response.model_dump()
        self.assertIn("claims_payload", dumped)
        for claim in dumped["claims_payload"]["claims"]:
            self.assertNotIn("review_status", claim)
            self.assertNotIn("entity_type", claim)
            self.assertNotIn("entity_id", claim)
            self.assertNotIn("accepted_at", claim)
            self.assertNotIn("accepted_by", claim)


if __name__ == "__main__":
    unittest.main()
