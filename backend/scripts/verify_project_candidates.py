from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal  # noqa: E402
from app.services.project_candidate_verifier import (  # noqa: E402
    AUTO_ADMIT_ELIGIBLE,
    NEEDS_REVIEW,
    QUARANTINED,
    ProjectCandidateVerifier,
)


@dataclass
class VerificationScriptSummary:
    candidates_checked: int = 0
    auto_admit_eligible: int = 0
    needs_review: int = 0
    quarantined: int = 0
    updated: int = 0
    validation_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify project candidates against strict auto-admit rules.")
    parser.add_argument("--confirm", action="store_true", help="Persist verification fields.")
    parser.add_argument("--candidate-id", type=uuid.UUID, default=None, help="Verify one candidate.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum candidates to verify.")
    parser.add_argument("--threshold", type=float, default=0.80, help="Minimum candidate confidence for auto-admit.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 0:
        raise SystemExit("--limit must be non-negative")
    if not 0 <= args.threshold <= 1:
        raise SystemExit("--threshold must be between 0 and 1")
    summary = VerificationScriptSummary()
    with SessionLocal() as db:
        verifier = ProjectCandidateVerifier(db)
        candidates = verifier.list_candidates(candidate_id=args.candidate_id, limit=args.limit)
        if args.candidate_id and not candidates:
            summary.validation_errors.append("candidate_not_found")
        for candidate in candidates:
            result = verifier.verify(candidate, threshold=args.threshold, persist=args.confirm)
            summary.candidates_checked += 1
            if result.decision == AUTO_ADMIT_ELIGIBLE:
                summary.auto_admit_eligible += 1
            elif result.decision == NEEDS_REVIEW:
                summary.needs_review += 1
            elif result.decision == QUARANTINED:
                summary.quarantined += 1
            summary.warnings.extend(f"{result.candidate_id}:{warning}" for warning in result.warnings)
            summary.decisions.append(
                {
                    "candidate_id": result.candidate_id,
                    "decision": result.decision,
                    "confidence": result.confidence,
                    "reasons": result.reasons,
                    "blocking_errors": result.blocking_errors,
                }
            )
            if args.confirm:
                summary.updated += 1
        if args.confirm and not summary.validation_errors:
            db.commit()
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    if summary.validation_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
