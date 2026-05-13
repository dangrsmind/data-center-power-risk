from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal, create_db_and_tables  # noqa: E402
from app.services.discovered_source_service import DiscoveredSourceService  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest public discovery-run source JSON into discovered_sources.")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to a discovery-run discovered_sources.json file.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize without writing rows.")
    parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="Update existing rows with matching source_url instead of skipping them.",
    )
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    if path.is_absolute() or path.exists():
        return path
    return REPO_DIR / path


def infer_discovery_run_id(path: Path) -> str | None:
    if path.name == "discovered_sources.json" and path.parent.name:
        return path.parent.name
    return None


def load_discovered_source_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, str | None]]:
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"input file is not valid JSON: {exc}") from exc

    context: dict[str, str | None] = {
        "adapter_id": None,
        "source_registry_id": None,
    }
    if isinstance(payload, list):
        return payload, context
    if not isinstance(payload, dict):
        raise SystemExit("input JSON must be a list of discovered source records or a discovery summary object")
    if isinstance(payload.get("discovered_sources"), list):
        return payload["discovered_sources"], context

    rows: list[dict[str, Any]] = []
    for adapter_result in payload.get("adapter_results", []):
        if not isinstance(adapter_result, dict):
            continue
        adapter_id = adapter_result.get("adapter_id")
        source_id = adapter_result.get("source_id")
        for row in adapter_result.get("discovered_sources", []):
            if isinstance(row, dict):
                enriched = {
                    "adapter_id": adapter_id,
                    "source_registry_id": source_id,
                    **row,
                }
                rows.append(enriched)
    if rows:
        return rows, context
    raise SystemExit("input JSON does not contain discovered source records")


def main() -> None:
    args = parse_args()
    input_path = resolve_path(args.input)
    rows, context = load_discovered_source_rows(input_path)
    discovery_run_id = infer_discovery_run_id(input_path)

    with SessionLocal() as db:
        if not args.dry_run:
            create_db_and_tables()
        summary = DiscoveredSourceService(db).ingest_rows(
            rows,
            dry_run=args.dry_run,
            allow_existing=args.allow_existing,
            discovery_run_id=discovery_run_id,
            adapter_id=context["adapter_id"],
            source_registry_id=context["source_registry_id"],
        )
        if not args.dry_run:
            db.commit()

    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
