from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.discovery import DiscoveryRunSummary  # noqa: E402
from app.services.source_registry import (  # noqa: E402
    DEFAULT_REGISTRY_PATH,
    SourceRegistryValidationError,
    load_source_registry,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run public-source data center discovery.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List enabled discovery sources without fetching web content.",
    )
    return parser.parse_args()


def source_preview(source: Any) -> dict[str, Any]:
    return {
        "id": source.id,
        "name": source.name,
        "source_type": source.source_type,
        "geography": source.geography,
        "base_url": str(source.base_url),
        "discovery_method": source.discovery_method,
        "priority": source.priority,
        "search_terms": source.search_terms,
    }


def build_dry_run_summary() -> dict[str, Any]:
    registry = load_source_registry(DEFAULT_REGISTRY_PATH)
    enabled_sources = registry.enabled_sources
    summary = DiscoveryRunSummary(
        sources_checked=len(enabled_sources),
        warnings=["dry_run_only: no web content was fetched and no runtime data was written"],
    )
    return {
        **summary.model_dump(),
        "dry_run": True,
        "registry_path": str(DEFAULT_REGISTRY_PATH),
        "enabled_sources": [source_preview(source) for source in enabled_sources],
        "would_run": [
            f"{source.id}: {source.discovery_method} against {source.base_url}"
            for source in enabled_sources
        ],
    }


def main() -> None:
    args = parse_args()
    if not args.dry_run:
        print(
            json.dumps(
                {
                    "errors": ["public discovery fetching is not implemented yet; run with --dry-run"],
                    "dry_run": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(1)

    try:
        payload = build_dry_run_summary()
    except SourceRegistryValidationError as exc:
        print(
            json.dumps(
                {
                    "errors": exc.errors,
                    "dry_run": True,
                    "enabled_sources": [],
                    "would_run": [],
                },
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(1) from exc

    print(json.dumps(payload, indent=2, sort_keys=True))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
