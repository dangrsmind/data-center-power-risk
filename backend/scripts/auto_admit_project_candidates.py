from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal  # noqa: E402
from app.services.project_candidate_promotion import ProjectCandidatePromotionService  # noqa: E402
from app.services.project_candidate_verifier import AUTO_ADMIT_ELIGIBLE, NEEDS_REVIEW, QUARANTINED, ProjectCandidateVerifier  # noqa: E402


@dataclass
class AutoAdmitSummary:
    candidates_checked: int = 0
    eligible: int = 0
    promoted: int = 0
    skipped_needs_review: int = 0
    skipped_quarantined: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    promoted_project_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run-first auto-admit for strictly verified project candidates.")
    parser.add_argument("--confirm", action="store_true", help="Promote eligible candidates.")
    parser.add_argument("--candidate-id", type=uuid.UUID, default=None, help="Evaluate one candidate.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum candidates to evaluate.")
    parser.add_argument("--threshold", type=float, default=0.80, help="Minimum candidate confidence for auto-admit.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 0:
        raise SystemExit("--limit must be non-negative")
    if not 0 <= args.threshold <= 1:
        raise SystemExit("--threshold must be between 0 and 1")
    summary = AutoAdmitSummary()
    with SessionLocal() as db:
        verifier = ProjectCandidateVerifier(db)
        candidates = verifier.list_candidates(candidate_id=args.candidate_id, limit=args.limit)
        if args.candidate_id and not candidates:
            summary.errors.append("candidate_not_found")
        promotion_service = ProjectCandidatePromotionService(db)
        for candidate in candidates:
            result = verifier.verify(candidate, threshold=args.threshold, persist=args.confirm)
            summary.candidates_checked += 1
            if result.decision == AUTO_ADMIT_ELIGIBLE:
                summary.eligible += 1
                promotion = promotion_service.promote(candidate.id, confirm=args.confirm)
                if promotion.errors:
                    summary.errors.extend(f"{candidate.id}:{error}" for error in promotion.errors)
                    continue
                summary.warnings.extend(f"{candidate.id}:{warning}" for warning in promotion.warnings)
                if args.confirm and promotion.promoted:
                    summary.promoted += 1
                    if promotion.promoted_project_id:
                        summary.promoted_project_ids.append(promotion.promoted_project_id)
            elif result.decision == NEEDS_REVIEW:
                summary.skipped_needs_review += 1
            elif result.decision == QUARANTINED:
                summary.skipped_quarantined += 1
        if args.confirm and not summary.errors:
            db.commit()
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    if summary.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
