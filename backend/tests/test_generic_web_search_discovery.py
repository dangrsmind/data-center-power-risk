from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = BACKEND_DIR / "tests" / "fixtures"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

from app.schemas.discovery import DiscoveredSource  # noqa: E402
from app.services.discovery_adapters.generic_web_search import (  # noqa: E402
    GENERIC_WEB_SEARCH_ADAPTER_ID,
    MockWebSearchProvider,
    GenericWebSearchDiscoveryAdapter,
    is_relevant_result,
    WebSearchResult,
)
from app.services.source_registry import load_source_registry  # noqa: E402
from run_public_discovery import run_sources  # noqa: E402


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
        result = GenericWebSearchDiscoveryAdapter(self._source()).run(dry_run=False)

        self.assertEqual(result.discovered_sources, [])
        self.assertTrue(any("generic_web_search_requires_search_api" in warning for warning in result.warnings))

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
        self.assertEqual(len(generic_results), 7)
        self.assertEqual(payload["sources_checked"], 11)
        self.assertEqual(payload["sources_discovered"], 0)
        self.assertTrue(any(result["planned_queries"] for result in generic_results))
        self.assertTrue(any("no adapter implemented" in warning for warning in payload["warnings"]))

    def test_run_public_discovery_non_dry_run_without_provider_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = run_sources(dry_run=False, output_dir=Path(tmpdir))

        self.assertTrue(any("generic_web_search_requires_search_api" in warning for warning in payload["warnings"]))

    def test_run_public_discovery_with_mock_provider_writes_output(self) -> None:
        old_provider = os.environ.get("WEB_SEARCH_PROVIDER")
        old_path = os.environ.get("WEB_SEARCH_MOCK_RESULTS_PATH")
        os.environ["WEB_SEARCH_PROVIDER"] = "mock"
        os.environ["WEB_SEARCH_MOCK_RESULTS_PATH"] = str(FIXTURES_DIR / "generic_web_search_results.json")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                payload = run_sources(dry_run=False, output_dir=Path(tmpdir))
                self.assertIsNotNone(payload["output_path"])
                self.assertTrue(Path(payload["output_path"]).exists())
                self.assertGreaterEqual(payload["sources_discovered"], 2)
        finally:
            if old_provider is None:
                os.environ.pop("WEB_SEARCH_PROVIDER", None)
            else:
                os.environ["WEB_SEARCH_PROVIDER"] = old_provider
            if old_path is None:
                os.environ.pop("WEB_SEARCH_MOCK_RESULTS_PATH", None)
            else:
                os.environ["WEB_SEARCH_MOCK_RESULTS_PATH"] = old_path

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
