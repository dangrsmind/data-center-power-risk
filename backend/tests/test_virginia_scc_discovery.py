from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

from app.schemas.discovery import DiscoveredSource  # noqa: E402
from app.services.discovery_adapters.virginia_scc import VirginiaSccDiscoveryAdapter  # noqa: E402
from app.services.source_registry import load_source_registry  # noqa: E402
from run_public_discovery import run_sources  # noqa: E402


class VirginiaSccDiscoveryTest(unittest.TestCase):
    def _source(self):
        registry = load_source_registry()
        return next(source for source in registry.sources if source.id == "virginia_scc_data_center_large_load_dockets")

    def test_virginia_scc_dry_run_returns_planned_queries(self) -> None:
        result = VirginiaSccDiscoveryAdapter(self._source()).run(dry_run=True)

        self.assertEqual(len(result.planned_queries), 4)
        terms = {query["term"] for query in result.planned_queries}
        self.assertIn("data center", terms)
        self.assertIn("large load", terms)
        self.assertEqual(result.discovered_sources, [])

    def test_discovered_source_records_validate(self) -> None:
        adapter = VirginiaSccDiscoveryAdapter(self._source())

        sources = adapter._extract_relevant_links(  # noqa: SLF001 - adapter parser behavior is intentionally tested
            '<a href="/docketsearch/DOCS/example.PDF">Data center large load docket</a>'
        )

        self.assertEqual(len(sources), 1)
        self.assertIsInstance(sources[0], DiscoveredSource)
        self.assertEqual(sources[0].publisher, "Virginia State Corporation Commission")
        self.assertEqual(sources[0].confidence, "candidate_discovered")

    def test_run_public_discovery_dry_run_skips_unimplemented_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = run_sources(dry_run=True, output_dir=Path(tmpdir))

        self.assertEqual(payload["sources_checked"], 11)
        self.assertEqual(payload["sources_discovered"], 0)
        self.assertTrue(any("no adapter implemented" in warning for warning in payload["warnings"]))
        self.assertEqual(payload["implemented_adapters"], ["virginia_scc_data_center_large_load_dockets"])

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
