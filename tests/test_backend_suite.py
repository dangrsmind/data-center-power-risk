from __future__ import annotations

import unittest
from pathlib import Path


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    repo_root = Path(__file__).resolve().parents[1]
    backend_tests = repo_root / "backend" / "tests"
    return loader.discover(str(backend_tests), pattern or "test*.py", top_level_dir=str(repo_root))
