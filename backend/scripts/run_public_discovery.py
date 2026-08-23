from __future__ import annotations

import argparse
from collections import Counter, defaultdict
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
from app.services.discovery_adapters.generic_web_search import (  # noqa: E402
    GENERIC_WEB_SEARCH_ADAPTER_ID,
    GENERIC_WEB_SEARCH_METHOD,
    GenericWebSearchDiscoveryAdapter,
    configured_provider_name,
    result_limit_from_env,
)
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
DEFAULT_SOURCE_FETCHES_DIR = REPO_DIR / "data" / "source_fetches"
IMPLEMENTED_ADAPTERS = {
    VIRGINIA_SCC_SOURCE_ID: VirginiaSccDiscoveryAdapter,
}
IMPLEMENTED_DISCOVERY_METHODS = {
    GENERIC_WEB_SEARCH_METHOD: GenericWebSearchDiscoveryAdapter,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run public-source data center discovery.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List enabled discovery sources without fetching web content.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print a readable read-only report of planned discovery queries without running discovery.",
    )
    parser.add_argument(
        "--report-format",
        choices=("text", "json"),
        default="text",
        help="Output format for --report. Defaults to readable text.",
    )
    parser.add_argument(
        "--query-count-warning-threshold",
        type=int,
        default=100,
        help="Warn in report mode when planned query count exceeds this threshold.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DISCOVERY_RUNS_DIR,
        help="Runtime discovery output directory. Ignored by Git.",
    )
    parser.add_argument(
        "--allow-insecure-fetch",
        action="store_true",
        help="DEV ONLY: disable SSL certificate verification for public fetches.",
    )
    parser.add_argument(
        "--write-fetch-cache",
        action="store_true",
        help="Write fetched content and metadata under an ignored runtime fetch cache.",
    )
    parser.add_argument(
        "--fetch-cache-dir",
        type=Path,
        default=DEFAULT_SOURCE_FETCHES_DIR,
        help="Runtime fetch cache directory. Ignored by Git.",
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


def adapter_for_source(source: Any, *, fetch_cache_dir: Path | None = None) -> Any | None:
    adapter_cls = IMPLEMENTED_ADAPTERS.get(source.id)
    if adapter_cls is not None:
        return adapter_cls(source, fetch_cache_dir=fetch_cache_dir)
    adapter_cls = IMPLEMENTED_DISCOVERY_METHODS.get(source.discovery_method)
    if adapter_cls is not None:
        return adapter_cls(source)
    return None


def planned_query_count(adapter_results: list[dict[str, Any]], *, adapter_id: str | None = None) -> int:
    count = 0
    for result in adapter_results:
        if adapter_id is not None and result.get("adapter_id") != adapter_id:
            continue
        planned_queries = result.get("planned_queries")
        if isinstance(planned_queries, list):
            count += len(planned_queries)
    return count


def build_discovery_plan_report(*, query_count_warning_threshold: int = 100) -> dict[str, Any]:
    registry = load_source_registry(DEFAULT_REGISTRY_PATH)
    query_rows: list[dict[str, Any]] = []
    warnings: list[str] = ["report_only: no live search was run and no runtime data was written"]
    duplicate_counts: Counter[str] = Counter()

    for source in registry.enabled_sources:
        adapter = adapter_for_source(source)
        adapter_id = getattr(adapter, "adapter_id", source.discovery_method) if adapter is not None else "unimplemented"
        planned_queries = adapter.planned_queries() if adapter is not None else []
        if not planned_queries:
            warnings.append(f"no_planned_queries for source {source.id}")
        for planned in planned_queries:
            query_text = str(planned.get("term") or "").strip()
            if not query_text:
                continue
            duplicate_counts[query_text] += 1
            query_warnings = query_warnings_for(source, query_text)
            query_rows.append(
                {
                    "query": query_text,
                    "provider": configured_provider_name(),
                    "adapter": adapter_id,
                    "source_id": source.id,
                    "source_name": source.name,
                    "source_type": source.source_type,
                    "risk_category_tags": risk_tags_for_query(source.source_type, query_text),
                    "geography": source.geography,
                    "scope": query_scope(source, query_text),
                    "search_target": str(source.base_url),
                    "priority": source.priority,
                    "warnings": query_warnings,
                }
            )
            warnings.extend(f"{query_text}: {warning}" for warning in query_warnings)

    duplicate_queries = sorted(query for query, count in duplicate_counts.items() if count > 1)
    for query in duplicate_queries:
        warnings.append(f"duplicate_query: {query} appears {duplicate_counts[query]} times")
    total_queries = len(query_rows)
    if total_queries > query_count_warning_threshold:
        warnings.append(
            f"query_count_above_threshold: {total_queries} planned queries exceeds threshold {query_count_warning_threshold}"
        )
    provider = configured_provider_name()
    if provider == "disabled":
        warnings.append("web_search_provider_disabled: report is safe; live search remains off")
    else:
        warnings.append(f"web_search_provider_configured: {provider}; report mode still did not call it")

    return {
        "summary": {
            "total_planned_queries": total_queries,
            "web_search_provider": provider,
            "web_search_max_results": result_limit_from_env(),
            "registry_path": str(DEFAULT_REGISTRY_PATH),
            "count_by_provider": dict(sorted(Counter(row["provider"] for row in query_rows).items())),
            "count_by_adapter": dict(sorted(Counter(row["adapter"] for row in query_rows).items())),
            "count_by_source_type": dict(sorted(Counter(row["source_type"] for row in query_rows).items())),
            "count_by_risk_category": dict(
                sorted(Counter(tag for row in query_rows for tag in row["risk_category_tags"]).items())
            ),
            "count_by_geography": dict(sorted(Counter(row["geography"] for row in query_rows).items())),
            "count_by_scope": dict(sorted(Counter(row["scope"] for row in query_rows).items())),
            "duplicate_query_count": len(duplicate_queries),
            "warning_count": len(warnings),
        },
        "details": query_rows,
        "warnings": sorted(dict.fromkeys(warnings)),
    }


def query_scope(source: Any, query_text: str) -> str:
    text = query_text.lower()
    geography = (source.geography or "").lower()
    if "site:" in text:
        return "location-scoped"
    if geography not in {"united states", "united states counties", "united states cities"}:
        return "location-scoped"
    if any(token in text for token in ("project", "campus", "site", "county", "city")):
        return "registry-scoped"
    return "generic"


def risk_tags_for_query(source_type: str, query_text: str) -> list[str]:
    text = query_text.lower()
    tags = {source_type}
    keyword_tags = {
        "grid_transmission": ("interconnection", "transmission", "substation", "load request", "large load"),
        "onsite_generation": ("onsite", "behind the meter", "dedicated power", "gas turbine", "diesel", "backup", "fuel cell"),
        "nuclear_smr": ("nuclear", "smr"),
        "air_emissions": ("air permit", "emissions", "nox", "pollution"),
        "water_cooling": ("water", "cooling", "wastewater", "drought"),
        "public_hearing": ("public hearing", "public meeting", "planning commission", "city council"),
        "zoning_land_use": ("zoning", "rezoning", "land use", "special use", "conditional use", "moratorium"),
        "litigation": ("lawsuit", "legal challenge", "litigation", "appeal"),
        "community_opposition": ("community opposition", "residents oppose", "noise", "traffic", "political opposition"),
        "cost_financing": ("tax incentives", "cost", "financing", "delayed", "paused", "cancelled", "canceled"),
    }
    for tag, keywords in keyword_tags.items():
        if any(keyword in text for keyword in keywords):
            tags.add(tag)
    return sorted(tags)


def query_warnings_for(source: Any, query_text: str) -> list[str]:
    warnings: list[str] = []
    text = query_text.lower().strip("\"'")
    scope = query_scope(source, query_text)
    very_generic_terms = {
        "data center delayed",
        "data center paused",
        "data center cancelled",
        "data center canceled",
        "data center financing",
        "data center pollution",
    }
    if scope == "generic":
        warnings.append("no_location_or_project_scope")
    if text in very_generic_terms:
        warnings.append("potentially_overbroad_query")
    return warnings


def format_discovery_plan_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "Discovery Dry-Run Plan Report",
        "=============================",
        "",
        "Summary",
        f"- Total planned queries: {summary['total_planned_queries']}",
        f"- Web search provider: {summary['web_search_provider']} (not called)",
        f"- Web search max results: {summary['web_search_max_results']}",
        f"- Registry: {summary['registry_path']}",
        f"- Duplicate queries: {summary['duplicate_query_count']}",
        f"- Warnings: {summary['warning_count']}",
        "",
        "Counts By Adapter",
        *format_counter_lines(summary["count_by_adapter"]),
        "",
        "Counts By Source Type",
        *format_counter_lines(summary["count_by_source_type"]),
        "",
        "Counts By Risk Category",
        *format_counter_lines(summary["count_by_risk_category"]),
        "",
        "Counts By Geography",
        *format_counter_lines(summary["count_by_geography"]),
        "",
        "Counts By Scope",
        *format_counter_lines(summary["count_by_scope"]),
        "",
        "Warnings",
    ]
    lines.extend(f"- {warning}" for warning in report["warnings"])
    lines.extend(["", "Planned Queries"])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in report["details"]:
        grouped[row["source_type"]].append(row)
    for source_type in sorted(grouped):
        lines.append("")
        lines.append(f"{source_type}")
        lines.append("-" * len(source_type))
        for row in grouped[source_type]:
            warning_text = f" warnings={','.join(row['warnings'])}" if row["warnings"] else ""
            lines.append(
                f"- {row['query']} [{row['adapter']}; {row['scope']}; {row['geography']}; {row['source_id']}]{warning_text}"
            )
    lines.append("")
    lines.append("No live search, URL fetch, database write, Project creation, ProjectCandidate creation, or promotion was run.")
    return "\n".join(lines)


def format_counter_lines(values: dict[str, int]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- {key}: {value}" for key, value in values.items()]


def run_sources(
    *,
    dry_run: bool,
    output_dir: Path = DEFAULT_DISCOVERY_RUNS_DIR,
    allow_insecure_fetch: bool = False,
    write_fetch_cache: bool = False,
    fetch_cache_dir: Path = DEFAULT_SOURCE_FETCHES_DIR,
) -> dict[str, Any]:
    registry = load_source_registry(DEFAULT_REGISTRY_PATH)
    enabled_sources = registry.enabled_sources
    warnings: list[str] = []
    errors: list[str] = []
    adapter_results: list[dict[str, Any]] = []
    discovered_sources: list[dict[str, Any]] = []

    if dry_run:
        warnings.append("dry_run_only: no web content was fetched and no runtime data was written")
    if allow_insecure_fetch:
        warnings.append(
            "INSECURE FETCH ENABLED: SSL certificate verification is disabled for local debugging only"
        )
    if write_fetch_cache:
        warnings.append(f"fetch cache writing enabled: fetched content/metadata will be written under {fetch_cache_dir}")

    for source in enabled_sources:
        adapter = adapter_for_source(source, fetch_cache_dir=fetch_cache_dir if write_fetch_cache else None)
        if adapter is None:
            warnings.append(f"no adapter implemented for source {source.id}; skipped")
            continue
        result = adapter.run(dry_run=dry_run, allow_insecure_fetch=allow_insecure_fetch)
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
        "allow_insecure_fetch": allow_insecure_fetch,
        "write_fetch_cache": write_fetch_cache,
        "fetch_cache_dir": str(fetch_cache_dir) if write_fetch_cache else None,
        "web_search_provider": configured_provider_name(),
        "web_search_max_results": result_limit_from_env(),
        "planned_search_query_count": planned_query_count(adapter_results),
        "planned_generic_web_search_query_count": planned_query_count(
            adapter_results,
            adapter_id=GENERIC_WEB_SEARCH_ADAPTER_ID,
        ),
        "registry_path": str(DEFAULT_REGISTRY_PATH),
        "enabled_sources": [source_preview(source) for source in enabled_sources],
        "implemented_adapters": sorted([*IMPLEMENTED_ADAPTERS, GENERIC_WEB_SEARCH_ADAPTER_ID]),
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
        if args.report:
            report = build_discovery_plan_report(query_count_warning_threshold=args.query_count_warning_threshold)
            if args.report_format == "json":
                print(json.dumps(report, indent=2, sort_keys=True))
            else:
                print(format_discovery_plan_report(report))
            raise SystemExit(0)
        payload = run_sources(
            dry_run=args.dry_run,
            output_dir=args.output_dir,
            allow_insecure_fetch=args.allow_insecure_fetch,
            write_fetch_cache=args.write_fetch_cache,
            fetch_cache_dir=args.fetch_cache_dir,
        )
    except SourceRegistryValidationError as exc:
        print(
            json.dumps(
                {
                    "errors": exc.errors,
                    "dry_run": args.dry_run,
                    "allow_insecure_fetch": args.allow_insecure_fetch,
                    "write_fetch_cache": args.write_fetch_cache,
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
