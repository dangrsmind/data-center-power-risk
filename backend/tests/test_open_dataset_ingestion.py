import json
import os
import subprocess
import sys
import unittest
from dataclasses import replace
from unittest.mock import patch
from sqlalchemy import select,func,event,text
from app.models.project import Project
from app.models.project_candidate import ProjectCandidate
from app.models.imported_dataset import ImportedDatasetRow,ImportedDatasetRun,ImportedCandidateLink
from app.services.open_dataset_ingestion import ingest_open_dataset
from app.services.open_dataset_registry import REGISTRY,DECISIONS
from tests import test_baseline_candidate_backfill as fixtures

class OpenDatasetTest(unittest.TestCase):
    def setUp(self):
        fixtures.BackfillTest.setUp(self)
        self.db.execute(text("PRAGMA foreign_keys=ON"))
        self.db.commit()
    tearDown=fixtures.BackfillTest.tearDown
    csv=fixtures.BackfillTest.csv
    snapshot=fixtures.BackfillTest.snapshot

    def row(self,name='Alpha',**extra):
        return {'Name':name+' Data Center','Country':'US','city':'Denver','state':'CO','latitude':'39',
            'longitude':'-105','status':'Proposed','Selected Sources':f'https://www.equinix.com/news/{name.lower()}-data-center-proposed-in-denver-colorado',**extra}

    def run_ingest(self,rows=None,**kwargs):
        path=self.csv(rows or [self.row()],name='data_centers.csv')
        return ingest_open_dataset(self.db,dataset='epoch_ai_data_centers',inputs=[path],**kwargs)

    def test_dry_run_reports_auto_lane_without_writes(self):
        before=self.snapshot()
        result=self.run_ingest(include_row_details=True)
        self.assertEqual(result['would_create_projects'],1,result['top_examples'])
        self.assertEqual(result['would_write_rows'],4)
        self.assertEqual(before,self.snapshot())
        self.assertEqual(set(result['decisions_by_type']),set(DECISIONS))
        self.assertGreaterEqual(result['row_details'][0]['overall_confidence'],.85)

    def test_caps_required_and_overflow_issue_no_insert(self):
        before=self.snapshot();writes=[]
        def capture(conn,cursor,statement,parameters,context,executemany):
            if statement.lstrip().split()[0].upper() in {'INSERT','UPDATE','DELETE'}: writes.append(statement)
        event.listen(self.engine,'before_cursor_execute',capture)
        try:
            for caps in ({},{'max_create_projects':0,'max_create_candidates':0,'max_write_rows':10},
                         {'max_create_projects':1,'max_create_candidates':0,'max_write_rows':3}):
                with self.assertRaises(ValueError):self.run_ingest(confirm=True,**caps)
        finally:event.remove(self.engine,'before_cursor_execute',capture)
        self.assertEqual(writes,[]);self.assertEqual(before,self.snapshot())

    def test_confirm_project_provenance_idempotency_and_no_evidence(self):
        result=self.run_ingest(confirm=True,max_create_projects=1,max_create_candidates=0,max_write_rows=4)
        self.assertEqual(result['created_projects'],1)
        project=self.db.scalar(select(Project));metadata=project.candidate_metadata_json
        self.assertEqual((project.latitude,project.longitude),(39,-105))
        self.assertEqual(project.coordinate_status,'unverified');self.assertIsNone(project.coordinate_verified_at)
        self.assertEqual(project.coordinate_precision,'source_row')
        self.assertEqual(metadata['automated_ingestion']['decision'],'auto_create_project')
        self.assertTrue(metadata['automated_ingestion']['source_row_hash'])
        self.assertEqual(self.db.scalar(select(ImportedCandidateLink)).linked_record_id,project.id)
        before=self.snapshot()
        result=self.run_ingest(confirm=True,max_create_projects=0,max_create_candidates=0,max_write_rows=0)
        self.assertEqual(result['would_skip_duplicates'],1)
        self.assertEqual(result['written_rows'],0);self.assertEqual(before,self.snapshot())
        self.assert_empty_except({'projects','imported_dataset_runs','imported_dataset_rows','imported_candidate_links'})

    def assert_empty_except(self,allowed):
        from app.models import Base
        for t in Base.metadata.sorted_tables:
            if t.name not in allowed:self.assertEqual(self.db.scalar(select(func.count()).select_from(t)),0,t.name)

    def test_medium_candidate_with_missing_coordinates_and_no_verification(self):
        result=self.run_ingest([self.row(latitude='',longitude='',**{'Selected Sources':'https://www.datacenterdynamics.com/en/news/alpha-data-center-proposed-in-denver-colorado/'})],
            confirm=True,max_create_projects=0,max_create_candidates=1,max_write_rows=4)
        self.assertEqual(result['created_project_candidates'],1,result['top_examples'])
        c=self.db.scalar(select(ProjectCandidate));self.assertEqual(c.status,'needs_review')
        self.assertIsNone(c.verification_status);self.assertFalse(c.auto_admit_eligible);self.assertIsNone(c.promoted_project_id)
        self.assertGreaterEqual(c.confidence,.60);self.assertLess(c.confidence,.85)
        self.assert_empty_except({'project_candidates','imported_dataset_runs','imported_dataset_rows','imported_candidate_links'})

    def test_context_files_and_operating_facility_never_projects(self):
        for filename in ('data_center_chillers.csv','data_center_cooling_towers.csv','data_center_timelines.csv'):
            path=self.csv([{'Name':filename,'Country':'US'}],name=filename)
            result=ingest_open_dataset(self.db,dataset='epoch_ai_data_centers',inputs=[path])
            self.assertEqual(result['would_create_context_records'],1)
        result=self.run_ingest([self.row(status='Operating',**{'Selected Sources':'https://www.equinix.com/facilities/denver'})],confirm=True,
            max_create_projects=0,max_create_candidates=0,max_write_rows=2)
        self.assertEqual(result['would_create_context_records'],1)
        self.assertEqual(self.db.scalar(select(ImportedDatasetRow)).normalized_row_json['automated_ingestion']['decision'],'create_context_record_only')
        self.assert_empty_except({'imported_dataset_runs','imported_dataset_rows'})

    def test_invalid_coordinates_geography_weak_sources_and_cancellation(self):
        for extra,lane in [({'latitude':'91'},'exception_review'),({'latitude':'NaN'},'exception_review'),
                           ({'state':'VA'},'exception_review'),({'status':'Unknown'},'exception_review'),
                           ({'Selected Sources':'https://facebook.com/groups/alpha'},'exception_review'),
                           ({'status':'Cancelled'},'reject_or_ignore')]:
            result=self.run_ingest([self.row(**extra)])
            self.assertEqual(result['decisions_by_type'][lane],1,result['top_examples'])
            self.assertEqual(result['would_create_projects'],0)

    def test_registry_policy_and_no_provenance(self):
        policy=REGISTRY['epoch_ai_data_centers']
        with patch.dict(REGISTRY,{'epoch_ai_data_centers':replace(policy,auto_project_allowed=False)}):
            self.assertEqual(self.run_ingest()['would_create_project_candidates'],1)
        with patch.dict(REGISTRY,{'epoch_ai_data_centers':replace(policy,canonical_source_url=None)}):
            result=self.run_ingest([self.row(**{'Selected Sources':''})],confirm=True,max_create_projects=0,max_create_candidates=0,max_write_rows=0)
            self.assertEqual(result['would_reject_or_ignore'],1);self.assertEqual(result['written_rows'],0)

    def test_existing_candidate_and_project_are_not_duplicated(self):
        for model in (Project,ProjectCandidate):
            with self.subTest(model=model):
                if model==Project: entity=model(canonical_name='Alpha Data Center',state='CO',latitude=39,longitude=-105,lifecycle_state='candidate_unverified')
                else: entity=model(candidate_key='existing',candidate_name='Alpha Data Center',state='CO',status='needs_review',confidence=.5,source_count=1,claim_count=0,primary_source_url=self.row()['Selected Sources'])
                self.db.add(entity);self.db.commit()
                result=self.run_ingest()
                self.assertEqual(result['would_create_projects'],0)
                self.assertEqual(result['would_create_project_candidates'],0)
                self.assertEqual(result['would_skip_duplicates']+result['would_exception_review'],1)
                self.db.delete(entity);self.db.commit()

    def test_cli_defaults_read_only_and_requires_caps(self):
        path=self.csv([self.row()],name='data_centers.csv');before=self.database.read_bytes()
        args=[sys.executable,'scripts/ingest_open_datasets.py','--dataset','epoch_ai_data_centers','--input',str(path)]
        env={**os.environ,'DATABASE_URL':f'sqlite:///{self.database}'}
        result=subprocess.run(args,env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(json.loads(result.stdout)['dry_run'])
        result=subprocess.run(args+['--confirm'],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertEqual(before,self.database.read_bytes())

    def test_candidate_cap_overflow_and_exception_audit_receipt(self):
        row=self.row(latitude='',longitude='',**{'Selected Sources':'https://www.datacenterdynamics.com/en/news/alpha-data-center-proposed-in-denver-colorado/'})
        before=self.snapshot()
        with self.assertRaises(ValueError):
            self.run_ingest([row],confirm=True,max_create_projects=0,max_create_candidates=0,max_write_rows=10)
        self.assertEqual(before,self.snapshot())
        result=self.run_ingest([self.row(latitude='91')],confirm=True,max_create_projects=0,max_create_candidates=0,max_write_rows=2)
        self.assertEqual(result['would_exception_review'],1)
        audit=self.db.scalar(select(ImportedDatasetRow))
        decision=audit.normalized_row_json['automated_ingestion']
        self.assertEqual(decision['decision'],'exception_review')
        for key in ('source_trust_score','identity_score','location_score','coordinate_score','lifecycle_score',
                    'source_specificity_score','duplicate_risk_score','conflict_score','overall_confidence',
                    'normalized_identity_key','normalized_location_key','source_row_hash','decision_reasons'):
            self.assertIn(key,decision)
        self.assert_empty_except({'imported_dataset_runs','imported_dataset_rows'})

    def test_batch_duplicates_and_repeat_context_are_idempotent(self):
        result=self.run_ingest([self.row(),self.row()],confirm=True,max_create_projects=1,max_create_candidates=0,max_write_rows=4)
        self.assertEqual(result['would_skip_duplicates'],1)
        self.assertEqual(result['created_projects'],1)
        before=self.snapshot()
        result=self.run_ingest([self.row(),self.row()],confirm=True,max_create_projects=0,max_create_candidates=0,max_write_rows=0)
        self.assertEqual(result['would_skip_duplicates'],2);self.assertEqual(before,self.snapshot())

    def test_late_database_failure_rolls_back_entire_import(self):
        before=self.snapshot()
        def reject_insert(conn,cursor,statement,parameters,context,executemany):
            if statement.startswith('INSERT INTO projects'):
                raise RuntimeError('simulated database failure')
        event.listen(self.engine,'before_cursor_execute',reject_insert)
        try:
            with self.assertRaises(RuntimeError):
                self.run_ingest(confirm=True,max_create_projects=1,max_create_candidates=0,max_write_rows=4)
        finally:event.remove(self.engine,'before_cursor_execute',reject_insert)
        self.assertEqual(before,self.snapshot())

    def test_decisions_are_reproducible(self):
        first=self.run_ingest(include_row_details=True)
        second=self.run_ingest(include_row_details=True)
        self.assertEqual(first,second)

    def test_all_existing_records_are_indexed_not_just_latest_thousand(self):
        self.db.add_all([Project(canonical_name=f'Existing {i}',state='VA',lifecycle_state='candidate_unverified') for i in range(1001)])
        self.db.commit()
        result=self.run_ingest([self.row(Name='Existing 0',state='VA',city='Richmond',**{'Selected Sources':'https://www.equinix.com/news/existing-0-proposed-campus-in-richmond-virginia'})])
        self.assertEqual(result['would_create_projects'],0)
        self.assertEqual(result['would_exception_review'],1)

    def test_synthetic_smoke_fixture_covers_all_six_lanes(self):
        from pathlib import Path
        result=ingest_open_dataset(self.db,dataset='epoch_ai_data_centers',
            inputs=[Path('tests/fixtures/open_dataset/data_centers.csv')])
        self.assertEqual(result['decisions_by_type'],{k:1 for k in DECISIONS})
