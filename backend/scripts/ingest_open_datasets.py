"""Local-file automated triage; defaults to read-only preview. Never fetches URLs."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.core.db import get_database_url
from app.services.open_dataset_registry import REGISTRY
from app.services.open_dataset_ingestion import ingest_open_dataset


def parse_args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',choices=REGISTRY,required=True)
    parser.add_argument('--input',type=Path,action='append',required=True,help='Explicit local CSV; repeat for related dataset files')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run',action='store_true')
    mode.add_argument('--confirm',action='store_true')
    for name in ('max-create-projects','max-create-candidates','max-write-rows'):
        parser.add_argument('--'+name,type=int)
    parser.add_argument('--limit',type=int,help='Explicit total input row limit; report records it (not a creation cap)')
    parser.add_argument('--include-row-details',action='store_true')
    parser.add_argument('--report-output',type=Path,help='New JSON report file; never overwrites')
    args=parser.parse_args(argv)
    caps=(args.max_create_projects,args.max_create_candidates,args.max_write_rows)
    if args.confirm and any(v is None for v in caps): parser.error('--confirm requires --max-create-projects, --max-create-candidates and --max-write-rows')
    if any(v is not None and v<0 for v in caps) or (args.limit is not None and args.limit<0): parser.error('Caps/limit must be nonnegative')
    if args.report_output and args.report_output.exists(): parser.error('Report already exists; refusing to overwrite')
    return args


def main(argv=None):
    args=parse_args(argv)
    url=make_url(get_database_url())
    if url.get_backend_name()=='sqlite':
        path=Path(url.database or '').resolve()
        if not path.is_file(): raise SystemExit('Existing migrated database required; no database created')
        uri=path.as_uri()+('?mode=rw' if args.confirm else '?mode=ro')
        engine=create_engine('sqlite://',creator=lambda:sqlite3.connect(uri,uri=True,timeout=30))
    else: engine=create_engine(url)
    try:
        with Session(engine,autoflush=False) as db:
            report=ingest_open_dataset(db,dataset=args.dataset,inputs=args.input,confirm=args.confirm,
                max_create_projects=args.max_create_projects,max_create_candidates=args.max_create_candidates,
                max_write_rows=args.max_write_rows,limit=args.limit,include_row_details=args.include_row_details)
        output=json.dumps(report,indent=2,sort_keys=True,allow_nan=False)
        print(output)
        if args.report_output:
            with args.report_output.open('x',encoding='utf8') as f: f.write(output+'\n')
        return 0
    except (ValueError,OSError,KeyError) as exc:
        print(f'Open dataset ingestion failed: {exc}',file=sys.stderr);return 2
    finally: engine.dispose()

if __name__=='__main__': raise SystemExit(main())
