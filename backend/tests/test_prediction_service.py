from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from app.core.enums import LifecycleState  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.prediction import ProjectPrediction  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.api.routes.projects import run_project_prediction as run_project_prediction_api  # noqa: E402
from app.services.prediction_service import MODEL_VERSION, PredictionService  # noqa: E402
from app.services.project_prediction_runner import run_prediction_for_project  # noqa: E402
from run_demo_predictions import run_predictions  # noqa: E402


class PredictionServiceTest(unittest.TestCase):
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

    def _project(self, db, **kwargs) -> Project:
        project = Project(
            canonical_name=kwargs.pop("canonical_name", "Demo Prediction Campus"),
            state=kwargs.pop("state", "VA"),
            county=kwargs.pop("county", "Caroline"),
            lifecycle_state=kwargs.pop("lifecycle_state", LifecycleState.CANDIDATE_UNVERIFIED),
            candidate_metadata_json=kwargs.pop("candidate_metadata_json", None),
            **kwargs,
        )
        db.add(project)
        db.flush()
        return project

    def test_v02_returns_valid_monotonic_probabilities_and_drivers(self) -> None:
        db = self.SessionLocal()
        try:
            project = self._project(
                db,
                latitude=38.03,
                longitude=-77.35,
                coordinate_status="unverified",
                coordinate_precision="approximate",
                candidate_metadata_json={
                    "demo_dataset_id": "demo_projects_v0_1",
                    "load_mw": 900,
                    "load_bucket": "900+ MW",
                    "iso_region": "PJM",
                    "source_url": "https://example.test/source",
                    "evidence_excerpt": "A source-backed excerpt describing the planned demo project load.",
                },
            )
            db.commit()

            response = PredictionService(db).get_project_prediction(project.id)

            self.assertEqual(response.model_version, MODEL_VERSION)
            self.assertEqual(response.model_name, "baseline_power_delay")
            self.assertGreaterEqual(response.p_delay_6mo, 0)
            self.assertLessEqual(response.p_delay_18mo, 1)
            self.assertLessEqual(response.p_delay_6mo, response.p_delay_12mo)
            self.assertLessEqual(response.p_delay_12mo, response.p_delay_18mo)
            self.assertTrue(response.drivers)
            self.assertTrue(any("Large load" in driver.driver for driver in response.drivers))
            self.assertTrue(any(driver.driver == "Utility not confirmed" for driver in response.drivers))
        finally:
            db.close()

    def test_missing_fields_do_not_crash_and_lower_confidence(self) -> None:
        db = self.SessionLocal()
        try:
            project = self._project(db, canonical_name="Sparse Prediction Campus")
            db.commit()

            response = PredictionService(db).get_project_prediction(project.id)

            self.assertEqual(response.confidence, "low")
            self.assertGreater(response.p_delay_18mo, 0)
            self.assertTrue(response.drivers)
            self.assertIn("load_mw", response.missing_inputs)
            self.assertTrue(any(driver.driver == "Load size unknown" for driver in response.drivers))
        finally:
            db.close()

    def test_run_demo_predictions_does_not_duplicate_predictions(self) -> None:
        db = self.SessionLocal()
        try:
            self._project(
                db,
                canonical_name="Stored Demo Campus",
                coordinate_status="unverified",
                coordinate_precision="approximate",
                candidate_metadata_json={
                    "demo_dataset_id": "demo_projects_v0_1",
                    "load_mw": 300,
                    "source_url": "https://example.test/source",
                },
            )
            db.commit()
        finally:
            db.close()

        with patch("run_demo_predictions.SessionLocal", self.SessionLocal):
            first = run_predictions()
            second = run_predictions()

        db = self.SessionLocal()
        try:
            predictions = db.scalars(select(ProjectPrediction)).all()

            self.assertEqual(first.projects_scored, 1)
            self.assertEqual(first.predictions_created, 1)
            self.assertEqual(second.projects_scored, 1)
            self.assertEqual(second.predictions_created, 0)
            self.assertEqual(len(predictions), 1)
            self.assertEqual(predictions[0].model_version, MODEL_VERSION)
        finally:
            db.close()

    def test_single_project_prediction_runner_creates_prediction(self) -> None:
        db = self.SessionLocal()
        try:
            project = self._project(
                db,
                candidate_metadata_json={
                    "load_mw": 300,
                    "source_url": "https://example.test/source",
                    "evidence_excerpt": "A source-backed excerpt describing the project.",
                },
            )
            db.commit()
            result = run_prediction_for_project(db, project.id)
            db.commit()
            prediction = db.scalar(select(ProjectPrediction))
        finally:
            db.close()

        self.assertTrue(result.prediction_created)
        self.assertFalse(result.prediction_updated)
        self.assertEqual(result.errors, [])
        self.assertIsNotNone(prediction)
        self.assertEqual(prediction.project_id, project.id)

    def test_single_project_prediction_runner_updates_idempotently(self) -> None:
        db = self.SessionLocal()
        try:
            project = self._project(
                db,
                candidate_metadata_json={"load_mw": 300, "source_url": "https://example.test/source"},
            )
            db.commit()
            first = run_prediction_for_project(db, project.id)
            db.commit()
            project.candidate_metadata_json = {"load_mw": 900, "source_url": "https://example.test/source"}
            second = run_prediction_for_project(db, project.id)
            db.commit()
            third = run_prediction_for_project(db, project.id)
            db.commit()
            predictions = db.scalars(select(ProjectPrediction)).all()
        finally:
            db.close()

        self.assertTrue(first.prediction_created)
        self.assertTrue(second.prediction_updated)
        self.assertTrue(third.prediction_skipped)
        self.assertEqual(len(predictions), 1)

    def test_single_project_prediction_runner_missing_project_returns_clean_error(self) -> None:
        db = self.SessionLocal()
        try:
            project_id = uuid.uuid4()
            result = run_prediction_for_project(db, project_id)
        finally:
            db.close()

        self.assertEqual(result.project_id, str(project_id))
        self.assertIn("project_not_found", result.errors)

    def test_prediction_run_api_endpoint_creates_prediction(self) -> None:
        db = self.SessionLocal()
        try:
            project = self._project(db, candidate_metadata_json={"source_url": "https://example.test/source"})
            db.commit()
            response = run_project_prediction_api(project.id, db)
            prediction = db.scalar(select(ProjectPrediction))
        finally:
            db.close()

        self.assertTrue(response.prediction_created)
        self.assertEqual(response.project_id, project.id)
        self.assertIsNotNone(prediction)

    def test_prediction_run_api_endpoint_missing_project_raises_404(self) -> None:
        db = self.SessionLocal()
        try:
            with self.assertRaises(HTTPException) as context:
                run_project_prediction_api(uuid.uuid4(), db)
        finally:
            db.close()

        self.assertEqual(context.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
