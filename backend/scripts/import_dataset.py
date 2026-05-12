from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Date, DateTime, Numeric, func, select


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal, create_db_and_tables
from app.models.evidence import Claim, Evidence, FieldProvenance
from app.models.event import Event
from app.models.project import Phase, Project


IMPORT_MODELS = [
    Project,
    Phase,
    Evidence,
    Claim,
    FieldProvenance,
    Event,
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import dataset JSONL files into an empty database.")
    parser.add_argument("export_dir", type=Path, help="Directory containing exported JSONL files.")
    return parser.parse_args()


def deserialize_value(column: Any, value: Any) -> Any:
    if value is None:
        return None
    column_type = column.type
    if isinstance(column_type, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(column_type, Date):
        return date.fromisoformat(value)
    if isinstance(column_type, Numeric):
        return Decimal(str(value))
    return value


_LEGACY_COORD_SOURCE: dict[str, str] = {
    "starter_dataset": "imported_dataset",
    "manual_capture": "manual_review",
}


def deserialize_row(model: Any, row: dict[str, Any]) -> dict[str, Any]:
    columns = model.__table__.columns
    result = {column.name: deserialize_value(column, row[column.name]) for column in columns if column.name in row}
    if result.get("coordinate_source") in _LEGACY_COORD_SOURCE:
        result["coordinate_source"] = _LEGACY_COORD_SOURCE[result["coordinate_source"]]
    return result


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing export file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def assert_target_tables_empty() -> None:
    with SessionLocal() as db:
        non_empty = []
        for model in IMPORT_MODELS:
            count = db.scalar(select(func.count()).select_from(model)) or 0
            if count:
                non_empty.append(f"{model.__tablename__}={count}")
        if non_empty:
            details = ", ".join(non_empty)
            raise SystemExit(f"Refusing to import into non-empty dataset tables: {details}")


def main() -> None:
    args = parse_args()
    create_db_and_tables()
    assert_target_tables_empty()

    counts: dict[str, int] = {}
    with SessionLocal() as db:
        for model in IMPORT_MODELS:
            records = read_jsonl(args.export_dir / f"{model.__tablename__}.jsonl")
            for record in records:
                db.add(model(**deserialize_row(model, record)))
            db.flush()
            counts[model.__tablename__] = len(records)
        db.commit()

    print(f"Dataset imported from {args.export_dir}")
    for table_name, count in counts.items():
        print(f"{table_name}={count}")


if __name__ == "__main__":
    main()
