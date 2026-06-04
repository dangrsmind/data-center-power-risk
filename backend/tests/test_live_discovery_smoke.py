from __future__ import annotations

import json
import os
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

import run_live_discovery_smoke  # noqa: E402
from run_live_discovery_smoke import StepResult  # noqa: E402


class LiveDiscoverySmokeTest(unittest.TestCase):
    def _args(self, *argv: str):
        return run_live_discovery_smoke.parse_args(list(argv))

    def test_disabled_provider_refuses_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            summary, exit_code = run_live_discovery_smoke.run_smoke(self._args())

        self.assertEqual(exit_code, 1)
        self.assertEqual(summary["provider"], "disabled")
        self.assertIn("web_search_provider_disabled", summary["errors"])

    def test_brave_without_api_key_exits_cleanly_without_traceback(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/run_live_discovery_smoke.py"],
            cwd=BACKEND_DIR,
            env={"WEB_SEARCH_PROVIDER": "brave"},
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("Traceback", result.stdout)
        payload = json.loads(result.stdout)
        self.assertIn("web_search_api_key_missing", payload["errors"])
        self.assertFalse(payload["api_key_present"])

    def test_mock_provider_smoke_path_runs_without_api_key(self) -> None:
        env = dict(os.environ)
        env.update(
            {
                "WEB_SEARCH_PROVIDER": "mock",
                "WEB_SEARCH_MOCK_RESULTS_PATH": str(FIXTURES_DIR / "generic_web_search_results.json"),
                "WEB_SEARCH_API_KEY": "",
            }
        )
        result = subprocess.run(
            [sys.executable, "scripts/run_live_discovery_smoke.py", "--max-results", "3"],
            cwd=BACKEND_DIR,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["provider"], "mock")
        self.assertEqual(payload["max_results"], 3)
        self.assertFalse(payload["api_key_present"])
        self.assertGreaterEqual(payload["discovery"]["sources_discovered"], 1)

    def test_api_key_is_not_printed_when_present(self) -> None:
        secret = "test-secret-that-must-not-appear"

        def fake_runner(command: list[str]) -> StepResult:
            return StepResult(
                returncode=0,
                payload={
                    "sources_discovered": 0,
                    "output_path": None,
                    "errors": [],
                    "warnings": [secret],
                },
                stdout=json.dumps({"warnings": [secret]}),
                stderr=secret,
            )

        with patch.dict(os.environ, {"WEB_SEARCH_PROVIDER": "brave", "WEB_SEARCH_API_KEY": secret}, clear=True):
            summary, _ = run_live_discovery_smoke.run_smoke(self._args(), step_runner=fake_runner)

        rendered = json.dumps(summary)
        self.assertNotIn(secret, rendered)

    def test_no_output_path_with_downstream_ingest_reports_clear_error(self) -> None:
        def fake_runner(command: list[str]) -> StepResult:
            return StepResult(
                returncode=0,
                payload={"sources_discovered": 0, "output_path": None, "errors": [], "warnings": []},
                stdout="{}",
                stderr="",
            )

        with patch.dict(os.environ, {"WEB_SEARCH_PROVIDER": "mock"}, clear=True):
            summary, exit_code = run_live_discovery_smoke.run_smoke(self._args("--ingest"), step_runner=fake_runner)

        self.assertEqual(exit_code, 1)
        self.assertIn("no_discovery_output_to_ingest", summary["errors"])
        self.assertIsNone(summary["ingest"])

    def test_downstream_json_aggregation_and_auto_admit_does_not_promote(self) -> None:
        calls: list[list[str]] = []

        def fake_runner(command: list[str]) -> StepResult:
            calls.append(command)
            script = command[1]
            if script.endswith("run_public_discovery.py"):
                return StepResult(
                    returncode=0,
                    payload={
                        "sources_discovered": 2,
                        "output_path": "/tmp/discovered_sources.json",
                        "errors": [],
                        "warnings": [],
                    },
                    stdout="{}",
                    stderr="",
                )
            if script.endswith("ingest_public_discovered_sources.py"):
                return StepResult(0, {"sources_created": 2, "errors": [], "warnings": []}, "{}", "")
            if script.endswith("extract_discovered_source_claims.py"):
                return StepResult(0, {"claims_created": 3, "errors": [], "warnings": []}, "{}", "")
            if script.endswith("generate_project_candidates.py"):
                return StepResult(0, {"candidates_created": 1, "errors": [], "warnings": []}, "{}", "")
            if script.endswith("verify_project_candidates.py"):
                return StepResult(0, {"candidates_checked": 1, "auto_admit_eligible": 0, "warnings": []}, "{}", "")
            if script.endswith("auto_admit_project_candidates.py"):
                return StepResult(0, {"candidates_checked": 1, "eligible": 0, "promoted": 0, "errors": []}, "{}", "")
            if script.endswith("discovery_healthcheck.py"):
                return StepResult(0, {"errors": [], "warnings": [], "project_candidates_checked": 1}, "{}", "")
            raise AssertionError(command)

        with patch.dict(os.environ, {"WEB_SEARCH_PROVIDER": "mock"}, clear=True):
            summary, exit_code = run_live_discovery_smoke.run_smoke(
                self._args(
                    "--ingest",
                    "--extract-claims",
                    "--generate-candidates",
                    "--verify-candidates",
                    "--auto-admit-dry-run",
                    "--healthcheck",
                ),
                step_runner=fake_runner,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["ingest"]["sources_created"], 2)
        self.assertEqual(summary["claim_extraction"]["claims_created"], 3)
        self.assertEqual(summary["candidate_generation"]["candidates_created"], 1)
        self.assertEqual(summary["verification"]["candidates_checked"], 1)
        self.assertEqual(summary["auto_admit_dry_run"]["promoted"], 0)
        self.assertEqual(summary["promoted"], 0)
        auto_admit_call = next(call for call in calls if call[1].endswith("auto_admit_project_candidates.py"))
        self.assertNotIn("--confirm", auto_admit_call)

    def test_discovery_output_skips_discovery_and_counts_fixture_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_path = Path(tmpdir) / "discovered_sources.json"
            fixture_path.write_text((FIXTURES_DIR / "public_discovered_sources.json").read_text(), encoding="utf-8")

            with patch.dict(os.environ, {"WEB_SEARCH_PROVIDER": "mock"}, clear=True):
                summary, exit_code = run_live_discovery_smoke.run_smoke(
                    self._args("--discovery-output", str(fixture_path))
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["discovery"]["sources_discovered"], 2)
        self.assertEqual(summary["discovery"]["output_path"], str(fixture_path))


if __name__ == "__main__":
    unittest.main()
