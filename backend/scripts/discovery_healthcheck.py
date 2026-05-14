from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal, create_db_and_tables  # noqa: E402
from app.models.discovered_source import DiscoveredSourceClaim, DiscoveredSourceRecord  # noqa: E402
from app.services.discovered_source_claim_extractor import VALID_DISCOVERED_SOURCE_CLAIM_STATUSES  # noqa: E402
from app.services.discovered_source_service import VALID_DISCOVERED_SOURCE_STATUSES  # noqa: E402


def valid_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def run_healthcheck() -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    checked = 0
    claims_checked = 0
    try:
        create_db_and_tables()
        with SessionLocal() as db:
            checked = db.scalar(select(func.count()).select_from(DiscoveredSourceRecord)) or 0
            claims_checked = db.scalar(select(func.count()).select_from(DiscoveredSourceClaim)) or 0
            duplicate_count = db.scalar(
                select(func.count()).select_from(
                    select(DiscoveredSourceRecord.source_url)
                    .group_by(DiscoveredSourceRecord.source_url)
                    .having(func.count() > 1)
                    .subquery()
                )
            )
            if duplicate_count:
                errors.append(f"duplicate source_url values found: {duplicate_count}")
            for source_url, status in db.execute(select(DiscoveredSourceRecord.source_url, DiscoveredSourceRecord.status)):
                if not valid_url(source_url):
                    errors.append(f"invalid source_url: {source_url!r}")
                if status not in VALID_DISCOVERED_SOURCE_STATUSES:
                    errors.append(f"invalid status for {source_url}: {status}")
            source_ids = set(db.scalars(select(DiscoveredSourceRecord.id)))
            for claim_id, source_id, confidence, status in db.execute(
                select(
                    DiscoveredSourceClaim.id,
                    DiscoveredSourceClaim.discovered_source_id,
                    DiscoveredSourceClaim.confidence,
                    DiscoveredSourceClaim.status,
                )
            ):
                if source_id not in source_ids:
                    errors.append(f"claim {claim_id} references missing discovered_source_id: {source_id}")
                if not 0 <= confidence <= 1:
                    errors.append(f"claim {claim_id} has invalid confidence: {confidence}")
                if status not in VALID_DISCOVERED_SOURCE_CLAIM_STATUSES:
                    errors.append(f"claim {claim_id} has invalid status: {status}")
    except SQLAlchemyError as exc:
        errors.append(f"database healthcheck failed: {exc}")
    if checked == 0:
        warnings.append("no discovered sources ingested yet")
    return {
        "discovered_sources_checked": checked,
        "discovered_source_claims_checked": claims_checked,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> None:
    payload = run_healthcheck()
    print(json.dumps(payload, indent=2, sort_keys=True))
    raise SystemExit(1 if payload["errors"] else 0)


if __name__ == "__main__":
    main()
