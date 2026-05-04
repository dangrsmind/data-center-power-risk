from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal
from app.models.evidence import Claim, Evidence, FieldProvenance
from app.models.event import Event
from app.models.project import Phase, Project


EXPORT_MODELS = [
    Project,
    Phase,
    Evidence,
    Claim,
    FieldProvenance,
    Event,
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export the dataset tables to JSONL files.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to data/exports/YYYYMMDD under the backend directory.",
    )
    return parser.parse_args()


def default_output_dir() -> Path:
    return BACKEND_DIR / "data" / "exports" / datetime.now().strftime("%Y%m%d")


def serialize_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def row_to_dict(row: Any) -> dict[str, Any]:
    return {column.name: serialize_value(getattr(row, column.name)) for column in row.__table__.columns}


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    with SessionLocal() as db:
        for model in EXPORT_MODELS:
            rows = db.scalars(select(model).order_by(model.id)).all()
            records = [row_to_dict(row) for row in rows]
            write_jsonl(output_dir / f"{model.__tablename__}.jsonl", records)
            counts[model.__tablename__] = len(records)

    manifest = {
        "exported_at": datetime.now().isoformat(),
        "format": "jsonl",
        "tables": [model.__tablename__ for model in EXPORT_MODELS],
        "counts": counts,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Dataset exported to {output_dir}")
    for table_name, count in counts.items():
        print(f"{table_name}={count}")


if __name__ == "__main__":
    main()
