from __future__ import annotations

import uuid

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.enums import StressEntityType
from app.models.quarterly import StressObservation, StressScore


class StressRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_latest_project_score(self, project_id: uuid.UUID) -> StressScore | None:
        stmt = (
            select(StressScore)
            .where(
                StressScore.entity_type == StressEntityType.PROJECT,
                StressScore.entity_id == project_id,
            )
            .order_by(desc(StressScore.quarter), desc(StressScore.created_at))
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_project_scores(self, project_id: uuid.UUID) -> list[StressScore]:
        stmt = (
            select(StressScore)
            .where(
                StressScore.entity_type == StressEntityType.PROJECT,
                StressScore.entity_id == project_id,
            )
            .order_by(desc(StressScore.quarter), desc(StressScore.created_at))
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_project_observations(self, project_id: uuid.UUID) -> list[StressObservation]:
        stmt = (
            select(StressObservation)
            .where(
                StressObservation.entity_type == StressEntityType.PROJECT,
                StressObservation.entity_id == project_id,
            )
            .order_by(desc(StressObservation.quarter), desc(StressObservation.created_at))
        )
        return list(self.db.execute(stmt).scalars().all())
