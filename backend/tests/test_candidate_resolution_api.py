from sqlalchemy.orm import Session
from app.api.routes.project_candidates import candidate_resolution_report, get_project_candidate_constraint_summary
from tests.test_automated_candidate_promotion import harness


def test_resolution_display_and_dashboard_exclude_placeholders_without_writes(harness):
    harness.seed()
    harness.seed(name='Unresolved Virginia SCC candidate 123',
                 state=None, city=None, primary_source_url='https://example.gov/scc/search',
                 raw_metadata_json={})
    before = harness.snapshot()
    with Session(harness.engine) as db:
        result = candidate_resolution_report(db=db)
        assert result['counts_by_resolution_class']['unresolved_placeholder'] == 1
        assert result['counts_by_resolution_class']['promotable_now'] == 1
        all_rows = get_project_candidate_constraint_summary(db=db, limit_top_candidates=10)
        reviewable = get_project_candidate_constraint_summary(
            db=db, resolution_scope='reviewable', limit_top_candidates=10)
        assert all_rows.total_candidates == 2
        assert reviewable.total_candidates == 1
    assert before == harness.snapshot()
