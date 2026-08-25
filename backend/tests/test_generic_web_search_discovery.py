from __future__ import annotations

import contextlib
import io
import os
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = BACKEND_DIR / "tests" / "fixtures"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

from app.schemas.discovery import DiscoveredSource  # noqa: E402
from app.services.discovery_adapters.generic_web_search import (  # noqa: E402
    BraveWebSearchProvider,
    GENERIC_WEB_SEARCH_ADAPTER_ID,
    MockWebSearchProvider,
    GenericWebSearchDiscoveryAdapter,
    parse_brave_search_response,
    is_relevant_result,
    WebSearchResult,
)
from app.services.public_fetch import FetchResult  # noqa: E402
from app.services.source_registry import load_source_registry  # noqa: E402
from run_public_discovery import run_sources  # noqa: E402
from run_public_discovery import (  # noqa: E402
    DiscoveryPlanFilterError,
    build_discovery_plan_report,
    format_discovery_plan_report,
    parse_args,
)


class StubFetchClient:
    def __init__(self, result: FetchResult):
        self.result = result
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def fetch(self, url: str, *, headers=None) -> FetchResult:
        self.calls.append((url, headers))
        return self.result


class GenericWebSearchDiscoveryTest(unittest.TestCase):
    def _source(self, source_id: str = "generic_county_planning_data_center_search"):
        registry = load_source_registry()
        return next(source for source in registry.sources if source.id == source_id)

    def test_generic_web_search_dry_run_lists_queries_without_provider_calls(self) -> None:
        provider = MockWebSearchProvider({"unused": []})
        result = GenericWebSearchDiscoveryAdapter(self._source(), provider=provider).run(dry_run=True)

        self.assertEqual(len(result.planned_queries), 4)
        self.assertEqual(result.discovered_sources, [])
        self.assertEqual(provider.calls, [])
        self.assertIn("query_configured_web_search_provider", result.planned_queries[0]["action"])

    def test_no_provider_configured_warns_without_crashing(self) -> None:
        with patch.dict(os.environ, {"WEB_SEARCH_PROVIDER": "disabled"}, clear=False):
            result = GenericWebSearchDiscoveryAdapter(self._source()).run(dry_run=False)

        self.assertEqual(result.discovered_sources, [])
        self.assertTrue(any("generic_web_search_requires_search_api" in warning for warning in result.warnings))

    def test_real_provider_missing_api_key_warns_without_crashing(self) -> None:
        with patch.dict(os.environ, {"WEB_SEARCH_PROVIDER": "brave"}, clear=False):
            os.environ.pop("WEB_SEARCH_API_KEY", None)
            result = GenericWebSearchDiscoveryAdapter(self._source()).run(dry_run=False)

        self.assertEqual(result.discovered_sources, [])
        self.assertTrue(any("web_search_api_key_missing" in warning for warning in result.warnings))

    def test_mock_provider_results_become_valid_discovered_sources_and_dedupe(self) -> None:
        provider = MockWebSearchProvider.from_path(FIXTURES_DIR / "generic_web_search_results.json")
        result = GenericWebSearchDiscoveryAdapter(self._source(), provider=provider).run(dry_run=False)

        self.assertEqual(len(result.discovered_sources), 1)
        discovered = result.discovered_sources[0]
        self.assertIsInstance(discovered, DiscoveredSource)
        self.assertEqual(discovered.source_url.unicode_string(), "https://planning.example.gov/agendas/2026-05-01-data-center.html")
        self.assertEqual(discovered.publisher, "Example County Planning")
        self.assertEqual(discovered.discovery_method, "web_search_pattern")
        self.assertEqual(discovered.source_registry_id, "generic_county_planning_data_center_search")
        self.assertEqual(discovered.adapter_id, GENERIC_WEB_SEARCH_ADAPTER_ID)
        self.assertEqual(discovered.search_term, '"planning commission" "data center"')
        self.assertEqual(discovered.raw_metadata_json["provider"], "mock")

    def test_mock_provider_env_defaults_to_committed_fixture(self) -> None:
        with patch.dict(os.environ, {"WEB_SEARCH_PROVIDER": "mock"}, clear=False):
            os.environ.pop("WEB_SEARCH_MOCK_RESULTS_PATH", None)
            result = GenericWebSearchDiscoveryAdapter(self._source()).run(dry_run=False)

        self.assertEqual(len(result.discovered_sources), 1)

    def test_mock_provider_utility_result_maps_source_type_and_infers_publisher(self) -> None:
        provider = MockWebSearchProvider.from_path(FIXTURES_DIR / "generic_web_search_results.json")
        result = GenericWebSearchDiscoveryAdapter(
            self._source("generic_utility_large_load_filing_search"),
            provider=provider,
        ).run(dry_run=False)

        self.assertEqual(len(result.discovered_sources), 1)
        discovered = result.discovered_sources[0]
        self.assertEqual(discovered.source_type, "utility_large_load_filings")
        self.assertEqual(discovered.publisher, "utility.example.com")
        self.assertIn("large load", discovered.snippet or "")

    def test_brave_parser_reads_representative_json_fixture(self) -> None:
        payload = (FIXTURES_DIR / "brave_search_response.json").read_text()

        results = parse_brave_search_response(json.loads(payload))

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].url, "https://planning.example.gov/agendas/data-center-rezoning")
        self.assertEqual(results[0].title, "Planning Commission agenda: data center rezoning")
        self.assertEqual(results[0].publisher, "Example Planning Department")
        self.assertEqual(results[0].raw_metadata["age"], "2026-05-20")

    def test_brave_provider_fetch_failure_warns_without_crashing(self) -> None:
        provider = BraveWebSearchProvider(
            api_key="test-key",
            fetch_client=StubFetchClient(
                FetchResult(
                    url="https://api.search.brave.com/res/v1/web/search?q=x",
                    ok=False,
                    status_code=401,
                    content_type="application/json",
                    text=None,
                    content_hash=None,
                    fetched_at="2026-06-02T00:00:00+00:00",
                    error_type="http_status_error",
                    error_message="HTTP 401",
                )
            ),
        )

        result = GenericWebSearchDiscoveryAdapter(self._source(), provider=provider).run(dry_run=False)

        self.assertEqual(result.discovered_sources, [])
        self.assertTrue(any("generic_web_search_provider_error" in warning for warning in result.warnings))

    def test_relevance_filter_skips_obvious_irrelevant_results(self) -> None:
        self.assertFalse(
            is_relevant_result(
                WebSearchResult(
                    url="https://jobs.example.com/data-center-training",
                    title="Data center training jobs",
                    snippet="Jobs at data center training program.",
                ),
                query='"data center"',
            )
        )

    def test_run_public_discovery_dry_run_includes_generic_planned_queries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = run_sources(dry_run=True, output_dir=Path(tmpdir))

        generic_results = [
            result for result in payload["adapter_results"] if result["adapter_id"] == GENERIC_WEB_SEARCH_ADAPTER_ID
        ]
        self.assertEqual(len(generic_results), 31)
        self.assertEqual(payload["sources_checked"], 35)
        self.assertEqual(payload["sources_discovered"], 0)
        self.assertEqual(payload["project_candidates_created"], 0)
        self.assertEqual(payload["planned_search_query_count"], 117)
        self.assertEqual(payload["planned_generic_web_search_query_count"], 113)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["web_search_provider"], "disabled")
        self.assertTrue(any(result["planned_queries"] for result in generic_results))
        self.assertTrue(
            any(result["source_id"] == "loudoun_county_data_center_planning_search" for result in generic_results)
        )
        self.assertTrue(any("no adapter implemented" in warning for warning in payload["warnings"]))

    def test_discovery_plan_report_groups_queries_and_warns_without_live_provider(self) -> None:
        with patch.dict(os.environ, {"WEB_SEARCH_PROVIDER": "disabled"}, clear=False):
            report = build_discovery_plan_report(query_count_warning_threshold=100)

        summary = report["summary"]
        self.assertEqual(summary["total_planned_queries"], 117)
        self.assertEqual(summary["web_search_provider"], "disabled")
        self.assertEqual(summary["count_by_adapter"]["generic_web_search"], 113)
        self.assertEqual(summary["count_by_adapter"]["virginia_scc"], 4)
        self.assertGreaterEqual(summary["count_by_source_type"]["air_permit"], 6)
        self.assertGreaterEqual(summary["count_by_risk_category"]["onsite_generation"], 1)
        self.assertGreaterEqual(summary["count_by_scope"]["generic"], 1)
        self.assertEqual(summary["duplicate_query_count"], 0)
        self.assertTrue(any("query_count_above_threshold" in warning for warning in report["warnings"]))
        self.assertTrue(any("web_search_provider_disabled" in warning for warning in report["warnings"]))
        self.assertTrue(any("potentially_overbroad_query" in warning for warning in report["warnings"]))
        self.assertTrue(
            any(row["query"] == '"data center air permit"' and row["source_type"] == "air_permit" for row in report["details"])
        )

    def test_discovery_plan_report_text_is_readable(self) -> None:
        report = build_discovery_plan_report(query_count_warning_threshold=100)

        text = format_discovery_plan_report(report)

        self.assertIn("Discovery Dry-Run Plan Report", text)
        self.assertIn("Total planned queries: 117", text)
        self.assertIn("Counts By Source Type", text)
        self.assertIn("No live search", text)

    def test_discovery_plan_report_cli_supports_text_output(self) -> None:
        text_result = subprocess.run(
            [sys.executable, "scripts/run_public_discovery.py", "--dry-run", "--report"],
            cwd=BACKEND_DIR,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

        self.assertEqual(text_result.returncode, 0, text_result.stderr)
        self.assertIn("Discovery Dry-Run Plan Report", text_result.stdout)
        self.assertIn("No live search", text_result.stdout)

    def test_discovery_plan_report_output_writes_text_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "full-plan.txt"
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/run_public_discovery.py",
                    "--dry-run",
                    "--report",
                    "--report-output",
                    str(output_path),
                ],
                cwd=BACKEND_DIR,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output_path.exists())
            text = output_path.read_text(encoding="utf-8")
            self.assertIn("Discovery Dry-Run Plan Report", text)
            self.assertIn("Active Filters", text)
            self.assertIn("Warnings", text)
            self.assertNotIn("Discovery Dry-Run Plan Report", result.stdout)
            self.assertIn("Discovery dry-run plan report written.", result.stdout)
            self.assertIn(f"Output path: {output_path}", result.stdout)
            self.assertIn("Retained planned queries: 117", result.stdout)
            self.assertIn("Active filters: none", result.stdout)
            self.assertIn("No live search", result.stdout)

    def test_discovery_plan_report_output_writes_json_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "high-exclude-generic-30.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/run_public_discovery.py",
                    "--dry-run",
                    "--report",
                    "--report-format",
                    "json",
                    "--priority",
                    "high",
                    "--exclude-generic",
                    "--max-planned-queries",
                    "30",
                    "--report-output",
                    str(output_path),
                ],
                cwd=BACKEND_DIR,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            stdout_result = subprocess.run(
                [
                    sys.executable,
                    "scripts/run_public_discovery.py",
                    "--dry-run",
                    "--report",
                    "--report-format",
                    "json",
                    "--priority",
                    "high",
                    "--exclude-generic",
                    "--max-planned-queries",
                    "30",
                ],
                cwd=BACKEND_DIR,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )

            self.assertEqual(stdout_result.returncode, 0, stdout_result.stderr)
            self.assertEqual(payload, json.loads(stdout_result.stdout))
            summary = payload["summary"]
            self.assertEqual(summary["active_filters"]["priority"], ["high"])
            self.assertTrue(summary["active_filters"]["exclude_generic"])
            self.assertEqual(summary["active_filters"]["max_planned_queries"], 30)
            self.assertEqual(summary["retained_total_planned_queries"], len(payload["details"]))
            self.assertTrue(payload["warnings"])
            self.assertIn("Retained planned queries:", result.stdout)
            self.assertNotIn('"details"', result.stdout)

    def test_discovery_plan_report_does_not_write_without_output_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            unexpected_path = Path(tmpdir) / "full-plan.txt"
            result = subprocess.run(
                [sys.executable, "scripts/run_public_discovery.py", "--dry-run", "--report"],
                cwd=BACKEND_DIR,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(unexpected_path.exists())
            self.assertIn("Discovery Dry-Run Plan Report", result.stdout)

    def test_discovery_plan_report_output_does_not_require_provider_or_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "plan.txt"
            db_path = Path(tmpdir) / "report-mode.db"
            env = {
                **os.environ,
                "WEB_SEARCH_PROVIDER": "brave",
                "DATABASE_URL": f"sqlite:///{db_path}",
            }
            env.pop("WEB_SEARCH_API_KEY", None)
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/run_public_discovery.py",
                    "--dry-run",
                    "--report",
                    "--report-output",
                    str(output_path),
                ],
                cwd=BACKEND_DIR,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output_path.exists())
            self.assertFalse(db_path.exists())
            self.assertNotIn("web_search_api_key_missing", result.stdout)
            self.assertNotIn("web_search_api_key_missing", output_path.read_text(encoding="utf-8"))

    def test_discovery_plan_snapshot_directory_is_ignored_by_git(self) -> None:
        result = subprocess.run(
            ["git", "check-ignore", "data/discovery_plan_snapshots/example.json"],
            cwd=BACKEND_DIR.parent,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_discovery_plan_report_json_shape_is_serializable(self) -> None:
        payload = json.loads(json.dumps(build_discovery_plan_report()))

        self.assertEqual(payload["summary"]["total_planned_queries"], 117)
        self.assertEqual(payload["summary"]["original_total_planned_queries"], 117)
        self.assertEqual(payload["summary"]["filtered_total_planned_queries"], 117)
        self.assertEqual(payload["summary"]["retained_total_planned_queries"], 117)
        self.assertEqual(payload["summary"]["active_filters"], {})
        self.assertFalse(payload["summary"]["capped"])
        self.assertEqual(payload["details"][0]["provider"], payload["summary"]["web_search_provider"])

    def test_discovery_plan_report_filters_by_priority(self) -> None:
        report = build_discovery_plan_report(filters={"priority": ["high"]})

        summary = report["summary"]
        self.assertLess(summary["retained_total_planned_queries"], summary["original_total_planned_queries"])
        self.assertEqual(summary["active_filters"], {"priority": ["high"]})
        self.assertTrue(report["details"])
        self.assertTrue(all(row["priority"] == "high" for row in report["details"]))

    def test_discovery_plan_report_filters_by_scope(self) -> None:
        report = build_discovery_plan_report(filters={"scope": ["location-scoped"]})

        self.assertTrue(report["details"])
        self.assertEqual(set(report["summary"]["count_by_scope"]), {"location-scoped"})
        self.assertTrue(all(row["scope"] == "location-scoped" for row in report["details"]))

    def test_discovery_plan_report_excludes_generic_scope(self) -> None:
        report = build_discovery_plan_report(filters={"exclude_generic": True})

        self.assertTrue(report["details"])
        self.assertNotIn("generic", report["summary"]["count_by_scope"])
        self.assertTrue(all(row["scope"] != "generic" for row in report["details"]))

    def test_discovery_plan_report_filters_by_category(self) -> None:
        report = build_discovery_plan_report(filters={"category": ["grid_transmission"]})

        self.assertTrue(report["details"])
        self.assertGreater(report["summary"]["count_by_risk_category"]["grid_transmission"], 0)
        self.assertTrue(all("grid_transmission" in row["risk_category_tags"] for row in report["details"]))

    def test_discovery_plan_report_filters_by_source_type(self) -> None:
        report = build_discovery_plan_report(filters={"source_type": ["utility_large_load_filings"]})

        self.assertTrue(report["details"])
        self.assertEqual(set(report["summary"]["count_by_source_type"]), {"utility_large_load_filings"})
        self.assertTrue(all(row["source_type"] == "utility_large_load_filings" for row in report["details"]))

    def test_discovery_plan_report_caps_after_filters_with_stable_order(self) -> None:
        full_report = build_discovery_plan_report()
        capped_report = build_discovery_plan_report(filters={"max_planned_queries": 5})

        summary = capped_report["summary"]
        self.assertTrue(summary["capped"])
        self.assertEqual(summary["cap_limit"], 5)
        self.assertEqual(summary["filtered_total_planned_queries"], full_report["summary"]["total_planned_queries"])
        self.assertEqual(summary["retained_total_planned_queries"], 5)
        self.assertEqual(
            [row["query"] for row in capped_report["details"]],
            [row["query"] for row in full_report["details"][:5]],
        )
        self.assertTrue(any("planned_query_cap_applied" in warning for warning in capped_report["warnings"]))

    def test_discovery_plan_report_json_includes_filter_counts(self) -> None:
        report = build_discovery_plan_report(
            filters={"priority": ["high"], "exclude_generic": True, "max_planned_queries": 10}
        )
        payload = json.loads(json.dumps(report))

        summary = payload["summary"]
        self.assertEqual(summary["original_total_planned_queries"], 117)
        self.assertLessEqual(summary["retained_total_planned_queries"], 10)
        self.assertEqual(
            summary["active_filters"],
            {"priority": ["high"], "exclude_generic": True, "max_planned_queries": 10},
        )
        self.assertTrue(all(row["priority"] == "high" and row["scope"] != "generic" for row in payload["details"]))

    def test_discovery_plan_report_valid_zero_match_filter_warns(self) -> None:
        report = build_discovery_plan_report(filters={"category": ["nuclear_smr"], "scope": ["location-scoped"]})

        self.assertEqual(report["summary"]["filtered_total_planned_queries"], 0)
        self.assertEqual(report["summary"]["retained_total_planned_queries"], 0)
        self.assertEqual(report["details"], [])
        self.assertTrue(any("filters_returned_zero_planned_queries" in warning for warning in report["warnings"]))

    def test_discovery_plan_report_rejects_unknown_filters(self) -> None:
        for filters in (
            {"category": ["not_a_category"]},
            {"source_type": ["not_a_source_type"]},
            {"source_id": ["not_a_source_id"]},
        ):
            with self.subTest(filters=filters):
                with self.assertRaises(DiscoveryPlanFilterError):
                    build_discovery_plan_report(filters=filters)

    def test_discovery_plan_report_cli_rejects_invalid_filter_values(self) -> None:
        invalid_commands = (
            ["--scope", "not-a-scope"],
            ["--priority", "urgent"],
            ["--max-planned-queries", "0"],
        )
        for command in invalid_commands:
            with self.subTest(command=command):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        parse_args(["--dry-run", "--report", *command])

        result = subprocess.run(
            [sys.executable, "scripts/run_public_discovery.py", "--dry-run", "--report", "--category", "not_a_category"],
            cwd=BACKEND_DIR,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

        self.assertNotEqual(result.returncode, 0)

    def test_targeted_official_entries_plan_queries_without_provider_calls(self) -> None:
        provider = MockWebSearchProvider({"unused": []})
        result = GenericWebSearchDiscoveryAdapter(
            self._source("texas_puct_large_load_data_center_search"),
            provider=provider,
        ).run(dry_run=True)

        self.assertEqual(len(result.planned_queries), 2)
        self.assertEqual(provider.calls, [])
        self.assertIn("site:puc.texas.gov", result.planned_queries[0]["term"])

    def test_run_public_discovery_non_dry_run_without_provider_does_not_crash(self) -> None:
        with patch.dict(os.environ, {"WEB_SEARCH_PROVIDER": "disabled"}, clear=False):
            with tempfile.TemporaryDirectory() as tmpdir:
                payload = run_sources(dry_run=False, output_dir=Path(tmpdir))

        self.assertTrue(any("generic_web_search_requires_search_api" in warning for warning in payload["warnings"]))
        self.assertEqual(payload["web_search_provider"], "disabled")

    def test_run_public_discovery_with_mock_provider_writes_output(self) -> None:
        with patch.dict(
            os.environ,
            {
                "WEB_SEARCH_PROVIDER": "mock",
                "WEB_SEARCH_MOCK_RESULTS_PATH": str(FIXTURES_DIR / "generic_web_search_results.json"),
            },
            clear=False,
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                payload = run_sources(dry_run=False, output_dir=Path(tmpdir))
                self.assertIsNotNone(payload["output_path"])
                self.assertTrue(Path(payload["output_path"]).exists())
                self.assertGreaterEqual(payload["sources_discovered"], 2)
                self.assertEqual(payload["web_search_provider"], "mock")

    def test_unimplemented_sources_do_not_crash_discovery_run_cli(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/run_public_discovery.py", "--dry-run"],
            cwd=BACKEND_DIR,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("generic_web_search", result.stdout)


if __name__ == "__main__":
    unittest.main()
