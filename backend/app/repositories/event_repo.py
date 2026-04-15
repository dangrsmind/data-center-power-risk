from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.enums import EventScope
from app.models.event import Event
from app.models.project import Phase, Project
from app.models.reference import Region, Utility


@dataclass
class ProjectEventRow:
    event: Event
    phase_name: str | None
    region_name: str | None
    utility_name: str | None


class EventRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_project(self, project_id: uuid.UUID) -> list[ProjectEventRow]:
        project_region_id = select(Project.region_id).where(Project.id == project_id).scalar_subquery()
        project_utility_id = select(Project.utility_id).where(Project.id == project_id).scalar_subquery()
        stmt = (
            select(Event, Phase.phase_name, Region.name, Utility.name)
            .outerjoin(Phase, Event.phase_id == Phase.id)
            .outerjoin(Region, Event.region_id == Region.id)
            .outerjoin(Utility, Event.utility_id == Utility.id)
            .where(
                or_(
                    Event.project_id == project_id,
                    Event.phase_id.in_(select(Phase.id).where(Phase.project_id == project_id)),
                    and_(
                        Event.event_scope.in_(
                            [EventScope.REGION, EventScope.RTO, EventScope.UTILITY, EventScope.COUNTY]
                        ),
                        or_(
                            Event.region_id == project_region_id,
                            Event.utility_id == project_utility_id,
                        ),
                    ),
                )
            )
            .order_by(Event.event_date.desc(), Event.created_at.desc())
        )
        rows = self.db.execute(stmt).all()
        return [
            ProjectEventRow(
                event=row[0],
                phase_name=row[1],
                region_name=row[2],
                utility_name=row[3],
            )
            for row in rows
        ]

    def list_explicit_project_event_ids(self, project_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(Event.id).where(
            or_(
                Event.project_id == project_id,
                Event.phase_id.in_(select(Phase.id).where(Phase.project_id == project_id)),
            )
        )
        return list(self.db.execute(stmt).scalars().all())
