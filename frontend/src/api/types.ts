export type LifecycleState =
  // Real backend values (from LifecycleState enum)
  | "candidate_unverified"
  | "named_verified"
  | "location_verified"
  | "load_partially_resolved"
  | "phase_resolved"
  | "power_path_partial"
  | "monitoring_ready"
  | "production_ready"
  // Legacy / mock values (kept for mock data compatibility)
  | "under_review"
  | "active_construction"
  | "operational"
  | "canceled"
  | "delayed"
  | "downsized";

export type RiskTier = "high" | "elevated" | "moderate" | "low" | "unknown";

export type PhaseStatus =
  | "planning"
  | "permitting"
  | "construction"
  | "energized"
  | "delayed"
  | "canceled";

export type SourceType =
  | "county_record"
  | "utility_statement"
  | "regulatory_filing"
  | "press"
  | "developer_statement"
  | "rto_filing";

export interface ProjectListItem {
  project_id: string;
  project_name: string;
  state: string;
  region_or_rto: string;
  modeled_primary_load_mw: number;
  lifecycle_state: LifecycleState;
  risk_tier: RiskTier;
  current_hazard: number;
  deadline_probability: number;
  data_quality_score: number;
  latest_update_date: string;
  phase_count: number;
}

export interface Phase {
  phase_id: string;
  phase_name: string;
  modeled_primary_load_mw: number;
  optional_expansion_mw: number | null;
  target_energization_date: string | null;
  status: PhaseStatus;
  utility: string | null;
  interconnection_status_known: boolean;
  new_transmission_required: boolean;
}

export interface GraphFragilitySummary {
  most_likely_break_node: string;
  unresolved_critical_nodes: number;
}

export interface Score {
  project_id: string;
  phase_id: string | null;
  current_hazard: number;
  deadline_probability: number;
  project_stress_score: number;
  regional_stress_score: number;
  anomaly_score: number;
  evidence_quality_score: number;
  top_drivers: string[];
  weak_signal_summary: string | null;
  graph_fragility_summary: GraphFragilitySummary | null;
  as_of_quarter: string;
}

export interface ProjectDetail {
  project_id: string;
  project_name: string;
  state: string;
  region_or_rto: string;
  utility: string | null;
  modeled_primary_load_mw: number;
  headline_load_mw: number | null;
  optional_expansion_mw: number | null;
  lifecycle_state: LifecycleState;
  risk_tier: RiskTier;
  announce_date: string | null;
  phases: Phase[];
  score: Score;
  data_quality_score: number;
  latest_update_date: string;
}

export interface TimelineEvent {
  date: string;
  source_type: SourceType;
  summary: string;
}
