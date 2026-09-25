"""Reporting regressions use disposable candidates and never confirm promotion."""
from collections import Counter
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from app.services.auto_promotion_diagnostics import diagnostic_row, grouped_diagnostics
from app.services.automated_candidate_promotion import DECISIONS
from tests.test_automated_candidate_promotion import harness

REQUIRED_FIELDS = {
    'candidate_id', 'candidate_name', 'candidate_status', 'confidence', 'latitude', 'longitude',
    'promoted_project_id', 'promotion_decision', 'primary_blocker', 'blocker_category',
    'decision_reasons', 'blocking_reasons', 'source_quality', 'source_quality_status',
    'source_alignment_status', 'lifecycle_state', 'primary_source_url', 'provenance',
}


@pytest.mark.parametrize('fields,decision,category,primary', [
    ({}, 'would_promote', 'none', 'none'),
    ({'raw_metadata_json': {}, 'confidence': .3}, 'skip_missing_coordinates', 'missing_coordinates', 'coordinates'),
    ({'confidence': .3}, 'skip_low_confidence', 'low_confidence', 'confidence'),
    ({'status': 'promoted', 'raw_metadata_json': {}, 'confidence': .3}, 'skip_already_promoted', 'already_promoted', 'already_promoted'),
    ({'primary_source_url': 'https://facebook.com/groups/alpha'}, 'skip_weak_source', 'weak_source', 'primary_source'),
    ({'review_decision': 'keep_under_review'}, 'exception_review', 'review_hold', 'review_decision'),
    ({'status': 'rejected'}, 'exception_review', 'candidate_status', 'candidate_status'),
])
def test_explicit_rows_reconcile_without_writes(harness, fields, decision, category, primary):
    candidate = harness.seed(**fields)
    before = harness.snapshot()
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split()[0].upper())
    event.listen(harness.engine, 'before_cursor_execute', capture)
    report = harness.run(include_row_details=True)
    assert not {'INSERT', 'UPDATE', 'DELETE'} & set(statements)
    assert before == harness.snapshot()
    row = report['row_details'][0]
    assert REQUIRED_FIELDS <= row.keys()
    assert row['candidate_id'] == str(candidate.id)
    assert row['candidate_status'] == row['status'] == candidate.status
    assert row['promotion_decision'] == row['decision'] == decision
    assert row['decision_reasons'] == row['reasons'] and all(row['decision_reasons'])
    assert row['blocker_category'] == category
    assert row['primary_blocker'] == primary
    assert row['confidence'] == candidate.confidence
    assert row['lifecycle_state'] == candidate.lifecycle_state
    assert row['primary_source_url'] == candidate.primary_source_url
    assert row['blocking_reasons'] if decision not in {'would_promote', 'skip_already_promoted'} else row['blocking_reasons'] == []
    assert report['decisions_by_type'][decision] == report['blockers_by_category'][category] == 1
    assert report['candidates_by_status'] == {candidate.status: 1}
    assert report['candidates_by_lifecycle_state'] == {candidate.lifecycle_state: 1}
    assert_reconciles(report)
    json.dumps(report, allow_nan=False)


def assert_reconciles(report):
    rows = report['row_details']
    assert len(rows) == report['candidates_checked']
    actual = Counter(row['promotion_decision'] for row in rows)
    assert report['decisions_by_type'] == {key: actual[key] for key in report['decisions_by_type']}
    assert report['blockers_by_category'] == dict(Counter(row['blocker_category'] for row in rows))
    for key in DECISIONS:
        decision = 'would_promote' if key == 'promote' else key
        assert report['would_' + key] == actual[decision]
    for name in ['decisions_by_type', 'blockers_by_category', 'candidates_by_status',
                 'candidates_by_lifecycle_state', 'candidates_by_coordinate_availability']:
        assert sum(report[name].values()) == len(rows), name
    for category, examples in report['top_blocker_examples'].items():
        assert 0 < len(examples) <= 5
        assert all(row in rows and row['blocker_category'] == category for row in examples)


def test_mixed_skips_secondary_failures_do_not_inflate_primary_counts(harness):
    harness.seed(raw_metadata_json={}, confidence=.2)
    harness.seed(confidence=.4, primary_source_url='https://facebook.com/groups/alpha')
    harness.seed(status='promoted', raw_metadata_json={}, confidence=.2)
    result = harness.run(include_row_details=True)
    assert result['would_skip_already_promoted'] == result['would_skip_missing_coordinates'] == result['would_skip_low_confidence'] == 1
    assert result['would_skip_weak_source'] == 0
    assert result['blockers_by_category'] == {'already_promoted': 1, 'low_confidence': 1, 'missing_coordinates': 1}
    assert result['candidates_by_coordinate_availability'] == {'available': 1, 'missing_or_invalid': 2}
    missing = next(row for row in result['row_details'] if row['blocker_category'] == 'missing_coordinates')
    assert 'coordinate' in missing['decision_reasons'][0]
    assert any('confidence' in reason for reason in missing['blocking_reasons'])
    assert_reconciles(result)


def test_duplicate_risk_remains_explicit(harness):
    harness.seed(); harness.seed()
    report = harness.run(include_row_details=True)
    assert report['would_skip_duplicate_risk'] == 2
    assert all(row['promotion_decision'] == 'skip_duplicate_risk' and row['blocker_category'] == 'duplicate_risk'
               for row in report['row_details'])
    assert_reconciles(report)


def test_provenance_and_effective_coordinates_are_reported(harness):
    candidate = harness.seed()
    audit = harness.link(candidate)
    report = harness.run(include_row_details=True)
    row = report['row_details'][0]
    assert (row['latitude'], row['longitude']) == (38.9, -77.4)
    assert row['source_lifecycle_state'] == 'Proposed'
    assert row['source_quality_status'] == 'government_or_regulatory'
    assert row['source_alignment_status'] == 'aligned'
    assert row['provenance']['dataset_ids'] == ['epoch_ai_data_centers']
    assert row['provenance']['imported_rows'][0]['imported_row_id'] == str(audit.id)
    assert_reconciles(report)


def test_empty_filtered_and_bounded_examples_with_no_details(harness):
    for _ in range(7):
        harness.seed(raw_metadata_json={})
    full = harness.run(include_row_details=True)
    assert_reconciles(full)
    assert len(full['top_blocker_examples']['missing_coordinates']) == 5
    summary = harness.run()
    assert 'row_details' not in summary
    assert summary == {k: v for k, v in full.items() if k != 'row_details'}
    limited = harness.run(limit=2, include_row_details=True)
    assert limited['candidates_checked'] == 2 and limited['candidates_matching_filters'] == 7
    assert_reconciles(limited)
    empty = harness.run(dataset='not_present', include_row_details=True)
    assert_reconciles(empty)
    assert empty['top_blocker_examples'] == {}


def test_presentation_does_not_modify_evaluation_or_its_legacy_audit_contract(harness):
    candidate = harness.seed()
    report = harness.run(include_row_details=True)
    row = report['row_details'][0]
    evaluation = {**row, 'promotion_decision': 'promote'}
    before = deepcopy(evaluation)
    # No Project is inserted: only the stored-coordinate presentation is needed.
    diagnostic_row(candidate, [], SimpleNamespace(latitude=0, longitude=0), {}, evaluation)
    assert evaluation == before
    assert grouped_diagnostics([])['candidates_by_coordinate_availability'] == {'available': 0, 'missing_or_invalid': 0}
