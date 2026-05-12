from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.source_registry import SourceRegistryValidationError, load_source_registry  # noqa: E402


VALID_REGISTRY = """
version: test_registry
sources:
  - id: test_regulatory_source
    name: Test regulatory source
    source_type: state_regulatory_dockets
    geography: Test State
    base_url: https://example.test/
    discovery_method: docket_search
    enabled: true
    priority: high
    search_terms:
      - data center
    notes: Test source notes.
  - id: test_context_source
    name: Test context source
    source_type: grid_context
    geography: United States
    base_url: https://context.example.test/
    discovery_method: public_dataset
    enabled: false
    priority: low
    search_terms:
      - utility context
    notes: Context-only source notes.
"""


class SourceRegistryTest(unittest.TestCase):
    def _write_registry(self, payload: str) -> Path:
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".yaml", delete=False)
        with handle:
            handle.write(payload)
        self.addCleanup(lambda: os.path.exists(handle.name) and os.remove(handle.name))
        return Path(handle.name)

    def test_loads_enabled_sources_and_groups_by_type(self) -> None:
        registry = load_source_registry(self._write_registry(VALID_REGISTRY))

        self.assertEqual(len(registry.sources), 2)
        self.assertEqual([source.id for source in registry.enabled_sources], ["test_regulatory_source"])
        grouped = registry.group_by_source_type()
        self.assertEqual(len(grouped["state_regulatory_dockets"]), 1)
        self.assertEqual(len(grouped["grid_context"]), 1)

    def test_invalid_registry_raises_clear_errors(self) -> None:
        invalid = VALID_REGISTRY.replace("base_url: https://example.test/", "base_url: not-a-url")

        with self.assertRaises(SourceRegistryValidationError) as ctx:
            load_source_registry(self._write_registry(invalid))

        self.assertTrue(any("base_url" in error for error in ctx.exception.errors))


if __name__ == "__main__":
    unittest.main()
