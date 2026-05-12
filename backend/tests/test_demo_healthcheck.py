from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from demo_healthcheck import validate_coordinate_fields, validate_prediction_payload  # noqa: E402


class DemoHealthcheckValidationTest(unittest.TestCase):
    def _project(self, **kwargs):
        defaults = {
            "id": uuid.uuid4(),
            "canonical_name": "Healthcheck Campus",
            "latitude": 38.03,
            "longitude": -77.35,
            "coordinate_confidence": 0.7,
            "coordinate_source": "manual_review",
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_coordinate_validation_accepts_valid_coordinate_pair(self) -> None:
        self.assertEqual(validate_coordinate_fields(self._project()), [])

    def test_coordinate_validation_rejects_bad_ranges_and_legacy_source(self) -> None:
        errors = validate_coordinate_fields(
            self._project(
                latitude=91,
                longitude=None,
                coordinate_confidence=1.5,
                coordinate_source="starter_dataset",
            )
        )

        self.assertTrue(any("both be present" in error for error in errors))
        self.assertTrue(any("latitude" in error for error in errors))
        self.assertTrue(any("coordinate_confidence" in error for error in errors))
        self.assertTrue(any("legacy coordinate_source" in error for error in errors))

    def test_prediction_validation_requires_monotonic_probabilities_and_drivers(self) -> None:
        errors = validate_prediction_payload(
            {
                "model_name": "baseline_power_delay",
                "p_delay_6mo": 0.4,
                "p_delay_12mo": 0.3,
                "p_delay_18mo": 1.2,
                "risk_tier": "high",
                "confidence": "medium",
                "drivers": [],
            },
            label="Healthcheck Campus",
        )

        self.assertTrue(any("outside [0, 1]" in error for error in errors))
        self.assertTrue(any("not monotonic" in error for error in errors))
        self.assertTrue(any("drivers" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
