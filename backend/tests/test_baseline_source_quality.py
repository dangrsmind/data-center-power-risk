import unittest
from sqlalchemy import select
from app.models.imported_dataset import ImportedDatasetRun, ImportedDatasetRow
from app.services.baseline_candidate_backfill import backfill_candidates
from app.services.baseline_source_quality import classify_source_and_candidate
from tests import test_baseline_candidate_backfill as fixtures


class SourceQualityTest(unittest.TestCase):
    setUp = fixtures.BackfillTest.setUp
    tearDown = fixtures.BackfillTest.tearDown
    snapshot = fixtures.BackfillTest.snapshot
    assert_only_import_tables = fixtures.BackfillTest.assert_only_import_tables

    def preview(self, url, **fields):
        run = ImportedDatasetRun(dataset_name='fractracker_us_data_centers', source_file='fixture.csv', dry_run=False)
        self.db.add(run)
        self.db.flush()
        row = ImportedDatasetRow(run_id=run.id, dataset_name=run.dataset_name, source_file=run.source_file,
            row_number=2, duplicate_status='distinct', raw_row_json={'original': 'preserved', 'source_url': url,
                          'primary_source_title': str(fields.get('name', 'Example campus')) + ' proposed data center'},
            normalized_row_json={'name': 'Example campus', 'dataset_row_type': 'data_center',
                                 'latitude': 39, 'longitude': -77, **fields},
            source_urls_json=[url] if url else [], warnings_json=[], errors_json=[])
        self.db.add(row)
        self.db.commit()
        before = self.snapshot()
        result = backfill_candidates(self.db, dataset=run.dataset_name, import_run_id=str(run.id),
                                     only_mappable=True, include_row_details=True)
        self.assertEqual(self.snapshot(), before)
        self.assert_only_import_tables()
        self.assertEqual(result.created_candidates, 0)
        self.assertEqual(result.created_candidate_links, 0)
        self.assertEqual(result.created_projects, 0)
        self.assertEqual(result.created_evidence, 0)
        return result, result.row_details[0]

    def test_social_group_is_blocked_even_with_proposed_status(self):
        result, row = self.preview('https://www.facebook.com/groups/123/', lifecycle_state='Proposed')
        self.assertEqual(result.would_create_candidates, 0)
        self.assertEqual(result.rows_skipped_weak_source_quality, 1)
        self.assertEqual(row['source_quality'], 'social_media_or_group')
        self.assertFalse(row['source_quality_allows_candidate_creation'])
        self.assertEqual(row['classification'], 'weak_source_quality')
        self.assertIn('social-media', row['reason'])

    def test_official_operating_facility_is_not_a_build(self):
        result, row = self.preview('https://www.expedient.com/data-centers/phoenix/', lifecycle_state='Operating')
        self.assertEqual(result.rows_skipped_ambiguous_candidate_type, 1)
        self.assertEqual(row['source_quality'], 'official_project_or_operator')
        self.assertTrue(row['source_quality_allows_candidate_creation'])
        self.assertEqual(row['candidate_type'], 'operating_facility_or_colocation_page')
        self.assertFalse(row['candidate_type_allows_candidate_creation'])
        self.assertEqual(row['classification'], 'ambiguous_candidate_type')

    def test_broad_report_is_blocked_despite_row_proposal(self):
        result, row = self.preview('https://www.datacenterwatch.org/report', lifecycle_state='Proposed')
        self.assertEqual(result.rows_skipped_weak_source_quality, 1)
        self.assertEqual(row['source_quality'], 'broad_report_or_index')
        self.assertEqual(row['candidate_type'], 'broad_market_or_report_reference')
        self.assertIn('not project-specific', row['reason'])

    def test_credible_project_article_can_remain_eligible(self):
        result, row = self.preview('https://www.datacenterdynamics.com/en/news/proposed-data-center-scaled-down-near-san-francisco/')
        self.assertEqual(result.would_create_candidates, 1)
        self.assertEqual(row['source_quality'], 'credible_news_article')
        self.assertEqual(row['candidate_type'], 'project_specific_build_or_expansion')
        self.assertTrue(row['source_quality_allows_candidate_creation'])
        self.assertTrue(row['candidate_type_allows_candidate_creation'])
        self.assertEqual(row['classification'], 'would_create_candidate')

    def test_programmatic_article_is_blocked(self):
        result, row = self.preview('https://www.datacenterdynamics.com/en/news/air-force-accepting-proposals-for-data-centers-in-military-bases/', lifecycle_state='Proposed')
        self.assertEqual(result.rows_skipped_ambiguous_candidate_type, 1)
        self.assertEqual(row['candidate_type'], 'programmatic_solicitation_or_policy')

    def test_alternative_source_does_not_silently_replace_primary(self):
        result, row = self.preview('https://facebook.com/groups/123', lifecycle_state='Proposed')
        audit = self.db.scalar(select(ImportedDatasetRow))
        audit.source_urls_json = [*audit.source_urls_json, 'https://www.datacenterdynamics.com/en/news/proposed-campus/']
        self.db.commit()
        result = backfill_candidates(self.db, dataset='fractracker_us_data_centers', include_row_details=True,
                                     include_possible_duplicates=True)
        self.assertEqual(result.would_create_candidates, 0)
        self.assertEqual(result.row_details[0]['classification'], 'weak_source_quality')
        self.assertEqual(result.row_details[0]['public_source_url'], 'https://facebook.com/groups/123')

    def test_offline_categories_unknown_hosts_and_expansion_signals(self):
        cases = [
            ('https://maranaaz.gov/documents/proposed-campus.pdf', {}, 'government_or_regulatory', True),
            ('https://tract.com/news/new-campus/', {'lifecycle_state': 'Under construction'}, 'official_project_or_operator', True),
            ('https://expedient.com/data-centers/phoenix/', {'notes': 'Expansion proposed'}, 'official_project_or_operator', True),
            ('https://expedient.com/data-centers/phoenix-building-1/', {'name': 'Building 1', 'lifecycle_state': 'Operating'}, 'official_project_or_operator', False),
            ('https://expedient.com/data-centers/phoenix/', {'notes': 'No expansion planned'}, 'official_project_or_operator', False),
            ('https://datacenterwatch.org/specific-campus-report', {'lifecycle_state': 'Proposed'}, 'advocacy_or_watchdog_report', False),
            ('https://datacenterdynamics.com.attacker.example/en/news/proposed-campus/', {}, 'unknown', False),
            ('https://unknown.example/proposed-campus/', {}, 'unknown', False),
            ('https://reddit.com/r/example/comments/123', {}, 'social_media_or_group', False),
            ('https://datacenterdynamics.com/en/news/', {}, 'broad_report_or_index', False),
            (None, {'lifecycle_state': 'Proposed'}, 'unknown', False),
        ]
        for url, normalized, category, allowed in cases:
            with self.subTest(url=url):
                result = classify_source_and_candidate(url, normalized)
                self.assertEqual(result['source_quality'], category)
                self.assertEqual(result['source_quality_allows_candidate_creation'] and result['candidate_type_allows_candidate_creation'], allowed)

    def test_quality_blocked_rows_keep_duplicate_context_across_pages(self):
        self.preview('https://facebook.com/groups/123', lifecycle_state='Proposed')
        self.preview('https://datacenterdynamics.com/en/news/proposed-campus/', lifecycle_state='Proposed')
        from datetime import datetime
        for audit in self.db.scalars(select(ImportedDatasetRow)):
            audit.created_at = datetime(2026, 1, 1 if 'facebook.com' in audit.source_urls_json[0] else 2)
        self.db.commit()
        flags = dict(dataset='fractracker_us_data_centers', include_row_details=True)
        before = self.snapshot()
        whole = backfill_candidates(self.db, limit=2, **flags)
        first = backfill_candidates(self.db, limit=1, **flags)
        second = backfill_candidates(self.db, offset=1, limit=1, **flags)
        self.assertEqual(whole.would_create_candidates, 0)
        self.assertEqual(whole.rows_skipped_weak_source_quality, 1)
        self.assertEqual(whole.rows_skipped_possible_duplicate, 1)
        self.assertEqual(whole.row_details, first.row_details + second.row_details)
        self.assertEqual(second.row_details[0]['matched_audit_row_id'], first.row_details[0]['audit_row_id'])
        self.assertEqual(self.snapshot(), before)
