from __future__ import annotations

import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.source_registry import (  # noqa: E402
    DEFAULT_REGISTRY_PATH,
    SourceRegistryValidationError,
    load_source_registry,
    registry_summary,
)


def invalid_summary(errors: list[str]) -> dict:
    return {
        "total_sources": 0,
        "enabled_sources": 0,
        "source_types": [],
        "high_priority_sources": [],
        "validation_errors": errors,
    }


def main() -> None:
    try:
        registry = load_source_registry(DEFAULT_REGISTRY_PATH)
    except SourceRegistryValidationError as exc:
        print(json.dumps(invalid_summary(exc.errors), indent=2, sort_keys=True))
        raise SystemExit(1) from exc

    print(json.dumps(registry_summary(registry), indent=2, sort_keys=True))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
