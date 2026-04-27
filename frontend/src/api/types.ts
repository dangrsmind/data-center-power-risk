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

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------
export interface ProjectEvent {
  event_id: string;
  event_family: string;       // E1 | E2 | E3 | E4
  event_scope: string;
  event_date: string;
  phase_id: string | null;
  phase_name: string | null;
  region_name: string | null;
  utility_name: string | null;
  severity: string | null;
  reason_class: string | null;
  confidence: string | null;
  causal_strength: string;
  stress_direction: string;
  weak_label_weight: number | null;
  adjudicated: boolean;
  notes: string | null;
}

export interface ProjectEventsData {
  project_id: string;
  project_name: string;
  events: ProjectEvent[];
}

// ---------------------------------------------------------------------------
// Stress
// ---------------------------------------------------------------------------
export interface StressSignal {
  stress_observation_id: string;
  signal_name: string;
  source_signal_type: string;
  quarter: string;
  signal_value: number;
  signal_weight: number;
  derived_by: string | null;
}

export interface CurrentStress {
  quarter: string;
  project_stress_score: number | null;
  regional_stress_score: number | null;
  anomaly_score: number | null;
  evidence_quality_score: number | null;
  model_version: string;
  region_name: string | null;
  utility_name: string | null;
  decomposition: Record<string, number> | null;
}

export interface ProjectStressData {
  project_id: string;
  project_name: string;
  current_stress: CurrentStress | null;
  signals: StressSignal[];
}

// ---------------------------------------------------------------------------
// History
// ---------------------------------------------------------------------------
export interface ProjectHistoryItem {
  project_phase_quarter_id: string;
  quarter: string;
  phase_id: string;
  phase_name: string;
  current_hazard: number | null;
  deadline_probability: number | null;
  project_stress_score: number | null;
  regional_stress_score: number | null;
  anomaly_score: number | null;
  E1_label: boolean | null;
  E2_label: boolean | null;
  E3_intensity: number | null;
  E4_label: boolean | null;
  data_quality_score: number | null;
  model_version: string | null;
}

export interface ProjectHistoryData {
  project_id: string;
  project_name: string;
  history: ProjectHistoryItem[];
}

// ---------------------------------------------------------------------------
// Evidence
// ---------------------------------------------------------------------------
export interface EvidenceItem {
  evidence_id: string;
  source_type: string;
  source_date: string | null;
  title: string | null;
  source_url: string | null;
  source_rank: number | null;
  reviewer_status: string;
  excerpt: string | null;
  field_names: string[];
}

export interface ProjectEvidenceData {
  project_id: string;
  project_name: string;
  evidence: EvidenceItem[];
}

// ---------------------------------------------------------------------------
// Risk Signal
// ---------------------------------------------------------------------------
export interface RiskSignalEvidenceSummary {
  evidence_count: number;
  accepted_claim_count: number;
  unresolved_claim_count: number;
}

export interface ProjectRiskSignalData {
  project_id: string;
  risk_signal: string;
  risk_signal_score: number;
  risk_signal_tier: string;
  drivers: string[];
  missing_fields: string[];
  evidence_summary: RiskSignalEvidenceSummary;
  method: string;
}
