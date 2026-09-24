"""Preview existing candidates locally; confirmed promotion requires an explicit cap."""
import argparse
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--confirm', action='store_true')
    parser.add_argument('--max-promote', type=int)
    parser.add_argument('--min-confidence', type=float, default=.80)
    parser.add_argument('--dataset', help='Exact dataset identifier; matches stored/audited provenance')
    parser.add_argument('--source', help='Case-insensitive primary source URL substring')
    parser.add_argument('--limit', type=int, help='Explicit candidate window after filters, ordered oldest first then ID')
    parser.add_argument('--candidate-id', action='append', type=uuid.UUID, default=[])
    parser.add_argument('--include-row-details', action='store_true')
    parser.add_argument('--report-output', type=Path, help='Optional new JSON file; never overwritten')
    args = parser.parse_args(argv)
    if args.confirm and args.max_promote is None:
        parser.error('--confirm requires --max-promote')
    if args.max_promote is not None and args.max_promote < 0 or args.limit is not None and args.limit < 0:
        parser.error('Caps and limit must be nonnegative')
    if not math.isfinite(args.min_confidence) or not 0 <= args.min_confidence <= 1:
        parser.error('--min-confidence must be finite and between 0 and 1')
    if args.report_output and args.report_output.exists():
        parser.error('Report already exists; refusing to overwrite')
    return args


def main(argv=None):
    args = parse_args(argv)
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    from app.services.automated_candidate_promotion import auto_promote_candidates

    url = make_url(os.environ.get('DATABASE_URL', 'sqlite:///' + str(Path(__file__).resolve().parents[1] / 'local.db')))
    if url.get_backend_name() == 'sqlite':
        path = Path(url.database or '').resolve()
        if not path.is_file():
            raise SystemExit('Existing migrated SQLite database required; no database created')
        uri = path.as_uri() + ('?mode=rw' if args.confirm else '?mode=ro')
        engine = create_engine('sqlite://', creator=lambda: sqlite3.connect(uri, uri=True, timeout=30))
    else:
        engine = create_engine(url)
    try:
        with Session(engine, autoflush=False) as db:
            if not args.confirm and engine.dialect.name == 'postgresql':
                db.execute(text('SET TRANSACTION READ ONLY'))
            report = auto_promote_candidates(db, confirm=args.confirm, max_promote=args.max_promote,
                min_confidence=args.min_confidence, dataset=args.dataset, source=args.source,
                limit=args.limit, candidate_ids=args.candidate_id, include_row_details=args.include_row_details)
        output = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
        print(output)
        if args.report_output:
            with args.report_output.open('x', encoding='utf8') as handle:
                handle.write(output + '\n')
        return 0
    except (ValueError, OSError) as exc:
        print(f'Automated promotion failed: {exc}', file=sys.stderr)
        return 2
    finally:
        engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
