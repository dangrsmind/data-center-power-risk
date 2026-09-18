import unittest
from collections import Counter
from app.services.baseline_entity_taxonomy import classify_entity_taxonomy, ENTITY_TYPES, LIFECYCLE_STAGES, CANDIDATE_PURPOSES
from app.services.baseline_source_quality import classify_source_and_candidate
from app.services.baseline_candidate_backfill import backfill_candidates
from tests import test_baseline_source_quality as fixtures


class TaxonomyTest(unittest.TestCase):
    setUp = fixtures.SourceQualityTest.setUp
    tearDown = fixtures.SourceQualityTest.tearDown
    snapshot = fixtures.SourceQualityTest.snapshot
    assert_only_import_tables = fixtures.SourceQualityTest.assert_only_import_tables
    preview = fixtures.SourceQualityTest.preview

    def test_useful_roles_do_not_change_quality_gates(self):
        cases = [
            ('https://expedient.com/data-centers/phoenix/', {'name': 'PHX1', 'lifecycle_state': 'Operating'},
             'data_center_facility', 'existing_operational', 'facility_baseline', 'ambiguous_candidate_type', 0),
            ('https://facebook.com/groups/123', {'name': 'Project Blue Marana', 'lifecycle_state': 'Proposed'},
             'supporting_context', 'unknown', 'supporting_context', 'weak_source_quality', 0),
            ('https://datacenterwatch.org/report', {'name': 'Tract Phoenix Data Center', 'lifecycle_state': 'Under construction'},
             'supporting_context', 'unknown', 'supporting_context', 'weak_source_quality', 0),
            ('https://datacenterdynamics.com/en/news/air-force-accepting-proposals-for-data-centers-in-military-bases/', {'lifecycle_state': 'Proposed'},
             'policy_permitting_case', 'unknown', 'permitting_or_policy_signal', 'ambiguous_candidate_type', 0),
            ('https://datacenterdynamics.com/en/news/proposed-data-center-scaled-down/', {'name': 'Guadalupe Quarry Redevelopment Project Data Center', 'lifecycle_state': 'Proposed'},
             'data_center_project', 'proposed', 'build_review', 'would_create_candidate', 1),
        ]
        for url, fields, entity, stage, purpose, classification, eligible in cases:
            with self.subTest(url=url):
                result, row = self.preview(url, **fields)
                self.assertEqual((row['entity_type'], row['lifecycle_stage'], row['candidate_purpose']), (entity, stage, purpose))
                self.assertEqual(row['classification'], classification)
                self.assertEqual(result.would_create_candidates, eligible)
                self.assertIsInstance(row['constraint_domains'], list)
                self.assertEqual(result.taxonomy_summary['entity_type_counts'], {entity: 1})
                self.assertEqual(result.taxonomy_summary['lifecycle_stage_counts'], {stage: 1})
                self.assertEqual(result.taxonomy_summary['candidate_purpose_counts'], {purpose: 1})

    def test_equipment_mentions_are_topics_not_a_facility_replacement(self):
        result, row = self.preview('https://datacenterdynamics.com/en/news/proposed-data-center/',
            name='Example Data Center', lifecycle_state='Proposed',
            notes='Onsite power with gas turbines, backup generators and fuel cells. Transformer supply shortages. Cooling towers and chillers need water. Air emissions permits, rezoning, community opposition, litigation, financing costs and schedule delays.')
        self.assertEqual(row['entity_type'], 'data_center_project')
        self.assertEqual(row['candidate_purpose'], 'build_review')
        self.assertTrue({'onsite_power','gas_turbine_supply','backup_generation','fuel_supply',
                         'transformer_supply','grid_capacity','water_cooling','schedule_delay','air_emissions',
                         'land_use_zoning','community_opposition','legal_regulatory','cost_financing'} <= set(row['constraint_domains']))
        self.assertEqual(result.would_create_candidates, 1)

    def test_standalone_assets_supply_reports_and_unknowns(self):
        cases = [
            ({'name': 'Proposed gas turbine power plant', 'lifecycle_state': 'Proposed'}, 'power_generation_asset', 'infrastructure_context'),
            ({'name': 'Regional substation', 'lifecycle_state': 'Under construction'}, 'grid_interconnection_asset', 'infrastructure_context'),
            ({'name': 'Water treatment plant', 'lifecycle_state': 'Operating'}, 'cooling_water_asset', 'infrastructure_context'),
            ({'name': 'Gas turbine supply shortage report'}, 'equipment_supply_chain_signal', 'supply_chain_signal'),
            ({'name': 'Regional permitting case'}, 'policy_permitting_case', 'permitting_or_policy_signal'),
            ({'name': 'Operational data center campus', 'lifecycle_state': 'Operating'}, 'data_center_campus', 'facility_baseline'),
            ({}, 'unknown', 'unknown'),
        ]
        for n, entity, purpose in cases:
            with self.subTest(n=n):
                q = classify_source_and_candidate(None, n)
                value = classify_entity_taxonomy(n, q)
                self.assertEqual(value['entity_type'], entity)
                self.assertEqual(value['candidate_purpose'], purpose)
                self.assertIn(value['lifecycle_stage'], LIFECYCLE_STAGES)
        n = {'name': 'Gas turbine supply report'}
        url = 'https://datacenterwatch.org/report'
        value = classify_entity_taxonomy(n, classify_source_and_candidate(url, n), [url])
        self.assertEqual(value['candidate_purpose'], 'supply_chain_signal')

    def test_lifecycle_unknowns_and_structured_mentions(self):
        for status, stage in [('Operating','existing_operational'), ('Under construction','under_construction'),
                              ('Proposed','proposed'), ('Planned expansion','planned_expansion'),
                              ('Unverified','speculative_or_unverified'), ('Cancelled','cancelled'),
                              ('Retired','retired'), ('Not operational','unknown'), ('Approved','unknown')]:
            n = {'name': 'Example Data Center', 'lifecycle_state': status}
            value = classify_entity_taxonomy(n, classify_source_and_candidate(None, n))
            self.assertEqual(value['lifecycle_stage'], stage)
        n = {'name': 'Example Data Center'}
        q = classify_source_and_candidate(None, n)
        value = classify_entity_taxonomy(n, q, raw_row={'number_of_generators':'2', 'cooling_source':'Air', 'community_pushback':'yes'})
        self.assertTrue({'backup_generation','water_cooling','community_opposition'} <= set(value['constraint_domains']))
        empty = classify_entity_taxonomy({}, classify_source_and_candidate(None, {}),
                                         raw_row={'number_of_generators':'0', 'cooling_source':'unknown', 'community_pushback':'no', 'secret':'water turbines'})
        self.assertEqual(empty['constraint_domains'], [])
        self.assertEqual(empty['entity_type'], 'unknown')

    def test_summary_pages_reconcile_without_changing_decisions(self):
        self.preview('https://facebook.com/groups/123', name='Context row')
        self.preview('https://expedient.com/data-centers/phoenix/', name='PHX1', lifecycle_state='Operating')
        self.preview('https://datacenterdynamics.com/en/news/proposed-campus/', name='Guadalupe Data Center', lifecycle_state='Proposed')
        before = self.snapshot()
        flags = dict(dataset='fractracker_us_data_centers', include_row_details=True)
        whole = backfill_candidates(self.db, limit=3, **flags)
        pages = [backfill_candidates(self.db, offset=i, limit=1, **flags) for i in range(3)]
        for key, counts in whole.taxonomy_summary.items():
            total = Counter()
            for page in pages:
                total.update(page.taxonomy_summary[key])
            self.assertEqual(counts, dict(total))
        self.assertEqual(whole.row_details, [d for page in pages for d in page.row_details])
        self.assertEqual(whole.would_create_candidates, sum(p.would_create_candidates for p in pages))
        no_details = backfill_candidates(self.db, dataset=flags['dataset'], limit=3)
        self.assertEqual(no_details.taxonomy_summary, whole.taxonomy_summary)
        self.assertNotIn('row_details', no_details.to_dict())
        self.assertEqual(sum(whole.taxonomy_summary['entity_type_counts'].values()), whole.rows_checked)
        self.assertEqual(self.snapshot(), before)
        self.assert_only_import_tables()

    def test_secondary_paths_add_topics_without_changing_entity_or_lifecycle(self):
        n = {'name': 'General report'}
        primary = 'https://datacenterwatch.org/report'
        quality = classify_source_and_candidate(primary, n)
        value = classify_entity_taxonomy(n, quality, [primary, 'https://example.org/gas-turbine-supply-shortages/'])
        self.assertEqual(value['entity_type'], 'supporting_context')
        self.assertEqual(value['lifecycle_stage'], 'unknown')
        self.assertEqual(value['candidate_purpose'], 'supporting_context')
        self.assertTrue({'gas_turbine_supply', 'schedule_delay'} <= set(value['constraint_domains']))
        n = {'name': 'Example Data Center', 'lifecycle_state': 'Not operational'}
        value = classify_entity_taxonomy(n, classify_source_and_candidate(None, n), ['https://example.org/operating-data-center/'])
        self.assertEqual(value['lifecycle_stage'], 'unknown')
        value = classify_entity_taxonomy({'notes': 'Wind turbines'}, classify_source_and_candidate(None, {}))
        self.assertNotIn('gas_turbine_supply', value['constraint_domains'])
        url = 'https://datacenterdynamics.com/en/news/industry-forecast/'
        value = classify_entity_taxonomy({}, classify_source_and_candidate(url, {}), [url])
        self.assertEqual(value['entity_type'], 'supporting_context')
        self.assertNotIn('legal_regulatory', value['constraint_domains'])
