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
from app.services.project_prediction_runner import run_prediction_for_project  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic prediction refresh for one project.")
    parser.add_argument("--project-id", type=uuid.UUID, required=True, help="Project ID to score.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with SessionLocal() as db:
        result = run_prediction_for_project(db, args.project_id)
        if not result.errors:
            db.commit()
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if result.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
