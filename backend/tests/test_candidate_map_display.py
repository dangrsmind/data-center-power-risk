import unittest
from datetime import datetime, timezone
from sqlalchemy import select
from app.api.routes.project_candidates import candidate_coordinates, project_candidate_response
from app.services.project_candidate_generator import ProjectCandidateGenerator
from tests import test_project_candidate_review_decision as fixtures


class CandidateMapDisplayTest(unittest.TestCase):
    setUp = fixtures.ProjectCandidateReviewDecisionTest.setUp
    tearDown = fixtures.ProjectCandidateReviewDecisionTest.tearDown
    candidate = fixtures.ProjectCandidateReviewDecisionTest.candidate

    def test_coordinate_pair_validation(self):
        for value in (None, [], {}, {'latitude':True,'longitude':1}, {'latitude':'NaN','longitude':1},
                      {'latitude':91,'longitude':0}, {'latitude':1,'longitude':181},
                      {'latitude':'','longitude':1}, {'latitude':1}, {'latitude':{},'longitude':1}):
            self.assertEqual(candidate_coordinates(value), (None, None))
        self.assertEqual(candidate_coordinates({'latitude':'0','longitude':'-180'}), (0, -180))
        self.assertEqual(candidate_coordinates({'normalized_row':{'latitude':'38.2','longitude':-120}}), (38.2, -120))
        self.assertEqual(candidate_coordinates({'latitude':38, 'normalized_row':{'longitude':-120}}), (None, None))

    def test_response_is_read_only_and_preserves_metadata_redaction(self):
        with self.SessionLocal() as db:
            c = self.candidate(db, raw_metadata_json={'latitude':38, 'longitude':-120, 'private':'do not expose'},
                               lifecycle_state='dataset_import_needs_review')
            db.commit()
            before = {t.name: list(db.execute(select(t))) for t in c.metadata.sorted_tables}
            response = project_candidate_response(c)
            self.assertEqual((response.latitude,response.longitude), (38,-120))
            self.assertIsNone(response.raw_metadata_json)
            self.assertEqual(response.status, 'needs_review')
            self.assertIsNone(response.promoted_project_id)
            self.assertFalse(db.dirty)
            self.assertEqual(before, {t.name:list(db.execute(select(t))) for t in c.metadata.sorted_tables})

    def test_newest_sort_precedes_limit_without_changing_default(self):
        with self.SessionLocal() as db:
            older = self.candidate(db, candidate_key='older', triage_score=0.9, created_at=datetime(2025,1,1,tzinfo=timezone.utc))
            newer = self.candidate(db, candidate_key='newer', triage_score=0.1, created_at=datetime(2026,1,1,tzinfo=timezone.utc))
            db.commit()
            service = ProjectCandidateGenerator(db)
            self.assertEqual(service.list_candidates(limit=1)[0].id, older.id)
            self.assertEqual(service.list_candidates(limit=1, newest_first=True)[0].id, newer.id)
