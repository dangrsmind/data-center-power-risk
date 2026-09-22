"""Read-only audit inventory. Filtering and pagination happen in SQL."""
from datetime import datetime, timedelta, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.imported_dataset import ImportedDatasetRow as Row
from app.models.project_candidate import ProjectCandidate

router = APIRouter(prefix="/imported-context", tags=["imported-context"])


def basename(value):
    return value.replace("\\", "/").rsplit("/", 1)[-1]


def present(column):
    # JSON null and SQL NULL both mean absent; these columns contain arrays.
    return func.coalesce(cast(column, String), "null").notin_(["null", "[]"])


def payload(row, detail=False):
    normalized = row.normalized_row_json if isinstance(row.normalized_row_json, dict) else {}
    raw = row.raw_row_json if isinstance(row.raw_row_json, dict) else {}
    result = {column.name: getattr(row, column.name) for column in Row.__table__.columns
              if detail or column.name not in ("raw_row_json", "normalized_row_json")}
    result.update(source_file_basename=basename(row.source_file),
                  display_name=next((str(value) for value in [normalized.get("name"), normalized.get("candidate_name"),
                      raw.get("Name"), raw.get("name"), raw.get("Data center")] if value), "Unnamed context row"),
                  record_type=normalized.get("dataset_row_type") or normalized.get("inferred_record_type") or normalized.get("entity_type") or "context")
    return result


@router.get("")
def list_rows(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
              dataset_name: str | None = None, source_file: str | None = None,
              duplicate_status: str | None = None, has_candidate: bool | None = None,
              has_warnings: bool | None = None, has_errors: bool | None = None,
              q: str | None = Query(None, max_length=500), db: Session = Depends(get_db)):
    conditions = []
    for column, value in [(Row.dataset_name, dataset_name), (Row.duplicate_status, duplicate_status)]:
        if value is not None:
            conditions.append(column == value)
    if source_file:
        conditions.append(Row.source_file.icontains(source_file, autoescape=True))
    if q:
        conditions.append(or_(*(cast(column, String).icontains(q, autoescape=True) for column in
                               [Row.raw_row_json, Row.normalized_row_json, Row.source_urls_json])))
    for expression, value in [(Row.linked_project_candidate_id.is_not(None), has_candidate),
                              (present(Row.warnings_json), has_warnings), (present(Row.errors_json), has_errors)]:
        if value is not None:
            conditions.append(expression if value else ~expression)
    total = db.scalar(select(func.count()).select_from(Row).where(*conditions))
    rows = db.scalars(select(Row).where(*conditions).order_by(Row.created_at.desc(), Row.id.desc()).limit(limit).offset(offset))
    return {"items": [payload(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    def count(*conditions):
        return db.scalar(select(func.count()).select_from(Row).where(*conditions))
    def grouped(column):
        return dict(db.execute(select(column, func.count()).group_by(column)).all())
    files = {}
    for path, n in grouped(Row.source_file).items():
        name = basename(path)
        files[name] = files.get(name, 0) + n
    recent = datetime.now(timezone.utc) - timedelta(days=7)
    return {"total": count(), "counts_by_dataset_name": grouped(Row.dataset_name),
            "counts_by_source_file": files, "counts_by_duplicate_status": grouped(Row.duplicate_status),
            "rows_with_warnings": count(present(Row.warnings_json)), "rows_with_errors": count(present(Row.errors_json)),
            "linked_candidate_count": count(Row.linked_project_candidate_id.is_not(None)),
            "recent_row_count": count(Row.created_at >= recent), "recent_window_days": 7,
            "recent_rows": [payload(row) for row in db.scalars(select(Row).order_by(Row.created_at.desc(), Row.id.desc()).limit(5))],
            "top_source_files": [{"source_file": name, "count": n} for name, n in sorted(files.items(), key=lambda pair: (-pair[1], pair[0]))[:10]]}


@router.get("/{row_id}")
def detail(row_id: uuid.UUID, db: Session = Depends(get_db)):
    row = db.get(Row, row_id)
    if row is None:
        raise HTTPException(404, "Imported context row not found")
    result = payload(row, detail=True)
    candidate = db.get(ProjectCandidate, row.linked_project_candidate_id) if row.linked_project_candidate_id else None
    result["linked_candidate"] = {"id": candidate.id, "candidate_name": candidate.candidate_name, "status": candidate.status} if candidate else None
    return result
