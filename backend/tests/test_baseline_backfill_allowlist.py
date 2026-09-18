import json
import os
import subprocess
import sys
import unittest
import uuid
from sqlalchemy import select, event
from app.models.imported_dataset import ImportedDatasetRow
from app.models.project_candidate import ProjectCandidate
from app.services.baseline_candidate_backfill import backfill_candidates
from tests import test_baseline_candidate_backfill as fixtures


class AllowlistTest(unittest.TestCase):
    setUp = fixtures.BackfillTest.setUp
    tearDown = fixtures.BackfillTest.tearDown
    csv = fixtures.BackfillTest.csv
    sample = fixtures.BackfillTest.sample
    run_import = fixtures.BackfillTest.run_import
    snapshot = fixtures.BackfillTest.snapshot
    assert_only_import_tables = fixtures.BackfillTest.assert_only_import_tables

    def seed(self):
        self.run_import([self.sample(Name=name, Owner=name, **{'Current power (MW)': '', 'Selected Sources':
            f'https://www.datacenterdynamics.com/en/news/{name.lower()}-proposed-campus/'})
            for name in ('Alpha', 'Bravo', 'Charlie')], confirm=True)
        self.db.commit()
        return list(self.db.scalars(select(ImportedDatasetRow).order_by(ImportedDatasetRow.row_number)))

    def backfill(self, **kwargs):
        return backfill_candidates(self.db, dataset='epoch_ai_data_centers', **kwargs)

    def test_single_multiple_repeated_and_cap_preview(self):
        rows = self.seed()
        before = self.snapshot()
        for selected in ([rows[0]], [rows[0], rows[2]], [rows[1], rows[1]]):
            result = self.backfill(audit_row_ids=[str(r.id) for r in selected],
                                   max_create_candidates=1, include_row_details=True)
            count = len({r.id for r in selected})
            self.assertEqual(result.rows_checked, count)
            self.assertEqual(result.audit_row_id_filter_count, count)
            self.assertEqual(result.would_create_candidates, count)
            self.assertEqual(result.would_create_candidates_within_cap, count <= 1)
            self.assertEqual(result.confirm_safety_ready, count <= 1)
            self.assertEqual({r['audit_row_id'] for r in result.row_details}, {str(r.id) for r in selected})
            for row in result.row_details:
                for key in ('source_quality', 'candidate_type', 'entity_type', 'lifecycle_stage',
                            'source_row_alignment', 'classification', 'reason'):
                    self.assertIn(key, row)
        self.assertFalse(self.backfill().confirm_safety_ready)
        self.assertEqual(before, self.snapshot())

    def test_confirmation_guards_fail_before_writes(self):
        rows = self.seed()
        before = self.snapshot()
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().split()[0].upper() in {'INSERT', 'UPDATE', 'DELETE'}:
                statements.append(statement)
        event.listen(self.engine, 'before_cursor_execute', capture)
        try:
            for kwargs in ({}, {'audit_row_ids':[rows[0].id]}, {'max_create_candidates':1},
                           {'audit_row_ids':[r.id for r in rows], 'max_create_candidates':1}):
                with self.assertRaisesRegex(ValueError, 'created_candidates=0'):
                    self.backfill(confirm=True, **kwargs)
            self.assertEqual(statements, [])
        finally:
            event.remove(self.engine, 'before_cursor_execute', capture)
        self.assertEqual(before, self.snapshot())
        self.assert_only_import_tables()

    def test_confirm_only_selected_candidate_in_isolated_database(self):
        rows = self.seed()
        result = self.backfill(confirm=True, audit_row_ids=[rows[1].id], max_create_candidates=1)
        self.db.commit()
        self.assertEqual(result.created_candidates, 1)
        self.assertEqual(result.created_candidate_links, 1)
        candidate = self.db.scalar(select(ProjectCandidate))
        self.assertEqual(candidate.raw_metadata_json['imported_row_id'], str(rows[1].id))
        self.assert_only_import_tables(candidates=True)
        self.assertEqual(self.backfill(confirm=True, audit_row_ids=[rows[1].id], max_create_candidates=1).created_candidates, 0)

    def test_allowlist_does_not_bypass_quality_alignment_or_duplicate_context(self):
        rows = self.seed()
        rows[0].source_urls_json = ['https://www.facebook.com/groups/123/']
        rows[1].source_urls_json = ['https://www.datacenterdynamics.com/en/news/bravo-proposed-campus-in-pennsylvania/']
        rows[1].normalized_row_json = {**rows[1].normalized_row_json, 'state':'CO'}
        rows[2].normalized_row_json = {**rows[0].normalized_row_json}
        self.db.commit()
        before = self.snapshot()
        for row, expected in [(rows[0], 'weak_source_quality'), (rows[1], 'geography_mismatch'),
                              (rows[2], 'existing_candidate_duplicate')]:
            preview = self.backfill(audit_row_ids=[row.id], max_create_candidates=1, include_row_details=True)
            self.assertEqual(preview.would_create_candidates, 0)
            self.assertEqual(preview.row_details[0]['classification'], expected)
            self.assertEqual(self.backfill(confirm=True, audit_row_ids=[row.id], max_create_candidates=1).created_candidates, 0)
        self.assertEqual(before, self.snapshot())
        self.assert_only_import_tables()

    def test_allowlist_does_not_bypass_candidate_type(self):
        row = self.seed()[0]
        row.source_urls_json = ['https://www.expedient.com/data-centers/phoenix/']
        row.normalized_row_json = {**row.normalized_row_json, 'lifecycle_state':'Operating'}
        self.db.commit()
        before = self.snapshot()
        result = self.backfill(audit_row_ids=[row.id], max_create_candidates=1, include_row_details=True)
        self.assertEqual(result.would_create_candidates, 0)
        self.assertEqual(result.row_details[0]['classification'], 'ambiguous_candidate_type')
        self.assertEqual(self.backfill(confirm=True, audit_row_ids=[row.id], max_create_candidates=1).created_candidates, 0)
        self.assertEqual(before, self.snapshot())

    def test_invalid_ids_scope_and_caps_fail(self):
        rows = self.seed()
        for kwargs in ({'audit_row_ids':['invalid']}, {'audit_row_ids':[uuid.uuid4()]},
                       {'audit_row_ids':[rows[2].id], 'limit':1},
                       {'max_create_candidates':0}, {'max_create_candidates':-1},
                       {'max_create_candidates':1.5}):
            with self.assertRaises(ValueError):
                self.backfill(**kwargs)

    def test_cli_repeated_allowlist_and_rejections(self):
        rows = self.seed()
        before = self.database.read_bytes()
        command = [sys.executable, 'scripts/backfill_baseline_candidates.py', '--dataset', 'epoch_ai_data_centers']
        env = {**os.environ, 'DATABASE_URL':f'sqlite:///{self.database}'}
        selected = ['--audit-row-id', str(rows[0].id), '--audit-row-id', str(rows[2].id)]
        result = subprocess.run(command + ['--dry-run', '--include-row-details', '--max-create-candidates', '1'] + selected,
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['audit_row_id_filter_count'], 2)
        self.assertEqual(data['would_create_candidates'], 2)
        self.assertFalse(data['would_create_candidates_within_cap'])
        for flags in (['--confirm'], ['--confirm', '--max-create-candidates', '1'],
                      ['--confirm'] + selected, ['--confirm', '--max-create-candidates', '1'] + selected,
                      ['--dry-run', '--max-create-candidates', '0'], ['--dry-run', '--audit-row-id', 'invalid']):
            result = subprocess.run(command + flags, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(before, self.database.read_bytes())
