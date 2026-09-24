"""Promotion tests never use the local demo DB or external services."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.models import Base
from app.models.project import Project
from app.models.project_candidate import ProjectCandidate
from app.models.imported_dataset import ImportedDatasetRun, ImportedDatasetRow, ImportedCandidateLink
from app.services.automated_candidate_promotion import auto_promote_candidates
from scripts.auto_promote_candidates import parse_args


@pytest.fixture
def harness(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'promotion.db'}")
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    class Harness:
        def seed(self, name='Alpha Data Center', **kwargs):
            n = {'name': name, 'state': 'VA', 'city': 'Ashburn', 'lifecycle_state': 'Proposed',
                 'dataset_row_type': 'data_center', 'latitude': 38.9, 'longitude': -77.4}
            candidate = ProjectCandidate(candidate_key=str(uuid.uuid4()), candidate_name=name,
                state='VA', city='Ashburn', lifecycle_state='candidate_unverified', status='needs_review',
                confidence=.9, primary_source_url='https://example.gov/planning/alpha-data-center-proposed-in-ashburn-virginia',
                raw_metadata_json={'normalized_row': n})
            for key, value in kwargs.items():
                setattr(candidate, key, value)
            with Session(engine, expire_on_commit=False) as db:
                db.add(candidate); db.commit()
            return candidate
        def run(self, **kwargs):
            with Session(engine) as db:
                return auto_promote_candidates(db, **kwargs)
        def snapshot(self):
            with Session(engine) as db:
                return {t.name: deepcopy(list(db.execute(select(t)))) for t in Base.metadata.sorted_tables}
        def link(self, candidate, dataset='epoch_ai_data_centers', **kwargs):
            n = deepcopy(candidate.raw_metadata_json['normalized_row'])
            with Session(engine, expire_on_commit=False) as db:
                run = ImportedDatasetRun(dataset_name=dataset, source_file='data_centers.csv', dry_run=False)
                db.add(run); db.flush()
                row = ImportedDatasetRow(run_id=run.id, dataset_name=dataset, source_file=run.source_file,
                    row_number=1, normalized_row_json=n, source_urls_json=[candidate.primary_source_url], duplicate_status='distinct')
                for key, value in kwargs.items():
                    setattr(row, key, value)
                db.add(row); db.flush()
                db.add(ImportedCandidateLink(imported_row_id=row.id, linked_record_type='project_candidate',
                    linked_record_id=candidate.id, duplicate_status='distinct'))
                db.commit()
            return row
    h = Harness(); h.engine = engine; h.path = tmp_path / 'promotion.db'
    yield h
    engine.dispose()


def test_preview_preserves_all_tables_and_is_deterministic(harness):
    harness.seed()
    before = harness.snapshot()
    first = harness.run(include_row_details=True)
    assert first['would_promote'] == 1, first
    assert first == harness.run(include_row_details=True)
    assert before == harness.snapshot()


def test_caps_fail_before_any_write(harness):
    harness.seed(); before = harness.snapshot(); writes = []
    def observe(conn, cursor, statement, parameters, context, executemany):
        if statement.split()[0].upper() in {'INSERT', 'UPDATE', 'DELETE'}:
            writes.append(statement)
    event.listen(harness.engine, 'before_cursor_execute', observe)
    for kwargs in [{}, {'max_promote': 0}, {'max_promote': -1}, {'max_promote': True}]:
        with pytest.raises(ValueError):
            harness.run(confirm=True, **kwargs)
    assert not writes
    assert before == harness.snapshot()


def test_confirm_coordinates_provenance_idempotency_and_only_two_tables(harness):
    c = harness.seed(); row = harness.link(c)
    before = harness.snapshot()
    report = harness.run(confirm=True, max_promote=1, include_row_details=True)
    assert report['promoted'] == 1
    with Session(harness.engine) as db:
        candidate = db.get(ProjectCandidate, c.id)
        project = db.get(Project, candidate.promoted_project_id)
        assert candidate.status == 'promoted'
        assert (project.latitude, project.longitude) == (38.9, -77.4)
        assert project.coordinate_source_url == c.primary_source_url
        assert project.coordinate_status == 'unverified'
        assert project.coordinate_verified_at is None
        assert project.coordinate_precision == 'source_row'
        assert project.coordinate_confidence == .9
        assert project.coordinate_updated_at is not None
        assert project.lifecycle_state.value == 'candidate_unverified'
        assert candidate.verified_at is None and not candidate.auto_admit_eligible
        assert project.candidate_metadata_json['candidate_provenance'] == c.raw_metadata_json
        assert project.candidate_metadata_json['automated_promotion']['imported_row_ids'] == [str(row.id)]
    after = harness.snapshot()
    for table in before:
        if table not in {'projects', 'project_candidates'}:
            assert before[table] == after[table], table
    report = harness.run(confirm=True, max_promote=0)
    assert report['promoted'] == 0 and report['would_skip_already_promoted'] == 1
    assert after == harness.snapshot()


@pytest.mark.parametrize('kwargs,lane', [
    ({'raw_metadata_json': {}}, 'skip_missing_coordinates'),
    ({'confidence': .79}, 'skip_low_confidence'),
    ({'primary_source_url': 'https://facebook.com/groups/alpha'}, 'skip_weak_source'),
    ({'primary_source_url': 'http://[broken'}, 'skip_weak_source'),
    ({'primary_source_url': 'https://example.gov/'}, 'skip_weak_source'),
    ({'primary_source_url': 'https://www.datacenterdynamics.com/en/news/alpha-proposed-in-ashburn-virginia'}, 'skip_weak_source'),
    ({'status': 'rejected'}, 'exception_review'),
    ({'verification_status': 'quarantined'}, 'exception_review'),
    ({'verification_status': 'needs_review'}, 'exception_review'),
    ({'review_decision': 'keep_under_review'}, 'exception_review'),
    ({'verification_errors_json': ['conflicting_identity']}, 'exception_review'),
    ({'state': 'CA'}, 'exception_review'),
])
def test_blocks(harness, kwargs, lane):
    harness.seed(**kwargs)
    before = harness.snapshot()
    report = harness.run(confirm=True, max_promote=0, include_row_details=True)
    assert report['would_' + lane] == 1, report
    assert report['row_details'][0]['blocking_warnings']
    assert before == harness.snapshot()


@pytest.mark.parametrize('stage', ['Operating', 'Cancelled', 'Unknown', 'Retired', 'Speculative'])
def test_incompatible_lifecycle_blocks(harness, stage):
    c = harness.seed()
    with Session(harness.engine) as db:
        stored = db.get(ProjectCandidate, c.id)
        n = {**c.raw_metadata_json['normalized_row'], 'lifecycle_state': stage}
        stored.raw_metadata_json = {'normalized_row': n}; db.commit()
    assert harness.run()['would_exception_review'] == 1


def test_project_duplicates_beyond_1000_and_candidate_batch_conflicts(harness):
    c = harness.seed()
    with Session(harness.engine) as db:
        db.add_all([Project(canonical_name=f'Existing site {i}', state='NY', lifecycle_state='candidate_unverified') for i in range(1001)])
        db.add(Project(canonical_name=c.candidate_name, state='VA', latitude=38.9, longitude=-77.4, lifecycle_state='candidate_unverified'))
        db.commit()
    assert harness.run(confirm=True, max_promote=0)['would_skip_duplicate_risk'] == 1
    harness.seed(candidate_name='Alpha Data Center duplicate')
    assert harness.run()['would_skip_duplicate_risk'] == 2


def test_duplicate_candidates_in_same_batch_never_create_two_projects(harness):
    harness.seed(); harness.seed()
    assert harness.run(confirm=True, max_promote=0)['would_skip_duplicate_risk'] == 2


def test_unknown_or_disallowed_dataset_and_context_rows_block(harness):
    c = harness.seed(); harness.link(c, dataset='fractracker_us_data_centers')
    result = harness.run(include_row_details=True)
    assert result['would_exception_review'] == 1
    assert not result['row_details'][0]['gates']['dataset_policy']


def test_imported_row_coordinates_fallback_and_conflicts(harness):
    c = harness.seed(); row = harness.link(c)
    with Session(harness.engine) as db:
        stored = db.get(ProjectCandidate, c.id)
        n = {**c.raw_metadata_json['normalized_row']}; n.pop('latitude'); n.pop('longitude')
        stored.raw_metadata_json = {'normalized_row': n}; db.commit()
    assert harness.run(confirm=True, max_promote=1)['promoted'] == 1
    with Session(harness.engine) as db:
        p = db.scalar(select(Project))
        assert (p.latitude, p.longitude) == (38.9, -77.4)
        assert p.coordinate_source == 'baseline_imported_dataset_row'
        assert str(row.id) in p.coordinate_notes


def test_conflicting_coordinate_rows_and_weak_alignment_block(harness):
    c = harness.seed()
    n = {**c.raw_metadata_json['normalized_row'], 'latitude': 40}
    harness.link(c, normalized_row_json=n)
    assert harness.run()['would_exception_review'] == 1


def test_filters_allowlist_limit_and_missing_id(harness):
    c = harness.seed(); harness.link(c)
    for kwargs in [{'dataset':'other'}, {'source':'social'}, {'limit':0}]:
        assert harness.run(**kwargs)['candidates_checked'] == 0
    result = harness.run(dataset='epoch_ai_data_centers', source='EXAMPLE.GOV', candidate_ids=[c.id], limit=1)
    assert result['candidates_checked'] == result['would_promote'] == 1
    with pytest.raises(ValueError, match='Unknown candidate'):
        harness.run(candidate_ids=[uuid.uuid4()])


def test_late_failure_rolls_back_project_and_candidate(harness):
    harness.seed(); before = harness.snapshot()
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('UPDATE project_candidates'):
            raise RuntimeError('injected late update failure')
    event.listen(harness.engine, 'before_cursor_execute', fail)
    with pytest.raises(RuntimeError):
        harness.run(confirm=True, max_promote=1)
    event.remove(harness.engine, 'before_cursor_execute', fail)
    assert before == harness.snapshot()


def test_cli_validation_and_real_default_read_only_preview(harness):
    for args in [['--confirm'], ['--confirm','--max-promote','-1'], ['--min-confidence','nan'], ['--limit','-1'], ['--candidate-id','invalid']]:
        with pytest.raises(SystemExit): parse_args(args)
    harness.seed(); before = harness.path.read_bytes()
    result = subprocess.run([sys.executable, 'scripts/auto_promote_candidates.py', '--include-row-details'],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, 'DATABASE_URL': f'sqlite:///{harness.path}'},
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['dry_run'] and report['would_promote'] == 1
    assert before == harness.path.read_bytes()

@pytest.mark.parametrize('change', [
    {'dataset_row_type': 'equipment'}, {'name': 'Unrelated Data Center'}, {'lifecycle_state': 'Operating'},
    {'primary_source_facility_name': 'Unrelated building'},
])
def test_audit_context_and_identity_alignment_cannot_be_bypassed(harness, change):
    c = harness.seed()
    harness.link(c, normalized_row_json={**c.raw_metadata_json['normalized_row'], **change})
    assert harness.run(confirm=True, max_promote=0)['would_exception_review'] == 1


def test_duplicate_metadata_and_blocking_warnings_are_respected(harness):
    c = harness.seed()
    with Session(harness.engine) as db:
        db.get(ProjectCandidate, c.id).raw_metadata_json = {**c.raw_metadata_json, 'duplicate_status':'possible_duplicate'}
        db.commit()
    assert harness.run()['would_skip_duplicate_risk'] == 1
    with Session(harness.engine) as db:
        db.get(ProjectCandidate, c.id).raw_metadata_json = {**c.raw_metadata_json, 'warnings':['geography_conflict']}
        db.commit()
    assert harness.run()['would_exception_review'] == 1


def test_clean_session_required_and_nonfinite_threshold_rejected(harness):
    c = harness.seed()
    with Session(harness.engine) as db:
        db.get(ProjectCandidate, c.id).confidence = .99
        with pytest.raises(ValueError, match='clean session'):
            auto_promote_candidates(db)
    for value in [float('nan'), float('inf'), True, -.1, 1.1]:
        with pytest.raises(ValueError): harness.run(min_confidence=value)


def test_cap_checks_whole_selected_window_without_truncation(harness):
    harness.seed()
    harness.seed(name='Meridian Data Center', state='CO', city='Denver',
        primary_source_url='https://other.gov/planning/meridian-data-center-proposed-in-denver-colorado',
        raw_metadata_json={'normalized_row': {'name':'Meridian Data Center','state':'CO','city':'Denver',
            'latitude':39.7,'longitude':-105.0,'lifecycle_state':'Proposed','dataset_row_type':'data_center'}})
    assert harness.run()['would_promote'] == 2
    before = harness.snapshot()
    with pytest.raises(ValueError, match='Eligible count 2'):
        harness.run(confirm=True, max_promote=1)
    assert before == harness.snapshot()
    assert harness.run(confirm=True, max_promote=2)['promoted'] == 2


def test_confirm_recomputes_after_preview_and_custom_threshold(harness):
    c = harness.seed()
    assert harness.run()['would_promote'] == 1
    with Session(harness.engine) as db:
        db.get(ProjectCandidate,c.id).confidence = .75; db.commit()
    assert harness.run(confirm=True,max_promote=1)['promoted'] == 0
    assert harness.run(min_confidence=.75)['would_promote'] == 1


@pytest.mark.parametrize('url', [
    'https://example.gov/planning/proposed-data-center-in-virginia',
    'https://example.gov/planning/alpha-data-center-proposed-in-ashburn-california',
])
def test_weak_alignment_and_explicit_source_state_conflict_block(harness,url):
    harness.seed(primary_source_url=url)
    assert harness.run()['would_exception_review'] == 1


@pytest.mark.parametrize('lat,lon', [(91,-77),(38,181),(True,-77),('NaN',-77),(38,None)])
def test_invalid_coordinate_pairs_block(harness,lat,lon):
    c=harness.seed()
    with Session(harness.engine) as db:
        db.get(ProjectCandidate,c.id).raw_metadata_json={'normalized_row':{
            **c.raw_metadata_json['normalized_row'],'latitude':lat,'longitude':lon}}
        db.commit()
    assert harness.run()['would_skip_missing_coordinates'] == 1
