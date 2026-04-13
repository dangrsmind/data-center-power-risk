from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.db import get_db_session


def get_db() -> Session:
    yield from get_db_session()
