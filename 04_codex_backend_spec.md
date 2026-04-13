Build the v1 backend for an internal forecasting platform that tracks power-linked impairment risk in large U.S. data-center projects.

Core rule:
- Unit of analysis is always `project_phase_quarter`.

Implement these backend components:
1. Normalized relational schema with separate tables for:
   - projects
   - phases
   - evidence
   - claims
   - events
   - quarterly_snapshots
   - graph_nodes
   - graph_edges
2. Lifecycle states:
   - candidate_unverified
   - named_verified
   - location_verified
   - load_partially_resolved
   - phase_resolved
   - power_path_partial
   - monitoring_ready
   - production_ready
3. Load semantics:
   - `headline_load_mw`
   - `modeled_primary_load_mw`
   - `optional_expansion_mw`
   - never merge optional expansion into primary load unless explicitly firm
4. Evidence/provenance:
   - every normalized high-value field must reference one or more evidence records
   - keep contradictions as parallel claims, not overwritten values
5. Adjudication support:
   - `qualifying_positive`
   - `ambiguous_near_positive`
   - `non_event`
   - all positives must remain human-reviewed
6. Quarterly feature builder for hazard modeling:
   - generate one row per active phase per quarter
   - include lagged features and label
7. Forecasting core:
   - implement discrete-time hazard model over `project_phase_quarter`
   - logistic regression for quarterly hazard
   - cumulative probability by deadline from quarterly hazards
8. Graph support:
   - store dependency nodes and edges
   - compute graph-derived fragility summary features
9. API endpoints:
   - list projects
   - project detail
   - phase detail
   - evidence timeline
   - adjudication queue
   - current score
   - score history
   - scenario response
   - data quality view
10. Reproducibility:
   - version quarterly snapshots
   - preserve historical scores by run date
11. Validation:
   - rolling temporal backtests only
   - no random train/test split

Required v1 outputs:
- quarterly hazard
- cumulative deadline probability
- top contributing features
- evidence quality score
- graph fragility summary
- audit trail

Deliver:
- working repo
- migrations
- seed-data import
- API docs
- tests
- local setup instructions