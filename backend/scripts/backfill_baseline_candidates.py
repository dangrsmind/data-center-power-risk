"""Explicit read-only preview or confirmed candidate backfill from existing audits."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.core.db import get_database_url
from app.services.baseline_dataset_profiles import PROFILES
from app.services.baseline_candidate_backfill import backfill_candidates


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Backfill unverified review candidates from existing baseline audits; no Projects/Evidence.")
    parser.add_argument("--dataset", choices=PROFILES, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Read-only preview; writes nothing. Start here.")
    mode.add_argument("--confirm", action="store_true", help="Create review candidates and links only in an already migrated database.")
    parser.add_argument("--audit-row-id", type=uuid.UUID, action="append", default=[], help="Reviewed audit row UUID; repeat for multiple rows. Required with --confirm.")
    parser.add_argument("--max-create-candidates", type=int, help="Positive hard cap; fails rather than truncates. Required with --confirm.")
    parser.add_argument("--only-mappable", action="store_true")
    parser.add_argument("--include-row-details", action="store_true", help="Dry-run only: report selected audit rows, classifications and match IDs.")
    parser.add_argument("--include-possible-duplicates", action="store_true", help="CAUTION: allow ambiguous duplicate candidates for analyst review; exact duplicates stay blocked.")
    parser.add_argument("--import-run-id", help="Filter to an existing import run UUID.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--offset", type=int, default=0, help="Skip this many audit rows in stable order, including linked/ineligible rows.")
    parser.add_argument("--report-output", type=Path, help="New JSON output file, confirmed imports only; never overwrites an existing file.")
    args = parser.parse_args(argv)
    if args.include_row_details and not args.dry_run:
        parser.error("--include-row-details requires --dry-run")
    if args.max_create_candidates is not None and args.max_create_candidates <= 0:
        parser.error("--max-create-candidates must be a positive integer")
    if args.confirm and (not args.audit_row_id or args.max_create_candidates is None):
        parser.error("--confirm requires both --audit-row-id and --max-create-candidates")
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be non-negative")
    if args.offset < 0:
        parser.error("--offset must be non-negative")
    if args.dry_run and args.report_output:
        parser.error("--dry-run writes nothing; --report-output requires --confirm")
    if args.report_output and args.report_output.exists():
        parser.error("report output already exists; refusing to overwrite")
    return args


def main(argv=None):
    args = parse_args(argv)
    url = make_url(get_database_url())
    # No create_all/DDL: even an accidental new SQLite database is disallowed.
    if url.get_backend_name() == "sqlite":
        path = Path(url.database or "").resolve()
        if not path.is_file():
            raise SystemExit("An existing migrated database is required; no database was created.")
        uri = path.as_uri() + ("?mode=ro" if args.dry_run else "?mode=rw")
        engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True))
    else:
        engine = create_engine(url)
    try:
        with Session(engine, autoflush=False) as db:
            result = backfill_candidates(db, dataset=args.dataset, confirm=args.confirm,
                import_run_id=args.import_run_id, limit=args.limit, offset=args.offset, only_mappable=args.only_mappable,
                include_possible_duplicates=args.include_possible_duplicates,
                include_row_details=args.include_row_details, audit_row_ids=args.audit_row_id,
                max_create_candidates=args.max_create_candidates).to_dict()
            if args.confirm:
                db.commit()
        output = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
        print(output)
        if args.report_output:
            with args.report_output.open("x", encoding="utf-8") as handle:
                handle.write(output + "\n")
        return 0
    except ValueError as exc:
        print(f"Backfill refused: {exc}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
