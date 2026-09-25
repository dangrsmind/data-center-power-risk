"""Classify existing candidates for resolution. Dry-run only; never resolves or promotes."""
import argparse
import json
import math
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Read-only mode (also the default)')
    parser.add_argument('--include-row-details', action='store_true')
    parser.add_argument('--limit', type=int, help='Explicit window in creation-time / ID order')
    parser.add_argument('--min-confidence', type=float, default=.80)
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 0:
        parser.error('--limit must be nonnegative')
    if not math.isfinite(args.min_confidence) or not 0 <= args.min_confidence <= 1:
        parser.error('--min-confidence must be finite and between 0 and 1')
    return args


def main(argv=None):
    args = parse_args(argv)
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    from app.services.candidate_resolution import resolve_candidate_backlog

    url = make_url(os.environ.get('DATABASE_URL', 'sqlite:///' + str(Path(__file__).resolve().parents[1] / 'local.db')))
    if url.get_backend_name() == 'sqlite':
        path = Path(url.database or '').resolve()
        if not path.is_file():
            raise SystemExit('Existing migrated database required; no database created')
        engine = create_engine('sqlite://', creator=lambda: sqlite3.connect(path.as_uri() + '?mode=ro', uri=True))
    elif url.get_backend_name() == 'postgresql':
        engine = create_engine(url)
    else:
        raise SystemExit('Read-only CLI supports SQLite and PostgreSQL')
    try:
        with Session(engine, autoflush=False) as db:
            if engine.dialect.name == 'postgresql':
                db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
            else:
                db.execute(text('BEGIN'))  # One consistent read snapshot across both reports.
            report = resolve_candidate_backlog(db, limit=args.limit, min_confidence=args.min_confidence,
                include_row_details=args.include_row_details)
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError) as exc:
        print(f'Candidate resolution report failed: {exc}', file=sys.stderr)
        return 2
    finally:
        engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
