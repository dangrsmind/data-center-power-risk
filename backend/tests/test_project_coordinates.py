from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.routes.projects import (  # noqa: E402
    clear_project_coordinates,
    get_project_coordinate_history,
    list_missing_coordinates,
    patch_project_coordinates,
)
from app.core.enums import LifecycleState  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.schemas.project import ProjectCoordinatesRequest  # noqa: E402


class ProjectCoordinatesTest(unittest.TestCase):
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

    def _project(self, **kwargs) -> Project:
        db = self.SessionLocal()
        try:
            project = Project(
                canonical_name=kwargs.pop("canonical_name", "Coordinate Campus"),
                state=kwargs.pop("state", "VA"),
                county=kwargs.pop("county", "Example"),
                lifecycle_state=LifecycleState.CANDIDATE_UNVERIFIED,
                **kwargs,
            )
            db.add(project)
            db.commit()
            db.refresh(project)
            return project
        finally:
            db.close()

    def test_patch_coordinates_saves_valid_coordinates_and_history(self) -> None:
        project = self._project()
        db = self.SessionLocal()
        try:
            response = patch_project_coordinates(
                project.id,
                ProjectCoordinatesRequest(
                    latitude=37.5,
                    longitude=-78.5,
                    coordinate_precision="exact_site",
                    coordinate_status="verified",
                    coordinate_source="manual_review",
                    coordinate_confidence=0.8,
                    coordinate_notes="Reviewed against county parcel map.",
                ),
                db=db,
            )

            self.assertEqual(response.latitude, 37.5)
            self.assertEqual(response.longitude, -78.5)
            self.assertEqual(response.coordinate_status, "verified")
            history = get_project_coordinate_history(project.id, db=db)
            self.assertEqual(len(history), 1)
            self.assertIsNone(history[0].old_latitude)
            self.assertEqual(history[0].new_latitude, 37.5)
        finally:
            db.close()

    def test_patch_rejects_invalid_latitude_longitude_status_precision_and_confidence(self) -> None:
        invalid_cases = [
            {"latitude": 91, "longitude": -78, "coordinate_precision": "exact_site", "coordinate_status": "verified"},
            {"latitude": -91, "longitude": -78, "coordinate_precision": "exact_site", "coordinate_status": "verified"},
            {"latitude": 37, "longitude": 181, "coordinate_precision": "exact_site", "coordinate_status": "verified"},
            {"latitude": 37, "longitude": -181, "coordinate_precision": "exact_site", "coordinate_status": "verified"},
            {"latitude": 37, "longitude": -78, "coordinate_precision": "bad", "coordinate_status": "verified"},
            {"latitude": 37, "longitude": -78, "coordinate_precision": "exact_site", "coordinate_status": "bad"},
            {
                "latitude": 37,
                "longitude": -78,
                "coordinate_precision": "exact_site",
                "coordinate_status": "verified",
                "coordinate_confidence": 1.1,
            },
        ]
        for payload in invalid_cases:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    ProjectCoordinatesRequest(**payload)

    def test_missing_coordinates_returns_missing_and_needs_review_projects(self) -> None:
        missing = self._project(canonical_name="Missing", coordinate_status="missing")
        needs_review = self._project(
            canonical_name="Needs Review",
            latitude=37.1,
            longitude=-78.1,
            coordinate_status="needs_review",
            coordinate_precision="approximate",
        )
        self._project(
            canonical_name="Verified",
            latitude=37.2,
            longitude=-78.2,
            coordinate_status="verified",
            coordinate_precision="exact_site",
        )

        db = self.SessionLocal()
        try:
            rows = list_missing_coordinates(db=db)
            ids = {row.id for row in rows}
            self.assertIn(missing.id, ids)
            self.assertIn(needs_review.id, ids)
            self.assertEqual(len(rows), 2)
        finally:
            db.close()

    def test_history_is_newest_first_and_clear_creates_history(self) -> None:
        project = self._project(latitude=37.0, longitude=-78.0, coordinate_status="unverified")
        db = self.SessionLocal()
        try:
            patch_project_coordinates(
                project.id,
                ProjectCoordinatesRequest(
                    latitude=37.5,
                    longitude=-78.5,
                    coordinate_precision="exact_site",
                    coordinate_status="verified",
                    coordinate_source="manual_review",
                ),
                db=db,
            )
            cleared = clear_project_coordinates(project.id, db=db)
            self.assertIsNone(cleared.latitude)
            self.assertIsNone(cleared.longitude)
            self.assertEqual(cleared.coordinate_status, "missing")

            history = get_project_coordinate_history(project.id, db=db)
            self.assertEqual(len(history), 2)
            self.assertIsNone(history[0].new_latitude)
            self.assertEqual(history[1].new_latitude, 37.5)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
