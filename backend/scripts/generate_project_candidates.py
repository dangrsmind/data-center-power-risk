from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal, create_db_and_tables  # noqa: E402
from app.services.project_candidate_generator import ProjectCandidateGenerator  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate reviewable project candidates from discovered-source claims.")
    parser.add_argument("--dry-run", action="store_true", help="Summarize generation without writing candidates.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of claims to inspect.")
    parser.add_argument("--status", default="extracted", help="Claim status to read. Use empty string for all statuses.")
    parser.add_argument("--source-id", type=uuid.UUID, default=None, help="Only generate from one discovered source ID.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 0:
        raise SystemExit("--limit must be non-negative")
    create_db_and_tables()
    with SessionLocal() as db:
        summary = ProjectCandidateGenerator(db).generate(
            dry_run=args.dry_run,
            limit=args.limit,
            status=args.status or None,
            source_id=args.source_id,
        )
        if not args.dry_run:
            db.commit()
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
