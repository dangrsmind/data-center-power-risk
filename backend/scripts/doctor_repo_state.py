from __future__ import annotations

import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
RUNTIME_DIR = Path("backend/runtime_data")
LOCAL_DB = Path("backend/local.db")
OLD_MUTABLE_FILES = [
    Path("data/starter_sources/discovered_sources_v0_1.csv"),
    Path("data/starter_sources/discovery_decisions_v0_1.json"),
    Path("data/starter_sources/manual_source_captures_v0_1.json"),
]


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


def ok(message: str) -> None:
    print(f"OK: {message}")


def warn(message: str) -> None:
    print(f"WARN: {message}")


def error(message: str) -> None:
    print(f"ERROR: {message}")


def check_git_cleanliness() -> bool:
    result = run_git("status", "--short")
    if result.returncode != 0:
        error(f"git status failed: {result.stderr.strip() or result.stdout.strip()}")
        return False
    if result.stdout.strip():
        warn("working tree has uncommitted changes")
        print(result.stdout.rstrip())
    else:
        ok("working tree is clean")
    return True


def check_local_db_not_tracked() -> bool:
    result = run_git("ls-files", "--error-unmatch", str(LOCAL_DB))
    if result.returncode == 0:
        error(f"{LOCAL_DB} is tracked; remove it from Git with `git rm --cached {LOCAL_DB}`")
        return False
    ok(f"{LOCAL_DB} is not tracked")
    return True


def check_runtime_data_ignored() -> bool:
    result = run_git("check-ignore", "-q", str(RUNTIME_DIR))
    if result.returncode == 0:
        ok(f"{RUNTIME_DIR}/ is ignored")
        return True
    error(f"{RUNTIME_DIR}/ is not ignored")
    return False


def check_old_mutable_files_absent() -> bool:
    found = [path for path in OLD_MUTABLE_FILES if (REPO_DIR / path).exists()]
    if not found:
        ok("no mutable runtime files found under data/starter_sources/")
        return True
    for path in found:
        warn(f"mutable runtime file still exists under tracked data path: {path}")
    return True


def main() -> int:
    checks = [
        check_git_cleanliness(),
        check_local_db_not_tracked(),
        check_runtime_data_ignored(),
        check_old_mutable_files_absent(),
    ]
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
