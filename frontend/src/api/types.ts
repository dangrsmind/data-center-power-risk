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

export type RiskTier = "high" | "elevated" | "medium" | "moderate" | "low" | "unknown";

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
  developer: string | null;
  state: string;
  county: string | null;
  latitude: number | null;
  longitude: number | null;
  region_or_rto: string;
  modeled_primary_load_mw: number;
  lifecycle_state: LifecycleState;
  risk_tier: RiskTier;
  current_hazard: number;
  deadline_probability: number;
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
  developer: string | null;
  state: string;
  county: string | null;
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

export interface EvidenceReviewResponse {
  evidence_id: string;
  reviewer_status: string;
}

export interface ProjectEnrichmentData {
  utility: string | null;
  confidence: string | null;
  source: string | null;
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

// ---------------------------------------------------------------------------
// Ingest Workbench
// ---------------------------------------------------------------------------

export type IngestSourceType =
  | "official_filing"
  | "utility_statement"
  | "regulatory_record"
  | "county_record"
  | "press"
  | "developer_statement"
  | "other";

export interface IntakePacketRequest {
  source_url?: string;
  source_type: IngestSourceType;
  source_date?: string;
  title?: string;
  evidence_text: string;
  project_id?: string;
}

export interface IngestEvidencePayload {
  source_type: string;
  source_date?: string;
  source_url?: string;
  source_rank?: number;
  title?: string;
  extracted_text?: string;
  reviewer_status?: string;
}

export interface IngestClaimItem {
  claim_type: string;
  claim_value: Record<string, unknown>;
  claim_date?: string;
  confidence?: string;
}

export interface IngestSuggestedLinkTarget {
  claim_type: string;
  suggested_entity_type: string;
  suggested_entity_id: string;
  suggested_entity_label: string;
  reason: string;
}

export interface IntakePacketResponse {
  evidence_payload: IngestEvidencePayload;
  claims_payload: { claims: IngestClaimItem[] };
  suggested_link_targets: IngestSuggestedLinkTarget[];
  exact_next_steps: string[];
  uncertainties: string[];
  warnings: string[];
  generator_version: string;
}

export interface IngestEvidenceResponse {
  evidence_id: string;
  source_type: string;
  source_date?: string;
  source_url?: string;
  title?: string;
  extracted_text?: string;
  reviewer_status: string;
  next_action: string;
  created_at: string;
  updated_at: string;
}

export interface IngestClaimResponse {
  claim_id: string;
  evidence_id: string;
  claim_type: string;
  claim_value: Record<string, unknown>;
  claim_date?: string;
  confidence?: string;
  entity_type?: string;
  entity_id?: string;
  entity_label?: string;
  review_status: string;
  is_contradictory: boolean;
  next_action: string;
  reviewed_at?: string;
  reviewed_by?: string;
  review_notes?: string;
  accepted_at?: string;
  accepted_by?: string;
  created_at: string;
  updated_at: string;
}

export interface IngestClaimsCreateResponse {
  evidence_id: string;
  created_claims: IngestClaimResponse[];
}

export interface IngestClaimAcceptResponse {
  claim_id: string;
  review_status: string;
  accepted_at: string;
  accepted_by: string;
  entity_label?: string;
  next_action: string;
  normalized_update: Record<string, unknown>;
  field_provenance: {
    field_provenance_id: string;
    entity_type: string;
    entity_id: string;
    field_name: string;
    evidence_id: string;
    claim_id?: string;
    created_at: string;
    updated_at: string;
  };
}
