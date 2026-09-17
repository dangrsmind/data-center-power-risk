"""Explicit dry-run/confirm entrypoint to CsvDatasetImporter's baseline profiles."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.core.db import get_database_url
from app.services.baseline_dataset_profiles import PROFILES, FIELD_MAPPINGS
from app.services.csv_dataset_importer import CsvDatasetImporter


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Import local baseline CSVs into existing audit tables; no final Projects/Evidence.")
    parser.add_argument("--dataset", choices=PROFILES, required=True)
    parser.add_argument("--input", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Read-only preview; writes nothing. Start here.")
    mode.add_argument("--confirm", action="store_true", help="Write import audit records to an already migrated database.")
    parser.add_argument("--create-candidates", action="store_true", help="Opt in to new needs_review candidates; ambiguous or invalid rows remain audit-only.")
    parser.add_argument("--import-run-id", help="Optional new UUID; existing run IDs are rejected.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--report-output", type=Path, help="New JSON output file, confirmed imports only; never overwrites an existing file.")
    parser.add_argument("--source-url", help="Dataset landing URL; never treated as project evidence.")
    parser.add_argument("--citation")
    parser.add_argument("--license-note")
    parser.add_argument("--dataset-version")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be non-negative")
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
            result = CsvDatasetImporter(db).import_file(
                dataset=args.dataset, input_path=args.input, confirm=args.confirm,
                create_candidates=args.create_candidates, import_run_id=args.import_run_id,
                limit=args.limit, encoding="utf-8-sig", source_url=args.source_url,
                citation=args.citation, license_note=args.license_note, dataset_version=args.dataset_version,
            ).to_dict()
            result["profile"] = {**asdict(PROFILES[args.dataset]), "field_mappings": FIELD_MAPPINGS}
            if args.confirm:
                db.commit()
        output = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
        print(output)
        if args.report_output:
            with args.report_output.open("x", encoding="utf-8") as handle:
                handle.write(output + "\n")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
