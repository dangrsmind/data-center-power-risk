from __future__ import annotations

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
from app.services.discovery_adapters.virginia_scc import (  # noqa: E402
    VirginiaSccDiscoveryAdapter,
    extract_searchstax_config,
    normalize_url,
    parse_searchstax_response,
    parse_scc_search_results,
)
from app.services.public_fetch import FetchResult  # noqa: E402
from app.services.source_registry import load_source_registry  # noqa: E402
from run_public_discovery import run_sources  # noqa: E402


class StubFetchClient:
    def __init__(self, result: FetchResult):
        self.result = result
        self.calls: list[str] = []
        self.allow_insecure_fetch = result.insecure_fetch

    def fetch(self, url: str, *, headers=None) -> FetchResult:
        self.calls.append(url)
        return self.result


class SequenceFetchClient:
    def __init__(self, results: list[FetchResult]):
        self.results = results
        self.calls: list[tuple[str, dict[str, str] | None]] = []
        self.allow_insecure_fetch = False

    def fetch(self, url: str, *, headers=None) -> FetchResult:
        self.calls.append((url, headers))
        if not self.results:
            raise AssertionError(f"unexpected fetch: {url}")
        return self.results.pop(0)


class VirginiaSccDiscoveryTest(unittest.TestCase):
    def _source(self):
        registry = load_source_registry()
        return next(source for source in registry.sources if source.id == "virginia_scc_data_center_large_load_dockets")

    def test_virginia_scc_dry_run_returns_planned_queries(self) -> None:
        fetch_client = StubFetchClient(
            FetchResult(
                url="https://example.test",
                ok=True,
                status_code=200,
                content_type="text/html",
                text="<html></html>",
                content_hash="hash",
                fetched_at="2026-05-13T00:00:00+00:00",
            )
        )
        result = VirginiaSccDiscoveryAdapter(self._source(), fetch_client=fetch_client).run(dry_run=True)

        self.assertEqual(len(result.planned_queries), 4)
        terms = {query["term"] for query in result.planned_queries}
        self.assertIn("data center", terms)
        self.assertIn("large load", terms)
        self.assertEqual(result.discovered_sources, [])
        self.assertEqual(fetch_client.calls, [])

    def test_discovered_source_records_validate(self) -> None:
        adapter = VirginiaSccDiscoveryAdapter(self._source())

        sources = adapter._extract_relevant_links(  # noqa: SLF001 - adapter parser behavior is intentionally tested
            '<a href="/docketsearch/DOCS/example.PDF">Data center large load docket</a>'
        )

        self.assertEqual(len(sources), 1)
        self.assertIsInstance(sources[0], DiscoveredSource)
        self.assertEqual(sources[0].publisher, "Virginia State Corporation Commission")
        self.assertEqual(sources[0].confidence, "candidate_discovered")

    def test_parse_representative_scc_search_results_fixture(self) -> None:
        html = (FIXTURES_DIR / "scc_search_results.html").read_text()

        results = parse_scc_search_results(html, query="data center")

        self.assertEqual(len(results), 2)
        self.assertEqual(
            results[0].source_url,
            "https://www.scc.virginia.gov/docketsearch/DOCS/example-large-load.pdf",
        )
        self.assertEqual(results[0].source_title, "Data center large load electric service agreement")
        self.assertIn("public utility case", results[0].snippet)
        self.assertEqual(results[0].source_query, "data center")

    def test_extract_searchstax_config_from_scc_search_shell_fixture(self) -> None:
        html = (FIXTURES_DIR / "scc_searchstax_shell.html").read_text()

        config = extract_searchstax_config(html)

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(
            config.connector_url,
            "https://searchcloud-2-us-east-1.searchstax.com/29847/vcascc-1781/emselect",
        )
        self.assertEqual(config.select_auth_token, "public-select-token")
        self.assertEqual(config.search_auth_type, "token")
        self.assertEqual(config.search_additional_args, "hl.fragsize=200")
        self.assertIn("studio-app.js", " ".join(config.script_urls))
        self.assertEqual(config.tabs["casesTab"], "sectiontype_s-case")

    def test_parse_searchstax_response_fixture(self) -> None:
        payload = (FIXTURES_DIR / "scc_searchstax_response.json").read_text()

        results = parse_searchstax_response(payload, query="data center")

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].source_title, "SCC Data Center Initiatives Facts and Figures Feb2026")
        self.assertIn("Data Center Initiatives", results[0].snippet or "")
        self.assertEqual(results[0].document_type, "pdf")
        self.assertEqual(results[1].case_number, "PUR-2026-00022")

    def test_relative_url_normalization(self) -> None:
        self.assertEqual(
            normalize_url("/docketsearch/DOCS/example-large-load.pdf"),
            "https://www.scc.virginia.gov/docketsearch/DOCS/example-large-load.pdf",
        )

    def test_scc_search_result_parser_deduplicates_by_source_url(self) -> None:
        html = (FIXTURES_DIR / "scc_search_results.html").read_text()

        results = parse_scc_search_results(html, query="large load")

        urls = [normalize_url(result.source_url) for result in results]
        self.assertEqual(len(urls), len(set(urls)))
        self.assertIn("https://www.scc.virginia.gov/docketsearch/DOCS/example-large-load.pdf", urls)

    def test_no_parseable_results_warns_without_crashing(self) -> None:
        fetch_result = FetchResult(
            url="https://www.scc.virginia.gov/search/",
            ok=True,
            status_code=200,
            content_type="text/html",
            text='<html><body><a href="/pages/about-the-commission">About SCC</a></body></html>',
            content_hash="hash",
            fetched_at="2026-05-13T00:00:00+00:00",
        )

        result = VirginiaSccDiscoveryAdapter(self._source(), fetch_client=StubFetchClient(fetch_result)).run(
            dry_run=False
        )

        self.assertEqual(result.discovered_sources, [])
        self.assertTrue(any("scc_search_requires_client_side_execution" in warning for warning in result.warnings))

    def test_searchstax_no_results_warns_without_crashing(self) -> None:
        shell = (FIXTURES_DIR / "scc_searchstax_shell.html").read_text()
        empty_response = '{"response": {"numFound": 0, "docs": []}}'
        results = [
            FetchResult(
                url="https://www.scc.virginia.gov/search/",
                ok=True,
                status_code=200,
                content_type="text/html",
                text=shell,
                content_hash="shell",
                fetched_at="2026-05-13T00:00:00+00:00",
            )
        ]
        for index in range(4):
            results.append(
                FetchResult(
                    url=f"https://search.example.test/{index}",
                    ok=True,
                    status_code=200,
                    content_type="application/json",
                    text=empty_response,
                    content_hash=f"json-{index}",
                    fetched_at="2026-05-13T00:00:00+00:00",
                )
            )

        result = VirginiaSccDiscoveryAdapter(self._source(), fetch_client=SequenceFetchClient(results)).run(
            dry_run=False
        )

        self.assertEqual(result.discovered_sources, [])
        self.assertTrue(any("no_scc_searchstax_results" in warning for warning in result.warnings))

    def test_searchstax_query_results_become_discovered_sources(self) -> None:
        shell = (FIXTURES_DIR / "scc_searchstax_shell.html").read_text()
        payload = (FIXTURES_DIR / "scc_searchstax_response.json").read_text()
        empty_response = '{"response": {"numFound": 0, "docs": []}}'
        fetch_client = SequenceFetchClient(
            [
                FetchResult(
                    url="https://www.scc.virginia.gov/search/",
                    ok=True,
                    status_code=200,
                    content_type="text/html",
                    text=shell,
                    content_hash="shell",
                    fetched_at="2026-05-13T00:00:00+00:00",
                ),
                FetchResult(
                    url="https://search.example.test/0",
                    ok=True,
                    status_code=200,
                    content_type="application/json",
                    text=payload,
                    content_hash="json-0",
                    fetched_at="2026-05-13T00:00:00+00:00",
                ),
                FetchResult(
                    url="https://search.example.test/1",
                    ok=True,
                    status_code=200,
                    content_type="application/json",
                    text=empty_response,
                    content_hash="json-1",
                    fetched_at="2026-05-13T00:00:00+00:00",
                ),
                FetchResult(
                    url="https://search.example.test/2",
                    ok=True,
                    status_code=200,
                    content_type="application/json",
                    text=empty_response,
                    content_hash="json-2",
                    fetched_at="2026-05-13T00:00:00+00:00",
                ),
                FetchResult(
                    url="https://search.example.test/3",
                    ok=True,
                    status_code=200,
                    content_type="application/json",
                    text=empty_response,
                    content_hash="json-3",
                    fetched_at="2026-05-13T00:00:00+00:00",
                ),
            ]
        )

        result = VirginiaSccDiscoveryAdapter(self._source(), fetch_client=fetch_client).run(dry_run=False)

        self.assertEqual(len(result.discovered_sources), 2)
        self.assertEqual(result.discovered_sources[0].publisher, "Virginia State Corporation Commission")
        self.assertEqual(result.discovered_sources[0].geography, "Virginia")
        self.assertEqual(result.discovered_sources[0].discovery_method, "searchstax_query")
        self.assertEqual(result.discovered_sources[0].source_query, "data center")
        self.assertEqual(result.discovered_sources[1].case_number, "PUR-2026-00022")
        self.assertIn("Authorization", fetch_client.calls[1][1] or {})

    def test_run_public_discovery_dry_run_skips_unimplemented_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = run_sources(dry_run=True, output_dir=Path(tmpdir))

        self.assertEqual(payload["sources_checked"], 11)
        self.assertEqual(payload["sources_discovered"], 0)
        self.assertFalse(payload["allow_insecure_fetch"])
        self.assertFalse(payload["write_fetch_cache"])
        self.assertTrue(any("no adapter implemented" in warning for warning in payload["warnings"]))
        self.assertEqual(payload["implemented_adapters"], ["virginia_scc_data_center_large_load_dockets"])

    def test_run_public_discovery_can_mark_insecure_fetch_dev_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = run_sources(dry_run=True, output_dir=Path(tmpdir), allow_insecure_fetch=True)

        self.assertTrue(payload["allow_insecure_fetch"])
        self.assertTrue(any("INSECURE FETCH ENABLED" in warning for warning in payload["warnings"]))

    def test_fetch_cache_is_only_written_when_requested(self) -> None:
        fetch_result = FetchResult(
            url="https://www.scc.virginia.gov/search/",
            ok=False,
            status_code=None,
            content_type=None,
            text=None,
            content_hash=None,
            fetched_at="2026-05-13T00:00:00+00:00",
            error_type="ssl_certificate_error",
            error_message="certificate verify failed",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = VirginiaSccDiscoveryAdapter(
                self._source(),
                fetch_client=StubFetchClient(fetch_result),
                fetch_cache_dir=Path(tmpdir),
            )
            result = adapter.run(dry_run=False)
            self.assertEqual(len(result.fetch_cache_paths), 1)
            for cache_path in result.fetch_cache_paths:
                self.assertTrue(Path(cache_path, "metadata.json").exists())

    def test_virginia_scc_fetch_failure_becomes_structured_warning(self) -> None:
        fetch_result = FetchResult(
            url="https://www.scc.virginia.gov/search/",
            ok=False,
            status_code=None,
            content_type=None,
            text=None,
            content_hash=None,
            fetched_at="2026-05-13T00:00:00+00:00",
            error_type="ssl_certificate_error",
            error_message="certificate verify failed",
        )
        result = VirginiaSccDiscoveryAdapter(self._source(), fetch_client=StubFetchClient(fetch_result)).run(dry_run=False)

        self.assertEqual(result.discovered_sources, [])
        self.assertEqual(result.fetch_results[0].error_type, "ssl_certificate_error")
        self.assertTrue(any("ssl_certificate_error" in warning for warning in result.warnings))

    def test_run_public_discovery_dry_run_cli_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/run_public_discovery.py", "--dry-run"],
            cwd=BACKEND_DIR,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"dry_run": true', result.stdout)

if __name__ == "__main__":
    unittest.main()
