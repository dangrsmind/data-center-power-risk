from __future__ import annotations

import os
import csv
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base
from app.api.routes.project_candidates import project_candidate_response
from app.models.imported_dataset import ImportedCandidateLink, ImportedDatasetRow, ImportedDatasetRun
from app.models.project import Project
from app.models.project_candidate import ProjectCandidate
from app.services.csv_dataset_importer import CsvDatasetImporter
from app.services.project_candidate_triage import ProjectCandidateTriageService


class CsvDatasetImporterTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)
        Base.metadata.create_all(bind=self.engine)
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        self.engine.dispose()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def write_csv(self, name: str, text: str) -> Path:
        path = Path(self.tmpdir.name) / name
        path.write_text(text, encoding="utf-8")
        return path

    def first_csv_row(self, path: Path) -> dict[str, str]:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return next(iter(csv.DictReader(handle)))

    def test_epoch_data_centers_mapping_and_dry_run_writes_nothing(self) -> None:
        path = self.write_csv(
            "data_centers.csv",
            "Name,Owner,Users,Current power (MW),Country,Address,Selected Sources,Notes,Project,Energy companies,Calculations sheet\n"
            "Example Frontier Campus,Example Owner,Example User,240,USA,\"Richmond, VA\",https://example.com/source,Public note,Example Family,Dominion,https://example.com/calc\n",
        )
        db = self.SessionLocal()
        try:
            summary = CsvDatasetImporter(db).import_file(dataset="epoch_frontier", input_path=path)

            self.assertEqual(summary.rows_read, 1)
            self.assertEqual(summary.rows_skipped, 1)
            self.assertEqual(summary.promoted, 0)
            self.assertEqual(db.query(ImportedDatasetRow).count(), 0)
            row = CsvDatasetImporter(db).normalize_rows("epoch_frontier", [{"__row_number": 2, **self.first_csv_row(path)}], source_file=str(path), dataset_source=None)[0]
            self.assertEqual(row.normalized["name"], "Example Frontier Campus")
            self.assertEqual(row.normalized["developer"], "Example Owner")
            self.assertEqual(row.normalized["load_mw"], 240.0)
            self.assertIn("https://example.com/source", row.source_urls)
        finally:
            db.close()

    def test_epoch_timeline_mapping_includes_claims_and_link_hint(self) -> None:
        path = self.write_csv(
            "data_center_timelines.csv",
            "Data center,Date,Construction status,IT power (MW),Power (MW),Water use (MGD),Capital cost ($),Source\n"
            "Example Frontier Campus,2025-01-01,Under construction,120,240,2.5,$1B,https://example.com/timeline\n",
        )
        db = self.SessionLocal()
        try:
            row = CsvDatasetImporter(db).normalize_rows(
                "epoch_frontier",
                [{"__row_number": 2, **self.first_csv_row(path)}],
                source_file=str(path),
                dataset_source=None,
            )[0]

            self.assertEqual(row.normalized["dataset_row_type"], "timeline")
            self.assertEqual(row.normalized["name"], "Example Frontier Campus")
            self.assertEqual(row.normalized["claims"]["it_power_mw"], 120.0)
            self.assertEqual(row.normalized["claims"]["power_mw"], 240.0)
            self.assertIn("linked_candidate_key_hint", row.normalized)
        finally:
            db.close()

    def test_fractracker_flexible_mapping_and_unmapped_columns(self) -> None:
        path = self.write_csv(
            "fractracker_db_output_v2.csv",
            "Facility Name,Status,Company,County,State,Latitude,Longitude,MW,Square Footage,URL,Cooling,Power Source,Unexpected Column\n"
            "Open Tracker Campus,Planned,Tracker Co,Loudoun,Virginia,39.1,-77.5,300,1000000,https://example.com/open,Water,Grid,keep me\n",
        )
        db = self.SessionLocal()
        try:
            summary = CsvDatasetImporter(db).import_file(dataset="fractracker_open_us", input_path=path)

            self.assertEqual(summary.rows_read, 1)
            self.assertIn("Unexpected Column", summary.unmapped_columns)
            row = CsvDatasetImporter(db).normalize_rows(
                "fractracker_open_us",
                [{"__row_number": 2, **self.first_csv_row(path)}],
                source_file=str(path),
                dataset_source=None,
            )[0]
            self.assertEqual(row.normalized["name"], "Open Tracker Campus")
            self.assertEqual(row.normalized["state"], "VA")
            self.assertEqual(row.normalized["load_mw"], 300.0)
            self.assertEqual(row.normalized["square_feet"], 1000000.0)
            self.assertIn("Unexpected Column", row.unmapped_columns)
        finally:
            db.close()

    def test_confirm_writes_imported_rows_preserves_metadata_and_creates_no_projects(self) -> None:
        path = self.write_csv(
            "data_centers.csv",
            "Name,Owner,Country,Address,Selected Sources\n"
            "Example Frontier Campus,Example Owner,USA,\"Richmond, VA\",https://example.com/source\n",
        )
        db = self.SessionLocal()
        try:
            summary = CsvDatasetImporter(db).import_file(
                dataset="epoch_frontier",
                input_path=path,
                confirm=True,
                source_url="https://epoch.ai/data/frontier-data-centers",
                license_note="test license",
                citation="test citation",
            )
            db.commit()

            self.assertEqual(summary.rows_imported, 1)
            self.assertEqual(db.query(ImportedDatasetRun).count(), 1)
            imported_row = db.query(ImportedDatasetRow).one()
            self.assertEqual(imported_row.raw_row_json["Name"], "Example Frontier Campus")
            self.assertEqual(imported_row.normalized_row_json["license_note"], "test license")
            self.assertEqual(imported_row.normalized_row_json["citation"], "test citation")
            self.assertIn("https://epoch.ai/data/frontier-data-centers", imported_row.source_urls_json)
            self.assertEqual(db.query(Project).count(), 0)
        finally:
            db.close()

    def test_create_candidates_is_opt_in_needs_review_and_never_promotes(self) -> None:
        path = self.write_csv(
            "data_centers.csv",
            "Name,Owner,Country,Address,Selected Sources\n"
            "Example Frontier Campus,Example Owner,USA,\"Richmond, VA\",https://example.com/source\n",
        )
        db = self.SessionLocal()
        try:
            summary = CsvDatasetImporter(db).import_file(
                dataset="epoch_frontier",
                input_path=path,
                confirm=True,
                create_candidates=True,
            )
            db.commit()

            self.assertEqual(summary.candidates_created, 1)
            self.assertEqual(summary.candidate_links_created, 1)
            candidate = db.query(ProjectCandidate).one()
            self.assertEqual(candidate.status, "needs_review")
            self.assertFalse(candidate.auto_admit_eligible)
            self.assertEqual(candidate.raw_metadata_json["provenance"], "dataset_import")
            self.assertEqual(candidate.raw_metadata_json["dataset_name"], "epoch_frontier")
            self.assertEqual(candidate.raw_metadata_json["duplicate_status"], "distinct")
            self.assertEqual(len(candidate.raw_metadata_json["imported_rows"]), 1)
            self.assertIsNone(candidate.review_decision)
            self.assertIsNone(candidate.review_notes)
            self.assertIsNone(candidate.reviewed_by)
            self.assertIsNone(candidate.reviewed_at)
            imported_row = db.query(ImportedDatasetRow).one()
            self.assertEqual(imported_row.linked_project_candidate_id, candidate.id)
            self.assertEqual(db.query(ImportedCandidateLink).count(), 1)
            self.assertIsNone(candidate.promoted_project_id)
            self.assertEqual(db.query(Project).count(), 0)
        finally:
            db.close()

    def test_create_candidates_dry_run_reports_without_writes(self) -> None:
        path = self.write_csv(
            "data_centers.csv",
            "Name,Owner,Country,Address,Selected Sources\n"
            "Example Frontier Campus,Example Owner,USA,\"Richmond, VA\",https://example.com/source\n",
        )
        db = self.SessionLocal()
        try:
            summary = CsvDatasetImporter(db).import_file(
                dataset="epoch_frontier",
                input_path=path,
                create_candidates=True,
            )

            self.assertEqual(summary.rows_read, 1)
            self.assertEqual(summary.rows_skipped, 1)
            self.assertEqual(summary.candidates_created, 1)
            self.assertEqual(summary.candidate_links_created, 1)
            self.assertEqual(db.query(ImportedDatasetRow).count(), 0)
            self.assertEqual(db.query(ProjectCandidate).count(), 0)
            self.assertEqual(db.query(Project).count(), 0)
        finally:
            db.close()

    def test_rows_missing_identity_or_provenance_do_not_create_candidates(self) -> None:
        missing_identity = self.write_csv(
            "missing_identity.csv",
            "Name,URL\n"
            "No Location Campus,https://example.com/no-location\n",
        )
        missing_provenance = self.write_csv(
            "missing_provenance.csv",
            "Name,State\n"
            "No Source Campus,VA\n",
        )
        db = self.SessionLocal()
        try:
            identity_summary = CsvDatasetImporter(db).import_file(
                dataset="fractracker_open_us",
                input_path=missing_identity,
                confirm=True,
                create_candidates=True,
            )
            provenance_summary = CsvDatasetImporter(db).import_file(
                dataset="fractracker_open_us",
                input_path=missing_provenance,
                confirm=True,
                create_candidates=True,
            )
            db.commit()

            self.assertEqual(identity_summary.skipped_candidate_missing_identity, 1)
            self.assertEqual(identity_summary.candidates_created, 0)
            self.assertEqual(provenance_summary.skipped_candidate_missing_provenance, 1)
            self.assertEqual(provenance_summary.candidates_created, 0)
            self.assertEqual(db.query(ImportedDatasetRow).count(), 2)
            self.assertEqual(db.query(ProjectCandidate).count(), 0)
            self.assertEqual(db.query(Project).count(), 0)
        finally:
            db.close()

    def test_matching_existing_candidate_links_instead_of_duplicating(self) -> None:
        path = self.write_csv(
            "fractracker_db_output_v2.csv",
            "Name,State,URL,MW\n"
            "Shared Campus,VA,https://example.com/shared,100\n",
        )
        db = self.SessionLocal()
        try:
            existing = ProjectCandidate(
                candidate_key="existing-shared-campus",
                candidate_name="Shared Campus",
                developer=None,
                state="VA",
                county=None,
                city=None,
                utility=None,
                load_mw=None,
                lifecycle_state="candidate_unverified",
                confidence=0.6,
                status="needs_review",
                source_count=1,
                claim_count=0,
                primary_source_url="https://example.com/shared",
                discovered_source_ids_json=[],
                discovered_source_claim_ids_json=[],
                evidence_excerpt=None,
                raw_metadata_json={},
                auto_admit_eligible=False,
            )
            db.add(existing)
            db.commit()

            summary = CsvDatasetImporter(db).import_file(
                dataset="fractracker_open_us",
                input_path=path,
                confirm=True,
                create_candidates=True,
            )
            db.commit()

            self.assertEqual(summary.candidates_created, 0)
            self.assertEqual(summary.candidates_updated, 1)
            self.assertEqual(summary.candidate_links_created, 1)
            self.assertEqual(summary.exact_duplicates, 1)
            self.assertEqual(db.query(ProjectCandidate).count(), 1)
            imported_row = db.query(ImportedDatasetRow).one()
            self.assertEqual(imported_row.linked_project_candidate_id, existing.id)
            self.assertEqual(imported_row.duplicate_status, "exact_duplicate")
            link = db.query(ImportedCandidateLink).filter(ImportedCandidateLink.linked_record_id == existing.id).one()
            self.assertEqual(link.duplicate_status, "exact_duplicate")
            db.refresh(existing)
            self.assertEqual(existing.raw_metadata_json["duplicate_status"], "exact_duplicate")
            self.assertFalse(existing.auto_admit_eligible)
            self.assertEqual(db.query(Project).count(), 0)
        finally:
            db.close()

    def test_project_candidate_api_includes_safe_csv_provenance(self) -> None:
        path = self.write_csv(
            "data_centers.csv",
            "Name,Owner,Country,Address,Selected Sources\n"
            "Example Frontier Campus,Example Owner,USA,\"Richmond, VA\",https://example.com/source\n",
        )
        db = self.SessionLocal()
        try:
            CsvDatasetImporter(db).import_file(
                dataset="epoch_frontier",
                input_path=path,
                confirm=True,
                create_candidates=True,
                citation="Epoch citation",
                license_note="Epoch license",
            )
            db.commit()
            candidate = db.query(ProjectCandidate).one()

            response = project_candidate_response(candidate)

            self.assertIsNone(response.raw_metadata_json)
            self.assertIsNotNone(response.csv_provenance)
            assert response.csv_provenance is not None
            self.assertEqual(response.csv_provenance.dataset_name, "epoch_frontier")
            self.assertEqual(response.csv_provenance.citation, "Epoch citation")
            self.assertEqual(response.csv_provenance.license_note, "Epoch license")
            self.assertEqual(response.csv_provenance.imported_row_count, 1)
            self.assertIn("https://example.com/source", response.csv_provenance.source_urls)
        finally:
            db.close()

    def test_triage_works_on_csv_created_candidate(self) -> None:
        path = self.write_csv(
            "data_centers.csv",
            "Name,Owner,Current power (MW),Country,Address,Selected Sources\n"
            "Example Frontier Campus,Example Owner,240,USA,\"Richmond, VA\",https://example.com/source\n",
        )
        db = self.SessionLocal()
        try:
            CsvDatasetImporter(db).import_file(
                dataset="epoch_frontier",
                input_path=path,
                confirm=True,
                create_candidates=True,
                citation="Epoch citation",
            )
            db.commit()
            candidate = db.query(ProjectCandidate).one()

            result = ProjectCandidateTriageService(db).triage(candidate, persist=True)
            db.commit()

            self.assertIn("dataset_import_provenance", result.triage_reasons)
            self.assertIn("dataset_import_requires_source_review", result.triage_warnings)
            self.assertEqual(candidate.status, "needs_review")
            self.assertFalse(candidate.auto_admit_eligible)
            self.assertEqual(db.query(Project).count(), 0)
        finally:
            db.close()

    def test_duplicate_source_urls_and_same_name_state_dedupe_conservatively(self) -> None:
        path = self.write_csv(
            "fractracker_db_output_v2.csv",
            "Name,State,URL,MW\n"
            "Shared Campus,VA,https://example.com/shared,100\n"
            "Shared Campus,VA,https://example.com/shared,100\n"
            "Shared Campus,VA,https://example.com/other,105\n",
        )
        db = self.SessionLocal()
        try:
            summary = CsvDatasetImporter(db).import_file(dataset="fractracker_open_us", input_path=path)

            self.assertEqual(summary.exact_duplicates, 1)
            self.assertEqual(summary.likely_same_project, 1)
        finally:
            db.close()

    def test_missing_location_and_name_warns_without_crashing(self) -> None:
        path = self.write_csv(
            "fractracker_db_output_v2.csv",
            "Company,URL\n"
            "No Name LLC,https://example.com/no-name\n",
        )
        db = self.SessionLocal()
        try:
            summary = CsvDatasetImporter(db).import_file(dataset="fractracker_open_us", input_path=path)

            self.assertEqual(summary.rows_read, 1)
            self.assertEqual(summary.insufficient_information, 1)
            self.assertTrue(any("missing_name" in warning for warning in summary.warnings))
            self.assertTrue(any("missing_location" in warning for warning in summary.warnings))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
