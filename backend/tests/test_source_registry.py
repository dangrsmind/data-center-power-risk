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

    def test_default_registry_includes_controlled_targeted_official_searches(self) -> None:
        registry = load_source_registry()
        targeted_ids = {
            "loudoun_county_data_center_planning_search",
            "prince_william_county_data_center_planning_search",
            "fairfax_county_data_center_planning_search",
            "texas_puct_large_load_data_center_search",
            "ercot_large_load_data_center_search",
            "georgia_psc_data_center_utility_search",
            "georgia_economic_development_data_center_search",
            "ohio_power_siting_data_center_search",
            "indiana_economic_development_data_center_search",
            "north_carolina_commerce_data_center_search",
            "south_carolina_commerce_data_center_search",
            "arizona_corporation_commission_data_center_search",
            "nevada_puc_data_center_search",
            "pacific_northwest_utility_data_center_search",
        }
        sources_by_id = {source.id: source for source in registry.sources}

        self.assertEqual(len(registry.sources), 25)
        self.assertEqual(len(targeted_ids), 14)
        self.assertTrue(targeted_ids.issubset(sources_by_id))
        for source_id in targeted_ids:
            source = sources_by_id[source_id]
            self.assertEqual(source.discovery_method, "web_search_pattern")
            self.assertLessEqual(len(source.search_terms), 2)


if __name__ == "__main__":
    unittest.main()
