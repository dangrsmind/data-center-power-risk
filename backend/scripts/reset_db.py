from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import func, select, text


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal, engine
from app.models import Base
from app.models.evidence import Claim, Evidence
from app.models.project import Project


CONFIRM_TOKEN = "REAL_RESET"
DERIVED_TABLES = ["project_phase_quarter_features"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reset the configured database to an empty schema.")
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Drop and recreate the schema without loading demo or seed data.",
    )
    parser.add_argument(
        "--confirm",
        required=True,
        help=f"Required safety token. Use --confirm {CONFIRM_TOKEN}.",
    )
    return parser.parse_args()


def reset_schema_only() -> None:
    with engine.begin() as conn:
        for table_name in DERIVED_TABLES:
            conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def count_rows() -> dict[str, int]:
    with SessionLocal() as db:
        return {
            "projects": db.scalar(select(func.count()).select_from(Project)) or 0,
            "evidence": db.scalar(select(func.count()).select_from(Evidence)) or 0,
            "claims": db.scalar(select(func.count()).select_from(Claim)) or 0,
        }


def main() -> None:
    args = parse_args()
    if not args.schema_only:
        raise SystemExit("Refusing to reset without --schema-only.")
    if args.confirm != CONFIRM_TOKEN:
        raise SystemExit(f"Refusing to reset without --confirm {CONFIRM_TOKEN}.")

    reset_schema_only()
    counts = count_rows()
    print("Schema reset complete. No demo data loaded.")
    print(f"projects={counts['projects']} evidence={counts['evidence']} claims={counts['claims']}")


if __name__ == "__main__":
    main()
