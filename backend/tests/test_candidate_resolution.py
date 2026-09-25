"""Resolution reports use disposable databases and never fetch sources."""
from collections import Counter
import json
import os
import subprocess
import sys

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.services.candidate_resolution import resolve_candidate_backlog
from scripts.resolve_candidate_backlog import parse_args
from tests.test_automated_candidate_promotion import harness


def report(harness, **kwargs):
    with Session(harness.engine) as db:
        return resolve_candidate_backlog(db, include_row_details=True, **kwargs)


def normalized(**kwargs):
    return {'normalized_row': dict(name='Alpha Data Center', state='VA', city='Ashburn',
        lifecycle_state='Proposed', dataset_row_type='data_center', **kwargs)}


@pytest.mark.parametrize('kwargs,expected', [
    ({}, 'promotable_now'),
    ({'raw_metadata_json': normalized()}, 'resolvable_missing_coordinates'),
    ({'confidence': .4}, 'low_confidence'),
    ({'status': 'promoted'}, 'already_promoted'),
    ({'raw_metadata_json': {'normalized_row': {'dataset_row_type': 'equipment_reference'}}},
     'context_only_or_supporting'),
    ({'review_decision': 'rejected'}, 'exception_review'),
])
def test_classification(harness, kwargs, expected):
    harness.seed(**kwargs)
    row = report(harness)['row_details'][0]
    assert row['resolution_class'] == expected, row
    for field in ('candidate_id', 'candidate_name', 'status', 'confidence', 'lifecycle_state',
                  'city', 'state', 'county', 'latitude', 'longitude', 'primary_source_url',
                  'warnings', 'source_quality', 'source_row_alignment',
                  'primary_resolution_blocker', 'resolution_reasons', 'recommended_next_action'):
        assert field in row
    assert row['resolution_reasons']


@pytest.mark.parametrize('coordinates', [{}, {'latitude': 38.9, 'longitude': -77.4}])
def test_placeholder_cannot_be_fixed_with_coordinates(harness, coordinates):
    harness.seed(name='Unresolved Virginia SCC candidate 7db4fd45',
                 raw_metadata_json=normalized(**coordinates))
    row = report(harness)['row_details'][0]
    assert row['resolution_class'] == 'unresolved_placeholder'
    assert row['recommended_next_action'] == 'suppress_from_promotion'


@pytest.mark.parametrize('warning', ['unresolved_candidate_name', 'missing_state', 'missing_project_specific_claim'])
def test_explicit_placeholder_warnings(harness, warning):
    harness.seed(triage_warnings_json=[warning])
    assert report(harness)['row_details'][0]['resolution_class'] == 'unresolved_placeholder'


def test_identity_repair(harness):
    harness.seed(name='', raw_metadata_json=normalized())
    row = report(harness)['row_details'][0]
    assert row['resolution_class'] == 'resolvable_missing_identity', row


def test_duplicates_require_exception_review(harness):
    harness.seed()
    harness.seed()
    result = report(harness)
    assert result['duplicate_risk_count'] == 2
    assert all(row['primary_resolution_blocker'] == 'duplicate_risk' for row in result['row_details'])


def test_no_writes_and_reconciliation(harness):
    harness.seed()
    harness.seed(name='Unresolved SCC candidate 123', confidence=.4)
    harness.seed(name='Already linked', status='promoted')
    before = harness.snapshot()
    def reject_writes(conn, cursor, statement, parameters, context, executemany):
        assert statement.split()[0].upper() not in {'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP'}
    event.listen(harness.engine, 'before_cursor_execute', reject_writes)
    result = report(harness)
    assert before == harness.snapshot()
    assert result == report(harness)
    rows = result['row_details']
    for group, field in [('counts_by_resolution_class', 'resolution_class'),
                         ('counts_by_recommended_next_action', 'recommended_next_action'),
                         ('counts_by_status', 'status'), ('counts_by_lifecycle_state', 'lifecycle_state'),
                         ('counts_by_state', 'normalized_state')]:
        assert Counter({k: v for k, v in result[group].items() if v}) == Counter(row[field] for row in rows)
        assert sum(result[group].values()) == result['candidates_checked'] == len(rows)
    assert result['counts_by_warning'] == Counter(w for row in rows for w in row['warnings'])
    assert report(harness, limit=0)['candidates_checked'] == 0


def test_cli_read_only(harness):
    harness.seed()
    before = harness.path.read_bytes()
    proc = subprocess.run([sys.executable, 'scripts/resolve_candidate_backlog.py',
                           '--dry-run', '--include-row-details', '--limit', '200'],
                          env={**os.environ, 'DATABASE_URL': f'sqlite:///{harness.path}'},
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)['counts_by_resolution_class']['promotable_now'] == 1
    assert harness.path.read_bytes() == before


@pytest.mark.parametrize('args', [['--confirm'], ['--limit', '-1'], ['--min-confidence', 'nan']])
def test_cli_rejects_unsafe_arguments(args):
    with pytest.raises(SystemExit):
        parse_args(args)
