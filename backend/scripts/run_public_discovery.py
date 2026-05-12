from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.discovery import DiscoveryRunSummary  # noqa: E402
from app.services.discovery_adapters.virginia_scc import (  # noqa: E402
    VIRGINIA_SCC_SOURCE_ID,
    VirginiaSccDiscoveryAdapter,
)
from app.services.source_registry import (  # noqa: E402
    DEFAULT_REGISTRY_PATH,
    SourceRegistryValidationError,
    load_source_registry,
)


DEFAULT_DISCOVERY_RUNS_DIR = REPO_DIR / "data" / "discovery_runs"
IMPLEMENTED_ADAPTERS = {
    VIRGINIA_SCC_SOURCE_ID: VirginiaSccDiscoveryAdapter,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run public-source data center discovery.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List enabled discovery sources without fetching web content.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DISCOVERY_RUNS_DIR,
        help="Runtime discovery output directory. Ignored by Git.",
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


def adapter_for_source(source: Any) -> Any | None:
    adapter_cls = IMPLEMENTED_ADAPTERS.get(source.id)
    if adapter_cls is None:
        return None
    return adapter_cls(source)


def run_sources(*, dry_run: bool, output_dir: Path = DEFAULT_DISCOVERY_RUNS_DIR) -> dict[str, Any]:
    registry = load_source_registry(DEFAULT_REGISTRY_PATH)
    enabled_sources = registry.enabled_sources
    warnings: list[str] = []
    errors: list[str] = []
    adapter_results: list[dict[str, Any]] = []
    discovered_sources: list[dict[str, Any]] = []

    if dry_run:
        warnings.append("dry_run_only: no web content was fetched and no runtime data was written")

    for source in enabled_sources:
        adapter = adapter_for_source(source)
        if adapter is None:
            warnings.append(f"no adapter implemented for source {source.id}; skipped")
            continue
        result = adapter.run(dry_run=dry_run)
        adapter_results.append(result.to_dict())
        warnings.extend(result.warnings)
        errors.extend(result.errors)
        discovered_sources.extend(source.model_dump(mode="json") for source in result.discovered_sources)

    output_path: Path | None = None
    if not dry_run and discovered_sources:
        output_path = write_discovery_output(output_dir, discovered_sources)

    summary = DiscoveryRunSummary(
        sources_checked=len(enabled_sources),
        sources_discovered=len(discovered_sources),
        warnings=warnings,
        errors=errors,
        output_path=str(output_path) if output_path else None,
    )
    return {
        **summary.model_dump(),
        "dry_run": dry_run,
        "registry_path": str(DEFAULT_REGISTRY_PATH),
        "enabled_sources": [source_preview(source) for source in enabled_sources],
        "implemented_adapters": sorted(IMPLEMENTED_ADAPTERS),
        "adapter_results": adapter_results,
        "would_run": build_would_run(enabled_sources),
    }


def build_would_run(enabled_sources: list[Any]) -> list[str]:
    return [
        f"{source.id}: {source.discovery_method} against {source.base_url}"
        for source in enabled_sources
    ]


def write_discovery_output(output_dir: Path, discovered_sources: list[dict[str, Any]]) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=False)
    output_path = run_dir / "discovered_sources.json"
    output_path.write_text(json.dumps(discovered_sources, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def main() -> None:
    args = parse_args()
    try:
        payload = run_sources(dry_run=args.dry_run, output_dir=args.output_dir)
    except SourceRegistryValidationError as exc:
        print(
            json.dumps(
                {
                    "errors": exc.errors,
                    "dry_run": args.dry_run,
                    "enabled_sources": [],
                    "adapter_results": [],
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
