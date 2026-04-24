from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project


class CandidateRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_canonical_name(self, canonical_name: str) -> Project | None:
        stmt = select(Project).where(Project.canonical_name == canonical_name)
        return self.db.execute(stmt).scalar_one_or_none()

    def create_project(self, project: Project) -> Project:
        self.db.add(project)
        self.db.flush()
        self.db.refresh(project)
        return project
