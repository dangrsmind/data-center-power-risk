from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.discovery_adapters.generic_web_search import (  # noqa: E402
    DEFAULT_RESULT_LIMIT,
    result_limit_from_env,
)


DOWNSTREAM_FLAGS = (
    "ingest",
    "extract_claims",
    "generate_candidates",
    "verify_candidates",
    "auto_admit_dry_run",
)


@dataclass
class StepResult:
    returncode: int
    payload: dict[str, Any] | None
    stdout: str
    stderr: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a controlled live/mock public discovery smoke workflow.")
    parser.add_argument("--ingest", action="store_true", help="Ingest discovered sources into discovered_sources.")
    parser.add_argument("--extract-claims", action="store_true", help="Extract claims from ingested discovered sources.")
    parser.add_argument("--generate-candidates", action="store_true", help="Generate reviewable project candidates.")
    parser.add_argument("--verify-candidates", action="store_true", help="Dry-run project candidate verification.")
    parser.add_argument("--auto-admit-dry-run", action="store_true", help="Evaluate auto-admit without promotion.")
    parser.add_argument("--healthcheck", action="store_true", help="Run discovery database healthcheck.")
    parser.add_argument("--allow-disabled", action="store_true", help="Allow WEB_SEARCH_PROVIDER=disabled.")
    parser.add_argument("--dry-run", action="store_true", help="Avoid writes where downstream scripts support dry-run.")
    parser.add_argument(
        "--discovery-output",
        type=Path,
        default=None,
        help="Skip discovery and continue from an existing discovered_sources.json file.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="Set WEB_SEARCH_MAX_RESULTS for this process and child steps.",
    )
    return parser.parse_args(argv)


def run_step(command: list[str], *, env: dict[str, str]) -> StepResult:
    result = subprocess.run(
        command,
        cwd=BACKEND_DIR,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    stdout = redact_secret(result.stdout, env.get("WEB_SEARCH_API_KEY"))
    stderr = redact_secret(result.stderr, env.get("WEB_SEARCH_API_KEY"))
    payload = parse_json_stdout(stdout)
    return StepResult(returncode=result.returncode, payload=payload, stdout=stdout, stderr=stderr)


def parse_json_stdout(stdout: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def redact_secret(value: str, secret: str | None) -> str:
    if not secret:
        return value
    return value.replace(secret, "[REDACTED]")


def redact_payload(value: Any, secret: str | None) -> Any:
    if not secret:
        return value
    if isinstance(value, str):
        return redact_secret(value, secret)
    if isinstance(value, list):
        return [redact_payload(item, secret) for item in value]
    if isinstance(value, dict):
        return {key: redact_payload(item, secret) for key, item in value.items()}
    return value


def downstream_requested(args: argparse.Namespace) -> bool:
    return any(bool(getattr(args, flag)) for flag in DOWNSTREAM_FLAGS)


def discovery_output_count(path: Path) -> int | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict) and isinstance(payload.get("discovered_sources"), list):
        return len(payload["discovered_sources"])
    if isinstance(payload, dict) and isinstance(payload.get("adapter_results"), list):
        count = 0
        for result in payload["adapter_results"]:
            if isinstance(result, dict) and isinstance(result.get("discovered_sources"), list):
                count += len(result["discovered_sources"])
        return count
    return None


def empty_summary(*, provider: str, max_results: int, api_key_present: bool) -> dict[str, Any]:
    return {
        "provider": provider,
        "max_results": max_results,
        "api_key_present": api_key_present,
        "discovery": {
            "sources_discovered": 0,
            "output_path": None,
            "errors": [],
            "warnings": [],
        },
        "ingest": None,
        "claim_extraction": None,
        "candidate_generation": None,
        "verification": None,
        "auto_admit_dry_run": None,
        "healthcheck": None,
        "promoted": 0,
        "errors": [],
        "warnings": [],
    }


def normalize_step_payload(step: StepResult) -> dict[str, Any]:
    if step.payload is not None:
        payload = dict(step.payload)
    else:
        payload = {
            "errors": ["step_output_not_json"],
            "stdout": step.stdout,
        }
    if step.stderr:
        payload.setdefault("stderr", step.stderr)
    if step.returncode != 0:
        payload.setdefault("errors", [])
        if isinstance(payload["errors"], list):
            payload["errors"].append(f"step_failed_returncode_{step.returncode}")
    return payload


def append_step_errors(summary: dict[str, Any], step_name: str, payload: dict[str, Any]) -> None:
    for key in ("errors", "validation_errors"):
        values = payload.get(key)
        if isinstance(values, list):
            summary["errors"].extend(f"{step_name}:{value}" for value in values)
    warnings = payload.get("warnings")
    if isinstance(warnings, list):
        summary["warnings"].extend(f"{step_name}:{value}" for value in warnings)


def run_smoke(
    args: argparse.Namespace,
    *,
    step_runner: Callable[[list[str]], StepResult] | None = None,
) -> tuple[dict[str, Any], int]:
    env = dict(os.environ)
    provider_raw = env.get("WEB_SEARCH_PROVIDER")
    provider = (provider_raw or "disabled").strip().lower() or "disabled"
    if args.max_results is not None:
        if args.max_results < 1:
            summary = empty_summary(
                provider=provider,
                max_results=result_limit_from_env(),
                api_key_present=bool(env.get("WEB_SEARCH_API_KEY")),
            )
            summary["errors"].append("invalid_max_results")
            return summary, 1
        env["WEB_SEARCH_MAX_RESULTS"] = str(args.max_results)

    max_results = result_limit_from_env(default=DEFAULT_RESULT_LIMIT) if args.max_results is None else min(
        max(args.max_results, 1), DEFAULT_RESULT_LIMIT
    )
    api_key_present = bool(env.get("WEB_SEARCH_API_KEY"))
    summary = empty_summary(provider=provider, max_results=max_results, api_key_present=api_key_present)

    if (provider_raw is None or provider == "disabled") and not args.allow_disabled:
        summary["errors"].append("web_search_provider_disabled")
        summary["warnings"].append(
            "Set WEB_SEARCH_PROVIDER=mock or WEB_SEARCH_PROVIDER=brave; "
            "pass --allow-disabled to smoke disabled mode."
        )
        return summary, 1
    if provider == "brave" and not api_key_present:
        summary["errors"].append("web_search_api_key_missing")
        summary["warnings"].append("WEB_SEARCH_API_KEY is required for WEB_SEARCH_PROVIDER=brave.")
        return summary, 1

    runner = step_runner or (lambda command: run_step(command, env=env))

    output_path: str | None = None
    if args.discovery_output:
        output_path = str(args.discovery_output)
        count = discovery_output_count(args.discovery_output)
        summary["discovery"] = {
            "sources_discovered": count if count is not None else 0,
            "output_path": output_path,
            "errors": [] if args.discovery_output.exists() else ["discovery_output_not_found"],
            "warnings": ["discovery_skipped_existing_output"],
        }
        if not args.discovery_output.exists():
            summary["errors"].append("discovery:discovery_output_not_found")
            return summary, 1
    else:
        command = [sys.executable, "scripts/run_public_discovery.py"]
        if args.dry_run:
            command.append("--dry-run")
        step = runner(command)
        payload = redact_payload(normalize_step_payload(step), env.get("WEB_SEARCH_API_KEY"))
        summary["discovery"] = {
            "sources_discovered": payload.get("sources_discovered", 0),
            "output_path": payload.get("output_path"),
            "errors": payload.get("errors", []),
            "warnings": payload.get("warnings", []),
        }
        output_path = payload.get("output_path") if isinstance(payload.get("output_path"), str) else None
        append_step_errors(summary, "discovery", payload)
        if step.returncode != 0:
            return summary, 1

    if downstream_requested(args) and not output_path:
        summary["errors"].append("no_discovery_output_to_ingest")
        summary["warnings"].append("no_discovery_output_to_ingest")
        return summary, 1

    steps: list[tuple[str, bool, list[str]]] = [
        ("ingest", args.ingest, ["scripts/ingest_public_discovered_sources.py", "--input", output_path or ""]),
        ("claim_extraction", args.extract_claims, ["scripts/extract_discovered_source_claims.py"]),
        ("candidate_generation", args.generate_candidates, ["scripts/generate_project_candidates.py"]),
        ("verification", args.verify_candidates, ["scripts/verify_project_candidates.py"]),
        ("auto_admit_dry_run", args.auto_admit_dry_run, ["scripts/auto_admit_project_candidates.py"]),
        ("healthcheck", args.healthcheck, ["scripts/discovery_healthcheck.py"]),
    ]

    exit_code = 0
    for step_name, enabled, script_args in steps:
        if not enabled:
            continue
        command = [sys.executable, *script_args]
        if args.dry_run and step_name in {"ingest", "claim_extraction", "candidate_generation"}:
            command.append("--dry-run")
        step = runner(command)
        payload = redact_payload(normalize_step_payload(step), env.get("WEB_SEARCH_API_KEY"))
        summary[step_name] = payload
        append_step_errors(summary, step_name, payload)
        if step_name == "auto_admit_dry_run":
            promoted = payload.get("promoted")
            if promoted:
                summary["errors"].append("auto_admit_dry_run_reported_promotions")
            summary["promoted"] = 0
        if step.returncode != 0:
            exit_code = 1

    return summary, exit_code


def main(argv: list[str] | None = None) -> None:
    summary, exit_code = run_smoke(parse_args(argv))
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
