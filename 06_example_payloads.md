Example API payloads

GET /projects
[
  {
    "project_id": "P001",
    "project_name": "Example Campus",
    "state": "TX",
    "region_or_rto": "ERCOT",
    "modeled_primary_load_mw": 300,
    "lifecycle_state": "monitoring_ready",
    "risk_tier": "high",
    "current_hazard": 0.08,
    "deadline_probability": 0.24,
    "data_quality_score": 81,
    "latest_update_date": "2026-04-01"
  }
]

GET /projects/P001/score
{
  "project_id": "P001",
  "phase_id": "PH1",
  "current_hazard": 0.08,
  "deadline_probability": 0.24,
  "top_drivers": [
    "new transmission required",
    "power path not fully identified",
    "high electrical dependency complexity"
  ],
  "evidence_quality_score": 0.74,
  "graph_fragility_summary": {
    "most_likely_break_node": "transmission_upgrade",
    "unresolved_critical_nodes": 3
  }
}

GET /projects/P001/timeline
[
  {
    "date": "2025-10-01",
    "source_type": "county_record",
    "summary": "Project announced with 300 MW initial build."
  },
  {
    "date": "2026-02-15",
    "source_type": "utility_statement",
    "summary": "Substation and transmission upgrades under review."
  }
]