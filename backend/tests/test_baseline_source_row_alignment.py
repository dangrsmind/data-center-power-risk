import unittest
from datetime import datetime, timedelta
from app.services.baseline_source_row_alignment import classify_source_row_alignment
from app.services.baseline_candidate_backfill import backfill_candidates
from app.models.imported_dataset import ImportedDatasetRow, ImportedDatasetRun
from tests import test_baseline_source_quality as fixtures


class AlignmentTest(unittest.TestCase):
    setUp = fixtures.SourceQualityTest.setUp
    tearDown = fixtures.SourceQualityTest.tearDown
    snapshot = fixtures.SourceQualityTest.snapshot
    assert_only_import_tables = fixtures.SourceQualityTest.assert_only_import_tables

    def preview(self, name, city, state, slug, **extra):
        url = 'https://www.datacenterdynamics.com/en/news/' + slug + '/'
        run = ImportedDatasetRun(dataset_name='fractracker_us_data_centers', source_file='fixture.csv', dry_run=False)
        self.db.add(run)
        self.db.flush()
        self.fixture_sequence = getattr(self, 'fixture_sequence', 0) + 1
        self.db.add(ImportedDatasetRow(created_at=datetime(2026, 1, 1) + timedelta(seconds=self.fixture_sequence), run_id=run.id, dataset_name=run.dataset_name, source_file=run.source_file,
            row_number=2, duplicate_status='distinct', raw_row_json={'name': name}, source_urls_json=[url],
            normalized_row_json={'name':name,'city':city,'state':state,'latitude':39,'longitude':-77,
                                 'lifecycle_state':'Proposed','dataset_row_type':'data_center', **extra}))
        self.db.commit()
        before = self.snapshot()
        result = backfill_candidates(self.db, dataset=run.dataset_name, import_run_id=str(run.id),
                                     only_mappable=True, include_row_details=True)
        self.assertEqual(self.snapshot(), before)
        self.assert_only_import_tables()
        for field in ('created_candidates','created_projects','created_evidence','created_candidate_links'):
            self.assertEqual(getattr(result, field), 0)
        return result, result.row_details[0]

    def test_state_mismatch_blocks_even_matching_operator(self):
        for name, city, state, slug in [
            ('Cielo Digital Infrastructure','Hudson','CO','cielo-digital-infrastructure-plans-campus-in-south-carolina'),
            ('GotSpace','Bozrah','CT','data-center-campus-proposed-in-pennsylvania'),
        ]:
            result, row = self.preview(name,city,state,slug)
            self.assertEqual(result.would_create_candidates, 0)
            self.assertEqual(result.rows_skipped_source_row_alignment, 1)
            self.assertEqual(row['source_row_alignment'], 'geography_mismatch')
            self.assertFalse(row['source_row_alignment_allows_candidate_creation'])
            self.assertTrue(row['source_row_alignment_reasons'])

    def test_platform_and_rejection_are_blocked(self):
        result, row = self.preview('H5 Data Center','Tampa','FL','h5-and-novacap-launch-platform-acquire-three-carrier-hotels')
        self.assertEqual(result.would_create_candidates, 0)
        self.assertEqual(row['classification'], 'broad_transaction_or_platform_article')
        for phrase, stage in [('officials-fail-to-back-plans','unknown'), ('scrapped','cancelled'),
                              ('cancelled','cancelled'), ('rejected','unknown'), ('withdrawn','cancelled')]:
            result, row = self.preview('Project Jarvis','Fort Pierce','FL',phrase+'-for-data-center-in-florida')
            self.assertEqual(result.rows_skipped_source_row_alignment, 1)
            self.assertEqual(row['source_row_alignment'], 'cancelled_or_rejected_project')
            self.assertEqual(row['lifecycle_stage'], stage)
            self.assertIn(row['candidate_purpose'], {'supporting_context','permitting_or_policy_signal'})
            self.assertEqual(result.taxonomy_summary['lifecycle_stage_counts'], {stage:1})

    def test_aligned_state_and_site_conversion_remain_eligible(self):
        cases = [
            ('Guadalupe Quarry Redevelopment Project Data Center','Brisbane','CA','proposed-data-center-scaled-down-near-san-francisco-california','weakly_aligned'),
            ('Buena Vista Biomass Power site Data Center','Ione','CA','newyork-greencloud-acquires-californian-biomass-facility-for-carbon-negative-ai-data-center','aligned'),
            ('Example Campus','Denver','CO','example-campus-plans-expansion-in-denver-colorado','aligned'),
        ]
        for name,city,state,slug,category in cases:
            result, row = self.preview(name,city,state,slug)
            self.assertEqual(result.would_create_candidates, 1)
            self.assertEqual(row['source_row_alignment'], category)
            self.assertTrue(row['source_row_alignment_allows_candidate_creation'])

    def test_title_city_mismatch_bound_titles_and_unknown_alignment(self):
        n={'name':'Example Campus','city':'Denver','state':'CO'}
        url='https://datacenterdynamics.com/en/news/proposed-campus/'
        raw={'primary_source_title':'New proposed campus in Boston'}
        result=classify_source_row_alignment(n,[url],raw,known_cities={'Denver','Boston'})
        self.assertEqual(result['source_row_alignment'],'geography_mismatch')
        # An unbound secondary title cannot override primary-source geography.
        urls=['https://datacenterdynamics.com/en/news/proposed-campus-in-pennsylvania/', url]
        result=classify_source_row_alignment(n,urls,{'source_title':'Example Campus proposed in Denver Colorado'})
        self.assertEqual(result['source_row_alignment'],'geography_mismatch')
        result=classify_source_row_alignment(n,[url])
        self.assertEqual(result['source_row_alignment'],'insufficient_source_row_alignment')
        result=classify_source_row_alignment(n,[])
        self.assertEqual(result['source_row_alignment'],'unknown')
        result=classify_source_row_alignment(n,[url],{'primary_source_facility_name':'Unrelated Facility'})
        self.assertEqual(result['source_row_alignment'],'facility_or_operator_mismatch')

    def test_explicit_matching_state_exception_and_title_alignment(self):
        n={'name':'Example Campus','city':'Brisbane','state':'CA'}
        url='https://datacenterdynamics.com/en/news/proposed-campus-near-san-francisco-california/'
        self.assertTrue(classify_source_row_alignment(n,[url],known_cities={'San Francisco','Brisbane'})['source_row_alignment_allows_candidate_creation'])
        url='https://datacenterdynamics.com/en/news/article-123/'
        self.assertTrue(classify_source_row_alignment(n,[url],{'primary_source_title':'Example Campus plans expansion in Brisbane California'})['source_row_alignment_allows_candidate_creation'])

    def test_alignment_blocked_prefix_retains_duplicate_context_across_pages(self):
        self.preview('Cielo Digital Infrastructure', 'Hudson', 'CO',
                     'cielo-plans-campus-in-south-carolina')
        self.preview('Cielo Digital Infrastructure', 'Hudson', 'CO',
                     'cielo-plans-campus-in-hudson-colorado')
        before = self.snapshot()
        kwargs = dict(dataset='fractracker_us_data_centers', only_mappable=True,
                      include_row_details=True)
        full = backfill_candidates(self.db, **kwargs)
        first = backfill_candidates(self.db, offset=0, limit=1, **kwargs)
        second = backfill_candidates(self.db, offset=1, limit=1, **kwargs)
        self.assertEqual(full.row_details, first.row_details + second.row_details)
        self.assertEqual(full.rows_skipped_source_row_alignment, 1)
        self.assertEqual(full.would_create_candidates, 0)
        self.assertEqual(second.would_create_candidates, 0)
        self.assertNotEqual(second.row_details[0]['classification'], 'would_create_candidate')
        self.assertEqual(self.snapshot(), before)
        self.assert_only_import_tables()
