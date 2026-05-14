from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal  # noqa: E402
from app.services.project_candidate_promotion import ProjectCandidatePromotionService  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Explicitly promote one project candidate into a real Project.")
    parser.add_argument("--candidate-id", type=uuid.UUID, required=True, help="Project candidate ID to promote.")
    parser.add_argument("--confirm", action="store_true", help="Write the promoted Project and linked Evidence.")
    parser.add_argument(
        "--allow-unresolved-name",
        action="store_true",
        help="Allow promotion of cautious unresolved candidate names.",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Allow promotion when required conservative fields such as state are missing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with SessionLocal() as db:
        summary = ProjectCandidatePromotionService(db).promote(
            args.candidate_id,
            confirm=args.confirm,
            allow_unresolved_name=args.allow_unresolved_name,
            allow_incomplete=args.allow_incomplete,
        )
        if args.confirm and not summary.errors:
            db.commit()
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    if summary.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
