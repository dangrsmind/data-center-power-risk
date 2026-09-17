import os
import subprocess
import sys
import unittest
from sqlalchemy import select, func
from app.models import Base
from app.models.imported_dataset import ImportedDatasetRow, ImportedCandidateLink
from app.models.project_candidate import ProjectCandidate
from app.services.baseline_candidate_backfill import backfill_candidates
from app.services.csv_dataset_importer import CsvDatasetImporter
from tests import test_baseline_database_import as fixtures


class BackfillTest(unittest.TestCase):
    setUp = fixtures.BaselineImportTest.setUp
    tearDown = fixtures.BaselineImportTest.tearDown
    csv = fixtures.BaselineImportTest.csv
    sample = fixtures.BaselineImportTest.sample
    run_import = fixtures.BaselineImportTest.run_import
    assert_only_import_tables = fixtures.BaselineImportTest.assert_only_import_tables

    def seed(self, **extra):
        self.run_import([self.sample(**extra)], confirm=True)
        self.db.commit()
        return self.db.scalar(select(ImportedDatasetRow))

    def backfill(self, **kw):
        return backfill_candidates(self.db, dataset='epoch_ai_data_centers', **kw)

    def snapshot(self):
        return {t.name: [tuple(row) for row in self.db.execute(select(t))] for t in Base.metadata.sorted_tables}

    def test_preview_and_confirm_write_boundaries_and_rerun(self):
        audit = self.seed(latitude='39', longitude='-77')
        before = self.snapshot()
        result = self.backfill()
        self.assertEqual(result.would_create_candidates, 1)
        self.assertEqual(result.created_candidates, 0)
        self.assertEqual(before, self.snapshot())
        result = self.backfill(confirm=True)
        self.db.commit()
        self.assertEqual(result.created_candidates, 1)
        self.assertEqual(result.created_candidate_links, 1)
        after = self.snapshot()
        for table in before:
            if table not in {'project_candidates', 'imported_candidate_links'}:
                self.assertEqual(before[table], after[table], table)
        candidate = self.db.scalar(select(ProjectCandidate))
        self.assertEqual(candidate.status, 'needs_review')
        self.assertIsNone(candidate.verification_status)
        self.assertIsNone(candidate.verified_at)
        self.assertFalse(candidate.auto_admit_eligible)
        self.assertIsNone(candidate.promoted_project_id)
        self.assertEqual(candidate.claim_count, 0)
        metadata = candidate.raw_metadata_json
        self.assertEqual(metadata['import_kind'], 'baseline_dataset_import')
        self.assertEqual(metadata['provenance'], 'dataset_import')
        self.assertEqual(metadata['imported_row_id'], str(audit.id))
        self.assertEqual(metadata['import_run_id'], str(audit.run_id))
        self.assertEqual(metadata['raw_row'], audit.raw_row_json)
        self.assertEqual(metadata['latitude'], 39)
        self.assertIn('CC BY', metadata['license_note'])
        self.assert_only_import_tables(candidates=True)
        for confirm in (False, True):
            result = self.backfill(confirm=confirm)
            self.assertEqual(result.rows_skipped_already_linked, 1)
            self.assertEqual(result.would_create_candidates, 0)
            self.assertEqual(result.created_candidates, 0)

    def test_possible_duplicate_requires_opt_in(self):
        audit = self.seed()
        audit.duplicate_status = 'possible_duplicate'
        self.db.commit()
        self.assertEqual(self.backfill().rows_skipped_possible_duplicate, 1)
        result = self.backfill(confirm=True, include_possible_duplicates=True)
        self.assertEqual(result.created_candidates, 1)
        candidate = self.db.scalar(select(ProjectCandidate))
        self.assertEqual(candidate.raw_metadata_json['duplicate_status'], 'possible_duplicate')
        self.assertTrue(any('possible_duplicate' in w for w in candidate.raw_metadata_json['warnings']))

    def test_missing_identity_location_and_coordinates(self):
        audit = self.seed()
        self.assertEqual(self.backfill(only_mappable=True).rows_skipped_missing_coordinates_when_only_mappable, 1)
        self.assertEqual(self.backfill().rows_eligible, 1)
        original = dict(audit.normalized_row_json)
        for fields, counter in [({'name': None}, 'rows_skipped_missing_identity'),
                                ({'country': None}, 'rows_skipped_missing_location'),
                                ({'country': None, 'city': 'Example'}, 'rows_skipped_missing_identity')]:
            n = dict(original)
            n.update(fields)
            audit.normalized_row_json = n
            self.db.flush()
            self.assertEqual(getattr(self.backfill(), counter), 1)

    def test_fractracker_mappable_and_missing_source(self):
        path = self.csv([{'facility_name': 'Tracker', 'lat': '39.5', 'long': '-77.5', 'operator_name': 'Operator'}], 'fractracker.csv')
        CsvDatasetImporter(self.db).import_file(dataset='fractracker_us_data_centers', input_path=path, confirm=True)
        result = backfill_candidates(self.db, dataset='fractracker_us_data_centers', confirm=True, only_mappable=True)
        self.assertEqual(result.created_candidates, 1)
        self.assertEqual(result.rows_skipped_missing_public_source_url, 0)
        self.assertTrue(result.warnings)
        candidate = self.db.scalar(select(ProjectCandidate))
        self.assertEqual(candidate.developer, 'Operator')
        self.assertEqual(candidate.raw_metadata_json['latitude'], 39.5)
        self.assertEqual(candidate.raw_metadata_json['longitude'], -77.5)
        self.assertIsNone(candidate.primary_source_url)

    def test_exact_candidate_duplicate_never_overridden(self):
        self.seed()
        self.backfill(confirm=True)
        self.db.query(ImportedCandidateLink).delete()
        self.db.flush()
        result = self.backfill(include_possible_duplicates=True)
        self.assertEqual(result.rows_skipped_existing_candidate_duplicate, 1)
        self.assertEqual(result.rows_eligible, 0)

    def test_limit_and_run_filter(self):
        audit = self.seed()
        self.assertEqual(self.backfill(limit=0).rows_checked, 0)
        self.assertEqual(self.backfill(import_run_id=str(audit.run_id)).rows_checked, 1)
        self.assertEqual(self.backfill(import_run_id='00000000-0000-0000-0000-000000000000').rows_checked, 0)
        with self.assertRaises(ValueError):
            self.backfill(limit=-1)

    def test_cli_no_writes_and_requires_explicit_mode(self):
        self.seed()
        before = self.database.read_bytes()
        args = [sys.executable, 'scripts/backfill_baseline_candidates.py', '--dataset', 'epoch_ai_data_centers']
        env = {**os.environ, 'DATABASE_URL': f'sqlite:///{self.database}'}
        for flags, expected in [(['--dry-run'], 0), ([], 2), (['--confirm', '--dry-run'], 2),
                                (['--dry-run', '--report-output', str(self.path / 'report.json')], 2)]:
            result = subprocess.run(args + flags, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, expected, result.stderr)
            self.assertEqual(before, self.database.read_bytes())
        self.assertFalse((self.path / 'report.json').exists())

    def test_batch_duplicates_preview_matches_confirm(self):
        self.run_import([self.sample(), self.sample(Name='Second')], confirm=True)
        preview = self.backfill(include_possible_duplicates=True)
        result = self.backfill(confirm=True, include_possible_duplicates=True)
        self.assertEqual(preview.would_create_candidates, 1)
        self.assertEqual(result.created_candidates, 1)
        self.assertEqual(result.rows_skipped_existing_candidate_duplicate, 1)

    def test_supporting_invalid_and_unparseable_coordinates(self):
        audit = self.seed()
        original = dict(audit.normalized_row_json)
        audit.normalized_row_json = {**original, 'dataset_row_type': 'timeline'}
        self.db.flush()
        self.assertEqual(self.backfill().rows_skipped_invalid_or_supporting, 1)
        audit.normalized_row_json = {**original, 'latitude': 'NaN', 'longitude': '200'}
        self.db.flush()
        self.assertEqual(self.backfill(only_mappable=True).rows_skipped_missing_coordinates_when_only_mappable, 1)
        audit.errors_json = ['invalid_input']
        self.db.flush()
        self.assertEqual(self.backfill().rows_skipped_invalid_or_supporting, 1)
