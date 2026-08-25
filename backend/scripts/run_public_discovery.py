from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import re
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
        "--category",
        action="append",
        help="Report mode: keep planned queries tagged with this risk/source category. May be repeated.",
    )
    parser.add_argument(
        "--source-type",
        action="append",
        help="Report mode: keep planned queries from this source type. May be repeated.",
    )
    parser.add_argument(
        "--priority",
        action="append",
        choices=("high", "medium", "low"),
        help="Report mode: keep planned queries from sources with this priority. May be repeated.",
    )
    parser.add_argument(
        "--scope",
        action="append",
        choices=("generic", "location-scoped", "registry-scoped"),
        help="Report mode: keep planned queries with this query scope. May be repeated.",
    )
    parser.add_argument(
        "--geography",
        action="append",
        help="Report mode: keep planned queries for this geography. May be repeated.",
    )
    parser.add_argument(
        "--adapter",
        action="append",
        help="Report mode: keep planned queries from this adapter. May be repeated.",
    )
    parser.add_argument(
        "--source-id",
        action="append",
        help="Report mode: keep planned queries from this source id. May be repeated.",
    )
    parser.add_argument(
        "--exclude-generic",
        action="store_true",
        help="Report mode: remove generic planned queries and keep location- or registry-scoped queries.",
    )
    parser.add_argument(
        "--max-planned-queries",
        type=positive_int,
        help="Report mode: retain at most this many planned queries after filters are applied.",
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


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


class DiscoveryPlanFilterError(ValueError):
    pass


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


def report_filters_from_args(args: argparse.Namespace) -> dict[str, Any]:
    filters: dict[str, Any] = {
        "category": args.category or [],
        "source_type": args.source_type or [],
        "priority": args.priority or [],
        "scope": args.scope or [],
        "geography": args.geography or [],
        "adapter": args.adapter or [],
        "source_id": args.source_id or [],
        "exclude_generic": args.exclude_generic,
        "max_planned_queries": args.max_planned_queries,
    }
    return {key: value for key, value in filters.items() if value not in (None, False, [])}


def build_discovery_plan_report(
    *,
    query_count_warning_threshold: int = 100,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = load_source_registry(DEFAULT_REGISTRY_PATH)
    all_query_rows: list[dict[str, Any]] = []
    source_warnings: list[str] = []

    for source in registry.enabled_sources:
        adapter = adapter_for_source(source)
        adapter_id = getattr(adapter, "adapter_id", source.discovery_method) if adapter is not None else "unimplemented"
        planned_queries = adapter.planned_queries() if adapter is not None else []
        if not planned_queries:
            source_warnings.append(f"no_planned_queries for source {source.id}")
        for planned in planned_queries:
            query_text = str(planned.get("term") or "").strip()
            if not query_text:
                continue
            query_warnings = query_warnings_for(source, query_text)
            all_query_rows.append(
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

    active_filters = normalize_report_filters(filters)
    validate_report_filters(active_filters, all_query_rows)
    filtered_query_rows = [row for row in all_query_rows if report_row_matches_filters(row, active_filters)]
    filtered_total = len(filtered_query_rows)
    cap_limit = active_filters.get("max_planned_queries")
    retained_query_rows = filtered_query_rows[:cap_limit] if cap_limit is not None else filtered_query_rows
    capped = cap_limit is not None and filtered_total > cap_limit
    duplicate_counts: Counter[str] = Counter(row["query"] for row in retained_query_rows)
    duplicate_queries = sorted(query for query, count in duplicate_counts.items() if count > 1)
    retained_total = len(retained_query_rows)
    warnings: list[str] = ["report_only: no live search was run and no runtime data was written"]
    if not active_filters:
        warnings.extend(source_warnings)
    for row in retained_query_rows:
        warnings.extend(f"{row['query']}: {warning}" for warning in row["warnings"])
    for query in duplicate_queries:
        warnings.append(f"duplicate_query: {query} appears {duplicate_counts[query]} times")
    if filtered_total == 0:
        warnings.append("filters_returned_zero_planned_queries: no planned queries matched the active filters")
    if capped:
        warnings.append(
            f"planned_query_cap_applied: retained {retained_total} of {filtered_total} filtered planned queries"
        )
    if retained_total > query_count_warning_threshold:
        warnings.append(
            f"query_count_above_threshold: {retained_total} planned queries exceeds threshold {query_count_warning_threshold}"
        )
    provider = configured_provider_name()
    if provider == "disabled":
        warnings.append("web_search_provider_disabled: report is safe; live search remains off")
    else:
        warnings.append(f"web_search_provider_configured: {provider}; report mode still did not call it")
    warnings = sorted(dict.fromkeys(warnings))

    return {
        "summary": {
            "total_planned_queries": retained_total,
            "original_total_planned_queries": len(all_query_rows),
            "filtered_total_planned_queries": filtered_total,
            "retained_total_planned_queries": retained_total,
            "active_filters": active_filters,
            "capped": capped,
            "cap_limit": cap_limit,
            "web_search_provider": provider,
            "web_search_max_results": result_limit_from_env(),
            "registry_path": str(DEFAULT_REGISTRY_PATH),
            "count_by_provider": dict(sorted(Counter(row["provider"] for row in retained_query_rows).items())),
            "count_by_adapter": dict(sorted(Counter(row["adapter"] for row in retained_query_rows).items())),
            "count_by_source_type": dict(sorted(Counter(row["source_type"] for row in retained_query_rows).items())),
            "count_by_risk_category": dict(
                sorted(Counter(tag for row in retained_query_rows for tag in row["risk_category_tags"]).items())
            ),
            "count_by_geography": dict(sorted(Counter(row["geography"] for row in retained_query_rows).items())),
            "count_by_scope": dict(sorted(Counter(row["scope"] for row in retained_query_rows).items())),
            "duplicate_query_count": len(duplicate_queries),
            "warning_count": len(warnings),
        },
        "details": retained_query_rows,
        "warnings": warnings,
    }


def normalize_report_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    if filters is None:
        return {}
    normalized: dict[str, Any] = {}
    for key in ("category", "source_type", "priority", "scope", "geography", "adapter", "source_id"):
        values = filters.get(key)
        if values is None:
            continue
        if isinstance(values, str):
            values = [values]
        clean_values = [str(value).strip() for value in values if str(value).strip()]
        if clean_values:
            normalized[key] = clean_values
    if filters.get("exclude_generic"):
        normalized["exclude_generic"] = True
    cap_limit = filters.get("max_planned_queries")
    if cap_limit is not None:
        try:
            cap_limit = int(cap_limit)
        except (TypeError, ValueError) as exc:
            raise DiscoveryPlanFilterError("max_planned_queries must be a positive integer") from exc
        if cap_limit <= 0:
            raise DiscoveryPlanFilterError("max_planned_queries must be a positive integer")
        normalized["max_planned_queries"] = cap_limit
    return normalized


def validate_report_filters(filters: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    known_values = {
        "category": {tag for row in rows for tag in row["risk_category_tags"]},
        "source_type": {row["source_type"] for row in rows},
        "priority": {row["priority"] for row in rows},
        "scope": {row["scope"] for row in rows},
        "geography": {row["geography"] for row in rows},
        "adapter": {row["adapter"] for row in rows},
        "source_id": {row["source_id"] for row in rows},
    }
    for key, known in known_values.items():
        unknown = sorted(set(filters.get(key, [])) - known)
        if unknown:
            known_text = ", ".join(sorted(known)) or "none"
            raise DiscoveryPlanFilterError(f"unknown {key.replace('_', '-')} filter {unknown}; known values: {known_text}")


def report_row_matches_filters(row: dict[str, Any], filters: dict[str, Any]) -> bool:
    if filters.get("exclude_generic") and row["scope"] == "generic":
        return False
    field_filters = {
        "source_type": row["source_type"],
        "priority": row["priority"],
        "scope": row["scope"],
        "geography": row["geography"],
        "adapter": row["adapter"],
        "source_id": row["source_id"],
    }
    for key, value in field_filters.items():
        if key in filters and value not in filters[key]:
            return False
    if "category" in filters and not set(filters["category"]).intersection(row["risk_category_tags"]):
        return False
    return True


def query_scope(source: Any, query_text: str) -> str:
    text = query_text.lower()
    geography = (source.geography or "").lower()
    if "site:" in text:
        return "location-scoped"
    if geography not in {"united states", "united states counties", "united states cities"}:
        return "location-scoped"
    if any(re.search(rf"\b{re.escape(token)}\b", text) for token in ("project", "campus", "site", "county", "city")):
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
    cap_text = (
        f"yes, retained {summary['retained_total_planned_queries']} of {summary['filtered_total_planned_queries']}"
        if summary["capped"]
        else "no"
    )
    lines = [
        "Discovery Dry-Run Plan Report",
        "=============================",
        "",
        "Summary",
        f"- Total planned queries: {summary['total_planned_queries']}",
        f"- Original planned queries: {summary['original_total_planned_queries']}",
        f"- Filtered planned queries: {summary['filtered_total_planned_queries']}",
        f"- Retained planned queries: {summary['retained_total_planned_queries']}",
        f"- Capped: {cap_text}",
        f"- Cap limit: {summary['cap_limit'] if summary['cap_limit'] is not None else 'none'}",
        f"- Web search provider: {summary['web_search_provider']} (not called)",
        f"- Web search max results: {summary['web_search_max_results']}",
        f"- Registry: {summary['registry_path']}",
        f"- Duplicate queries: {summary['duplicate_query_count']}",
        f"- Warnings: {summary['warning_count']}",
        "",
        "Active Filters",
        *format_filter_lines(summary["active_filters"]),
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


def format_filter_lines(values: dict[str, Any]) -> list[str]:
    if not values:
        return ["- none"]
    lines = []
    for key, value in values.items():
        if isinstance(value, list):
            value_text = ", ".join(value)
        else:
            value_text = str(value)
        lines.append(f"- {key}: {value_text}")
    return lines


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
            report = build_discovery_plan_report(
                query_count_warning_threshold=args.query_count_warning_threshold,
                filters=report_filters_from_args(args),
            )
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
    except DiscoveryPlanFilterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(json.dumps(payload, indent=2, sort_keys=True))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
