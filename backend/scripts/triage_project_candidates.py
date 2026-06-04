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
from app.services.project_candidate_triage import ProjectCandidateTriageService  # noqa: E402


@dataclass
class TriageScriptSummary:
    candidates_checked: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run-first triage ranking for project candidates.")
    parser.add_argument("--confirm", action="store_true", help="Persist triage fields.")
    parser.add_argument("--candidate-id", type=uuid.UUID, default=None, help="Triage one candidate.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum candidates to triage.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 0:
        raise SystemExit("--limit must be non-negative")
    summary = TriageScriptSummary()
    with SessionLocal() as db:
        service = ProjectCandidateTriageService(db)
        candidates = service.list_candidates(candidate_id=args.candidate_id, limit=args.limit)
        if args.candidate_id and not candidates:
            summary.errors.append("candidate_not_found")
        for candidate in candidates:
            result = service.triage(candidate, persist=args.confirm)
            summary.candidates_checked += 1
            if result.triage_tier == "high":
                summary.high += 1
            elif result.triage_tier == "medium":
                summary.medium += 1
            elif result.triage_tier == "low":
                summary.low += 1
            summary.warnings.extend(f"{result.candidate_id}:{warning}" for warning in result.triage_warnings)
            summary.decisions.append(result.to_dict())
            if args.confirm:
                summary.updated += 1
        if args.confirm and not summary.errors:
            db.commit()
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    if summary.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
