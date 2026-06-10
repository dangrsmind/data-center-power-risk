from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal, create_db_and_tables  # noqa: E402
from app.services.csv_dataset_importer import CsvDatasetImporter  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import external data-center CSV datasets into review/audit tables.")
    parser.add_argument("--dataset", required=True, help="Dataset key, e.g. epoch_frontier or fractracker_open_us.")
    parser.add_argument("--input", required=True, help="CSV file to import.")
    parser.add_argument("--confirm", action="store_true", help="Persist imported row audit records.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum CSV rows to read.")
    parser.add_argument("--encoding", default="utf-8", help="CSV encoding. Defaults to utf-8.")
    parser.add_argument("--source-url", default=None, help="Dataset landing page or source URL.")
    parser.add_argument("--license-note", default=None, help="License note to preserve with the run and rows.")
    parser.add_argument("--citation", default=None, help="Citation text to preserve with the run and rows.")
    parser.add_argument("--create-candidates", action="store_true", help="Optionally create needs_review ProjectCandidates.")
    parser.add_argument("--dedupe-only", action="store_true", help="Persist/import row dedupe decisions without creating candidates.")
    parser.add_argument("--dataset-version", default=None, help="Optional dataset version label.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 0:
        raise SystemExit("--limit must be non-negative")
    if args.dedupe_only and args.create_candidates:
        raise SystemExit("--dedupe-only cannot be combined with --create-candidates")

    create_db_and_tables()
    with SessionLocal() as db:
        summary = CsvDatasetImporter(db).import_file(
            dataset=args.dataset,
            input_path=args.input,
            confirm=args.confirm,
            limit=args.limit,
            encoding=args.encoding,
            source_url=args.source_url,
            license_note=args.license_note,
            citation=args.citation,
            create_candidates=args.create_candidates,
            dedupe_only=args.dedupe_only,
            dataset_version=args.dataset_version,
        )
        if args.confirm:
            db.commit()
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
