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
    def sample(self, **extra):
        return fixtures.BaselineImportTest.sample(self, **{
            'status': 'Proposed',
            'Selected Sources': 'https://www.datacenterdynamics.com/en/news/proposed-example-campus/',
            **extra,
        })
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
        before = self.snapshot()
        result = backfill_candidates(self.db, dataset='fractracker_us_data_centers', only_mappable=True, include_row_details=True)
        self.assertEqual(result.created_candidates, 0)
        self.assertEqual(result.rows_skipped_weak_source_quality, 1)
        self.assertEqual(result.row_details[0]['source_quality'], 'unknown')
        self.assertEqual(result.row_details[0]['latitude'], 39.5)
        self.assertEqual(result.row_details[0]['longitude'], -77.5)
        self.assertEqual(self.snapshot(), before)

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

    def test_25_row_window_preserves_linked_duplicate_context(self):
        import hashlib
        rows = [{'facility_name': hashlib.sha256(str(i).encode()).hexdigest()[:16],
                 'lat': str(10 + i), 'long': '40', 'info_source_1': f'https://www.datacenterdynamics.com/en/news/proposed-site-{i}'}
                for i in range(25)]
        # Fifteen distinct rows, two shared-URL exact duplicates, three nearby
        # rows detected only against full audit coordinates, five flagged rows.
        for i in range(2):
            rows[15 + i]['info_source_1'] = rows[i]['info_source_1']
        for i in range(3):
            rows[17 + i]['lat'] = str(10 + i + .001)
        path = self.csv(rows, 'fractracker.csv')
        CsvDatasetImporter(self.db).import_file(dataset='fractracker_us_data_centers', input_path=path, confirm=True)
        audits = list(self.db.scalars(select(ImportedDatasetRow).order_by(ImportedDatasetRow.row_number)))
        for index, audit in enumerate(audits):
            audit.duplicate_status = 'possible_duplicate' if index >= 20 else 'distinct'
        self.db.commit()
        flags = dict(dataset='fractracker_us_data_centers', only_mappable=True, limit=25)
        before = self.snapshot()
        preview = backfill_candidates(self.db, **flags)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(preview.rows_checked, 25)
        self.assertEqual(preview.would_create_candidates, 15)
        self.assertEqual(preview.rows_skipped_existing_candidate_duplicate, 2)
        self.assertEqual(preview.rows_skipped_possible_duplicate, 8)
        result = backfill_candidates(self.db, confirm=True, **flags)
        self.db.commit()
        self.assertEqual(result.created_candidates, 15)
        self.assertEqual(result.created_candidate_links, 15)
        after = self.snapshot()
        for confirm in (False, True):
            repeat = backfill_candidates(self.db, confirm=confirm, **flags)
            self.db.commit()
            self.assertEqual(repeat.rows_checked, 25)
            self.assertEqual(repeat.rows_skipped_already_linked, 15)
            self.assertEqual(repeat.rows_skipped_existing_candidate_duplicate, 2)
            self.assertEqual(repeat.rows_skipped_possible_duplicate, 8)
            self.assertEqual(repeat.would_create_candidates, 0)
            self.assertEqual(repeat.created_candidates, 0)
            self.assertEqual(repeat.created_projects, 0)
            self.assertEqual(repeat.created_evidence, 0)
            self.assertEqual(self.snapshot(), after)
        self.assert_only_import_tables(candidates=True)
        override = backfill_candidates(self.db, include_possible_duplicates=True, **flags)
        self.assertEqual(override.would_create_candidates, 8)
        self.assertEqual(override.rows_skipped_existing_candidate_duplicate, 2)

    def test_explicit_offset_advances_audit_window(self):
        self.run_import([self.sample(Name='First'), self.sample(Name='Next', **{'Selected Sources': 'https://www.datacenterknowledge.com/news/proposed-next-campus'})], confirm=True)
        # Distinct input location to avoid intentional ambiguity from sample names.
        audits = list(self.db.scalars(select(ImportedDatasetRow).order_by(ImportedDatasetRow.row_number)))
        audits[1].duplicate_status = 'distinct'
        self.db.commit()
        first = self.backfill(limit=1, confirm=True)
        self.assertEqual(first.created_candidates, 1)
        self.assertEqual(self.backfill(limit=1).rows_skipped_already_linked, 1)
        next_batch = self.backfill(limit=1, offset=1)
        self.assertEqual(next_batch.offset, 1)
        self.assertEqual(next_batch.rows_checked, 1)
        self.assertEqual(next_batch.would_create_candidates, 1)
        self.assertEqual(self.backfill(limit=1, offset=2).rows_checked, 0)
        with self.assertRaises(ValueError):
            self.backfill(offset=-1)

    def test_preview_pages_reconcile_with_full_prefix_context_and_details(self):
        import hashlib
        from datetime import datetime, timedelta
        rows = [{'facility_name': hashlib.sha256(str(i).encode()).hexdigest()[:16],
                 'lat': str(10 + i), 'long': '40', 'operator_name': f'Operator {i}',
                 'info_source_1': f'https://www.datacenterdynamics.com/en/news/proposed-facility-{i}'} for i in range(30)]
        # Duplicate signals span page boundaries, including a row before offset.
        rows[5]['lat'] = '10.001'
        rows[12]['lat'] = '16.001'
        rows[18]['info_source_1'] = rows[9]['info_source_1']
        path = self.csv(list(reversed(rows)), 'fractracker.csv')
        CsvDatasetImporter(self.db).import_file(dataset='fractracker_us_data_centers', input_path=path, confirm=True)
        audits = list(self.db.scalars(select(ImportedDatasetRow).order_by(ImportedDatasetRow.row_number.desc())))
        for i, audit in enumerate(audits):
            # Physical insertion order differs from the documented preview order.
            audit.created_at = datetime(2026, 1, 1) + timedelta(seconds=i)
            audit.duplicate_status = 'distinct'
        self.db.commit()
        before = self.snapshot()
        flags = dict(dataset='fractracker_us_data_centers', only_mappable=True, include_row_details=True)
        whole = backfill_candidates(self.db, offset=5, limit=25, **flags).to_dict()
        pieces = [backfill_candidates(self.db, offset=i, limit=5, **flags).to_dict() for i in range(5, 30, 5)]
        count_fields = [k for k, v in whole.items() if isinstance(v, int) and not isinstance(v, bool) and k != 'offset']
        for key in count_fields:
            self.assertEqual(whole[key], sum(p[key] for p in pieces), key)
        details = [row for p in pieces for row in p['row_details']]
        self.assertEqual(whole['row_details'], details)
        self.assertEqual([row['audit_row_id'] for row in details], [str(a.id) for a in audits[5:]])
        self.assertEqual(whole, backfill_candidates(self.db, offset=5, limit=25, **flags).to_dict())
        self.assertEqual(details[0]['classification'], 'possible_duplicate')
        self.assertEqual(details[0]['matched_audit_row_id'], str(audits[0].id))
        self.assertEqual(details[13]['classification'], 'existing_candidate_duplicate')
        self.assertEqual(details[13]['matched_audit_row_id'], str(audits[9].id))
        self.assertTrue(any(d['classification'] == 'would_create_candidate' for d in details))
        self.assertTrue(all('raw_row' not in d and 'normalized_row' not in d for d in details))
        self.assertEqual(self.snapshot(), before)
        self.assert_only_import_tables()
        for key in ('created_projects', 'created_evidence', 'created_candidates', 'created_candidate_links'):
            self.assertEqual(whole[key], 0)
        self.assertEqual(backfill_candidates(self.db, offset=100, limit=5, **flags).row_details, [])
        self.assertEqual(backfill_candidates(self.db, offset=5, limit=0, **flags).row_details, [])

    def test_details_rejected_before_confirm_can_write(self):
        self.seed()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'requires dry-run'):
            self.backfill(confirm=True, include_row_details=True)
        self.assertEqual(self.snapshot(), before)
        args = [sys.executable, 'scripts/backfill_baseline_candidates.py', '--dataset',
                'epoch_ai_data_centers', '--include-row-details']
        env = {**os.environ, 'DATABASE_URL': f'sqlite:///{self.database}'}
        raw_before = self.database.read_bytes()
        result = subprocess.run(args + ['--confirm'], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--include-row-details requires --dry-run', result.stderr)
        result = subprocess.run(args + ['--dry-run'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        import json
        self.assertEqual(json.loads(result.stdout)['row_details'][0]['classification'], 'would_create_candidate')
        self.assertEqual(raw_before, self.database.read_bytes())
        self.assertNotIn('row_details', self.backfill().to_dict())
