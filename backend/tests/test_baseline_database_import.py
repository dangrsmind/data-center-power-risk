import csv
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from app.models import Base
from app.models.imported_dataset import ImportedDatasetRun, ImportedDatasetRow, ImportedCandidateLink
from app.models.project_candidate import ProjectCandidate
from app.services.csv_dataset_importer import CsvDatasetImporter
from app.api.routes.project_candidates import csv_provenance_from_metadata


class BaselineImportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.database = self.path / 'test.db'
        self.engine = create_engine(f'sqlite:///{self.database}')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.tmp.cleanup()

    def csv(self, rows, name='data_centers.csv'):
        path = self.path / name
        fields = list(dict.fromkeys(key for row in rows for key in row))
        with path.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def sample(self, **extra):
        return {'Name': 'Example campus', 'Country': 'USA', 'Owner': 'Owner',
                'Current power (MW)': '1,200', 'Selected Sources': 'https://example.org/facility', **extra}

    def run_import(self, rows, **options):
        return CsvDatasetImporter(self.db).import_file(dataset='epoch_ai_data_centers', input_path=self.csv(rows), **options)

    def assert_only_import_tables(self, candidates=False):
        allowed = {ImportedDatasetRun.__tablename__, ImportedDatasetRow.__tablename__, ImportedCandidateLink.__tablename__}
        if candidates:
            allowed.add(ProjectCandidate.__tablename__)
        for table in Base.metadata.sorted_tables:
            if table.name not in allowed:
                self.assertEqual(self.db.scalar(select(func.count()).select_from(table)), 0, table.name)

    def test_epoch_candidate_provenance_and_safety(self):
        raw = self.sample(latitude='39.1', longitude='-77.1', Notes='Original note')
        result = self.run_import([raw], confirm=True, create_candidates=True)
        self.assertEqual(result.created_candidates, 1)
        audit = self.db.scalar(select(ImportedDatasetRow))
        self.assertEqual(audit.raw_row_json, raw)
        normalized = audit.normalized_row_json
        self.assertEqual(normalized['load_mw'], 1200)
        self.assertEqual(normalized['country'], 'US')
        self.assertEqual(normalized['latitude'], 39.1)
        candidate = self.db.scalar(select(ProjectCandidate))
        self.assertEqual(candidate.status, 'needs_review')
        self.assertIsNone(candidate.verification_status)
        self.assertFalse(candidate.auto_admit_eligible)
        self.assertIsNone(candidate.promoted_project_id)
        self.assertEqual(candidate.claim_count, 0)
        provenance = csv_provenance_from_metadata(candidate.raw_metadata_json)
        self.assertEqual(provenance.import_kind, 'baseline_dataset_import')
        self.assertEqual(provenance.import_run_id, result.import_run_id)
        self.assertIn('CC BY', provenance.license_note)
        self.assertIn('Epoch', provenance.citation)
        self.assert_only_import_tables(candidates=True)

    def test_fractracker_columns(self):
        path = self.csv([{'facility_name': 'Tracker campus', 'state': 'Virginia', 'lat': '39', 'long': '-77',
                          'mw': '250', 'operator_name': 'Operator', 'cooling_source': 'Water',
                          'expected_date_online': '2028', 'info_source_1': 'https://example.org/tracker'}], 'fractracker_db_output_v2.csv')
        result = CsvDatasetImporter(self.db).import_file(dataset='fractracker_us_data_centers', input_path=path, confirm=True)
        self.assertEqual(result.created_import_records, 1)
        row = self.db.scalar(select(ImportedDatasetRow)).normalized_row_json
        for field, value in {'name': 'Tracker campus', 'state': 'VA', 'load_mw': 250, 'cooling': 'Water', 'opening_date': '2028', 'country': None}.items():
            self.assertEqual(row[field], value)
        self.assertIn('License not supplied', row['license_note'])
        self.assert_only_import_tables()

    def test_dry_run_and_audit_only(self):
        result = self.run_import([self.sample()], create_candidates=True)
        self.assertEqual(result.would_create_candidates, 1)
        self.assertEqual(result.created_import_records, 0)
        for table in Base.metadata.sorted_tables:
            self.assertEqual(self.db.scalar(select(func.count()).select_from(table)), 0)
        result = self.run_import([self.sample()], confirm=True)
        self.assertEqual(result.created_import_records, 1)
        self.assertEqual(result.created_candidates, 0)
        self.assert_only_import_tables()

    def test_missing_identity_coordinates_and_sources(self):
        result = self.run_import([{'Name': '', 'Country': 'US'}, {'Name': 'Named', 'Country': 'US'}], confirm=True, create_candidates=True)
        self.assertEqual(result.rows_invalid, 1)
        self.assertEqual(result.rows_missing_identity, 1)
        self.assertEqual(result.rows_missing_coordinates, 2)
        self.assertEqual(result.rows_missing_public_source_url, 2)
        self.assertEqual(result.created_candidates, 1)
        self.assertTrue(any('missing_public_source_url' in warning for warning in result.warnings))
        self.assert_only_import_tables(candidates=True)

    def test_exact_repeat_and_changed_id_are_not_merged(self):
        self.run_import([self.sample(id='stable')], confirm=True, create_candidates=True)
        result = self.run_import([self.sample(id='stable')], confirm=True, create_candidates=True)
        self.assertEqual(result.duplicate_rows_skipped, 1)
        self.assertEqual(result.created_import_records, 0)
        result = self.run_import([self.sample(id='stable', Name='Changed')], confirm=True, create_candidates=True)
        self.assertEqual(result.possible_duplicates_flagged, 1)
        self.assertEqual(result.created_candidates, 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ProjectCandidate)), 1)

    def test_duplicate_name_location_coordinates_and_url(self):
        rows = [self.sample(), self.sample(**{'Selected Sources': 'https://example.org/other'}),
                self.sample(Name='Other campus')]
        preview = self.run_import(rows, create_candidates=True)
        result = self.run_import(rows, confirm=True, create_candidates=True)
        self.assertEqual(result.possible_duplicates_flagged, 2)
        self.assertEqual(result.created_candidates, 1)
        self.assertEqual(preview.would_create_candidates, result.created_candidates)
        nearby = [{'Name': 'Nearby', 'latitude': '10', 'longitude': '20'},
                  {'Name': 'Nearby', 'latitude': '10.001', 'longitude': '20.001'}]
        self.assertEqual(self.run_import(nearby).possible_duplicates_flagged, 1)

    def test_existing_candidate_not_mutated(self):
        self.run_import([self.sample()], confirm=True, create_candidates=True)
        candidate = self.db.scalar(select(ProjectCandidate))
        candidate.status = 'rejected'
        self.db.flush()
        result = self.run_import([self.sample(Notes='updated')], confirm=True, create_candidates=True)
        self.assertEqual(result.created_candidates, 0)
        self.assertEqual(candidate.status, 'rejected')

    def test_supporting_files_are_audit_only(self):
        for name in ['data_center_timelines.csv', 'data_center_chillers.csv', 'data_center_cooling_towers.csv']:
            result = CsvDatasetImporter(self.db).import_file(dataset='epoch_ai_data_centers', input_path=self.csv([self.sample()], name), confirm=True, create_candidates=True)
            self.assertEqual(result.created_candidates, 0)
        self.assert_only_import_tables()

    def test_invalid_coordinates_and_ambiguous_numeric(self):
        result = self.run_import([self.sample(latitude='99', **{'Current power (MW)': '100-200'})], confirm=True, create_candidates=True)
        self.assertEqual(result.rows_invalid, 1)
        self.assertEqual(result.created_candidates, 0)
        self.assertIsNone(self.db.scalar(select(ImportedDatasetRow)).normalized_row_json['load_mw'])

    def test_landing_page_is_not_evidence(self):
        result = self.run_import([self.sample(**{'Selected Sources': 'https://epoch.ai/data/data-centers'})])
        self.assertEqual(result.rows_missing_public_source_url, 1)

    def test_cli_read_only_and_explicit_modes(self):
        path = self.csv([self.sample()])
        args = [sys.executable, 'scripts/import_baseline_open_databases.py', '--dataset', 'epoch_ai_data_centers', '--input', str(path)]
        env = {**os.environ, 'DATABASE_URL': f'sqlite:///{self.database}'}
        before = self.database.read_bytes()
        result = subprocess.run(args + ['--dry-run'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, self.database.read_bytes())
        self.assertNotEqual(subprocess.run(args, env=env, capture_output=True).returncode, 0)
        report = self.path / 'report.json'
        self.assertNotEqual(subprocess.run(args + ['--dry-run', '--report-output', str(report)], env=env, capture_output=True).returncode, 0)
        self.assertFalse(report.exists())

    def test_units_and_legacy_entrypoint_cannot_bypass_safety(self):
        self.run_import([self.sample(latitude='39 MW', **{'Current power (MW)': '2 MGD'})], confirm=True)
        row = self.db.scalar(select(ImportedDatasetRow)).normalized_row_json
        self.assertIsNone(row['latitude'])
        self.assertIsNone(row['load_mw'])
        missing = self.path / 'must-not-create.db'
        result = subprocess.run([sys.executable, 'scripts/import_csv_dataset.py', '--dataset',
            'epoch_ai_data_centers', '--input', str(self.csv([self.sample()]))],
            env={**os.environ, 'DATABASE_URL': f'sqlite:///{missing}'}, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('import_baseline_open_databases.py', result.stderr)
        self.assertFalse(missing.exists())
