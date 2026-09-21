import unittest
from sqlalchemy import select, func
from app.models import Base
from app.models.project import Project
from app.models.evidence import Evidence
from app.models.imported_dataset import ImportedDatasetRun, ImportedDatasetRow, ImportedCandidateLink
from app.services.project_candidate_promotion import ProjectCandidatePromotionService
from tests import test_project_candidate_promotion as fixtures


class PromotionCoordinatesTest(unittest.TestCase):
    setUp = fixtures.ProjectCandidatePromotionTest.setUp
    tearDown = fixtures.ProjectCandidatePromotionTest.tearDown
    _candidate = fixtures.ProjectCandidatePromotionTest._candidate

    def seed(self, db, metadata, row_metadata=None, link_type='project_candidate'):
        candidate = self._candidate(raw_metadata_json=metadata, confidence=0.45)
        db.add(candidate)
        db.flush()
        if row_metadata is not None:
            run = ImportedDatasetRun(dataset_name='fractracker_us_data_centers', source_file='fixture.csv', dry_run=False)
            db.add(run); db.flush()
            row = ImportedDatasetRow(run_id=run.id, dataset_name=run.dataset_name,
                source_file=run.source_file, row_number=1, normalized_row_json=row_metadata)
            db.add(row); db.flush()
            db.add(ImportedCandidateLink(imported_row_id=row.id, linked_record_type=link_type,
                linked_record_id=candidate.id, duplicate_status='distinct'))
        db.commit()
        return candidate

    def snapshot(self, db):
        return {t.name:list(db.execute(select(t))) for t in Base.metadata.sorted_tables}

    def test_linked_row_coordinates_provenance_and_idempotency(self):
        with self.SessionLocal() as db:
            c = self.seed(db, {}, {'latitude':'28.6146','longitude':'-81.3857'})
            before = self.snapshot(db)
            service = ProjectCandidatePromotionService(db)
            self.assertTrue(service.promote(c.id).would_promote)
            self.assertEqual(before, self.snapshot(db))
            result = service.promote(c.id, confirm=True)
            db.commit()
            p = db.get(Project, c.promoted_project_id)
            self.assertEqual((p.latitude,p.longitude), (28.6146,-81.3857))
            self.assertEqual(p.coordinate_status,'unverified')
            self.assertEqual(p.coordinate_precision,'source_row')
            self.assertEqual(p.coordinate_source,'baseline_imported_dataset_row')
            self.assertEqual(p.coordinate_source_url,c.primary_source_url)
            self.assertEqual(p.coordinate_confidence,0.45)
            self.assertIsNotNone(p.coordinate_updated_at)
            self.assertIsNone(p.coordinate_verified_at)
            self.assertIn('imported audit row',p.coordinate_notes)
            self.assertTrue(result.promoted)
            self.assertEqual(c.status,'promoted')
            self.assertEqual(db.scalar(select(func.count()).select_from(Project)),1)
            self.assertEqual(db.scalar(select(func.count()).select_from(Evidence)),1)
            after = self.snapshot(db)
            for name in before:
                if name not in {'projects','project_candidates','evidence','field_provenance'}:
                    self.assertEqual(before[name],after[name],name)
            service.promote(c.id, confirm=True)
            db.commit()
            self.assertEqual(after,self.snapshot(db))

    def test_explicit_candidate_coordinates_win(self):
        with self.SessionLocal() as db:
            c = self.seed(db, {'normalized_row':{'latitude':0,'longitude':180}}, {'latitude':38,'longitude':-120})
            ProjectCandidatePromotionService(db).promote(c.id, confirm=True)
            p=db.get(Project,c.promoted_project_id)
            self.assertEqual((p.latitude,p.longitude),(0,180))
            self.assertEqual(p.coordinate_source,'candidate_metadata')

    def test_invalid_candidate_pair_falls_back_to_linked_row(self):
        with self.SessionLocal() as db:
            c=self.seed(db, {'latitude':True,'longitude':-120}, {'latitude':38.277733,'longitude':-120.91554})
            ProjectCandidatePromotionService(db).promote(c.id, confirm=True)
            p=db.get(Project,c.promoted_project_id)
            self.assertEqual((p.latitude,p.longitude),(38.277733,-120.91554))

    def test_invalid_or_missing_pairs_do_not_block_promotion(self):
        for value in ({}, {'latitude':91,'longitude':0}, {'latitude':0,'longitude':181},
                      {'latitude':'NaN','longitude':0}, {'latitude':'Infinity','longitude':0},
                      {'latitude':True,'longitude':0}, {'latitude':3}, {'latitude':{},'longitude':0}):
            with self.subTest(value=value), self.SessionLocal() as db:
                c=self.seed(db,value,value)
                self.assertTrue(ProjectCandidatePromotionService(db).promote(c.id,confirm=True).promoted)
                p=db.get(Project,c.promoted_project_id)
                self.assertIsNone(p.latitude);self.assertIsNone(p.longitude)
                self.assertIsNone(p.coordinate_updated_at);self.assertIsNone(p.coordinate_verified_at)
                # Keep every case isolated while preserving fixture audit setup.
                db.rollback()
                for t in reversed(Base.metadata.sorted_tables):
                    db.execute(t.delete())
                db.commit()

    def test_wrong_link_type_is_not_coordinate_source(self):
        with self.SessionLocal() as db:
            c=self.seed(db,{}, {'latitude':38,'longitude':-120}, link_type='project')
            ProjectCandidatePromotionService(db).promote(c.id,confirm=True)
            self.assertIsNone(db.get(Project,c.promoted_project_id).latitude)

    def test_existing_project_coordinates_are_not_overwritten(self):
        from app.services.project_candidate_promotion import build_project
        with self.SessionLocal() as db:
            c=self.seed(db, {'latitude':38,'longitude':-120})
            p=build_project(c)
            p.latitude,p.longitude=39,-121
            p.coordinate_status='verified'
            db.add(p);db.commit()
            result=ProjectCandidatePromotionService(db).promote(c.id,confirm=True)
            self.assertTrue(result.project_updated)
            self.assertEqual((p.latitude,p.longitude),(39,-121))
            self.assertEqual(p.coordinate_status,'verified')
