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
from app.services.discovered_source_claim_extractor import DiscoveredSourceClaimService  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract conservative candidate claims from ingested discovered sources.")
    parser.add_argument("--source-id", type=uuid.UUID, default=None, help="Only extract claims for one discovered source ID.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of discovered sources to inspect.")
    parser.add_argument("--dry-run", action="store_true", help="Summarize extraction without writing claims.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 0:
        raise SystemExit("--limit must be non-negative")
    create_db_and_tables()
    with SessionLocal() as db:
        summary = DiscoveredSourceClaimService(db).extract_claims(
            source_id=args.source_id,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        if not args.dry_run:
            db.commit()
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
