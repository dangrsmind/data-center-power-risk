from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.routes.projects import get_project_enrichment  # noqa: E402
from app.core.enums import LifecycleState  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.enrichment import ProjectEnrichmentSnapshot  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.services.enrichment_service import EnrichmentService  # noqa: E402


class ProjectEnrichmentTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)
        Base.metadata.create_all(bind=self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_enrichment_returns_containing_hifld_retail_utility_and_stores_snapshot(self) -> None:
        db = self.SessionLocal()
        try:
            project = Project(
                canonical_name="Coordinate Campus",
                state="VA",
                county="Example",
                latitude=37.5,
                longitude=-78.5,
                lifecycle_state=LifecycleState.CANDIDATE_UNVERIFIED,
            )
            db.add(project)
            db.commit()
            loaded = EnrichmentService(db).load_hifld_retail_territories(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"OBJECTID": 1, "NAME": "Example Electric"},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [
                                    [
                                        [-79.0, 37.0],
                                        [-78.0, 37.0],
                                        [-78.0, 38.0],
                                        [-79.0, 38.0],
                                        [-79.0, 37.0],
                                    ]
                                ],
                            },
                        }
                    ],
                }
            )
            self.assertEqual(loaded, 1)

            response = get_project_enrichment(project.id, db=db)

            self.assertEqual(response.utility, "Example Electric")
            self.assertEqual(response.confidence, "medium")
            self.assertEqual(response.source, "HIFLD")

            snapshot = db.query(ProjectEnrichmentSnapshot).filter_by(project_id=project.id).one()
            self.assertEqual(snapshot.retail_utility_name, "Example Electric")
            self.assertEqual(snapshot.confidence, "medium")
            self.assertEqual(snapshot.source, "HIFLD")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
