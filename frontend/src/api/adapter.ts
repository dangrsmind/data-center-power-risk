/**
 * API Adapter Layer
 *
 * Mock mode: controlled by VITE_USE_MOCK env var.
 *   VITE_USE_MOCK=false  → real backend
 *   anything else        → mock data (default)
 *
 * Base URL: set VITE_API_BASE_URL in .env.local
 *   In Replit: use /api  (Vite proxies /api/* → http://127.0.0.1:8000/*)
 *   Locally:   use http://127.0.0.1:8000
 *
 * All components import from this file only — never from mock.ts directly.
 */

import type {
  ProjectListItem,
  ProjectDetail,
  Phase,
  Score,
  LifecycleState,
  PhaseStatus,
  ProjectEventsData,
  ProjectEnrichmentData,
  ProjectStressData,
  ProjectHistoryData,
  ProjectEvidenceData,
  ProjectPredictionData,
  ProjectPredictionRunResponse,
  ProjectRiskSignalData,
  IntakePacketRequest,
  IntakePacketResponse,
  IngestEvidencePayload,
  IngestEvidenceResponse,
  ProjectCandidate,
  ProjectCandidateListResponse,
  ProjectCandidatePromotionRequest,
  ProjectCandidatePromotionResponse,
  ProjectCandidateReviewDecision,
  ProjectCandidateReviewDecisionRequest,
  DiscoveredSource,
  DiscoveredSourceReviewListResponse,
  DiscoveredSourceReviewSummaryResponse,
  DiscoveredSourceClaimListResponse,
  DiscoverDecisions,
  ManualCapture,
  ManualCapturesResponse,
  ManualCaptureRequest,
  ProjectCoordinatesRequest,
  MissingCoordinateProject,
  ProjectCoordinateHistoryItem,
  IngestClaimItem,
  IngestClaimsCreateResponse,
  IngestClaimResponse,
  IngestClaimAcceptResponse,
  ConstraintSummaryResponse,
  ConstraintSummaryItem,
} from "./types";
import {
  MOCK_PROJECTS,
  MOCK_PROJECT_DETAILS,
} from "./mock";

const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

const EMPTY_CONSTRAINT_SUMMARY: ConstraintSummaryResponse = {
  total_candidates: 0,
  by_status: {},
  by_verification_status: {},
  by_triage_tier: {},
  by_review_decision: {},
  csv_backed_count: 0,
  web_discovered_count: 0,
  with_energy_strategy_count: 0,
  by_energy_strategy: {},
  by_energy_risk_tag: {},
  with_siting_friction_count: 0,
  by_siting_friction_category: {},
  by_siting_friction_warning: {},
  high_priority_review_count: 0,
  needs_source_count: 0,
  ready_for_verification_count: 0,
  likely_duplicate_count: 0,
  dataset_only_rejected_count: 0,
  top_review_priority_candidates: [],
};

// ---------------------------------------------------------------------------
// Raw backend shapes (not exported — internal to the adapter only)
// ---------------------------------------------------------------------------

interface RawProjectListItem {
  id: string;
  canonical_name: string;
  developer: string | null;
  operator: string | null;
  state: string | null;
  county: string | null;
  latitude: number | null;
  longitude: number | null;
  coordinate_status: ProjectListItem["coordinate_status"] | null;
  coordinate_precision: ProjectListItem["coordinate_precision"] | null;
  coordinate_source: ProjectListItem["coordinate_source"] | null;
  coordinate_source_url: string | null;
  coordinate_notes: string | null;
  coordinate_confidence: number | null;
  coordinate_updated_at: string | null;
  coordinate_verified_at: string | null;
  lifecycle_state: string;
  announcement_date: string | null;
  latest_update_date: string | null;
  modeled_primary_load_mw: number | null;
  phase_count: number;
  current_hazard: number;
  deadline_probability: number;
  risk_tier: string;
  as_of_quarter: string | null;
}

interface RawProjectDetail {
  id: string;
  canonical_name: string;
  developer: string | null;
  operator: string | null;
  state: string | null;
  county: string | null;
  latitude: number | null;
  longitude: number | null;
  coordinate_status: ProjectDetail["coordinate_status"] | null;
  coordinate_precision: ProjectDetail["coordinate_precision"] | null;
  coordinate_source: ProjectDetail["coordinate_source"] | null;
  coordinate_source_url: string | null;
  coordinate_notes: string | null;
  coordinate_confidence: number | null;
  coordinate_updated_at: string | null;
  coordinate_verified_at: string | null;
  lifecycle_state: string;
  announcement_date: string | null;
  latest_update_date: string | null;
  region_id: string | null;
  utility_id: string | null;
  modeled_primary_load_mw: number | null;
  phase_count: number;
}

interface RawPhase {
  id: string;
  project_id: string;
  phase_name: string;
  phase_order: number | null;
  announcement_date: string | null;
  target_energization_date: string | null;
  status: string | null;
  notes: string | null;
  modeled_primary_load_mw: number | null;
  optional_expansion_mw: number | null;
}

interface RawScoreDriver {
  signal: string;
  contribution: number;
}

interface RawScore {
  project_id: string;
  phase_id: string | null;
  quarter: string | null;
  deadline_date: string;
  current_hazard: number;
  deadline_probability: number;
  project_stress_score: number;
  regional_stress_score: number;
  anomaly_score: number;
  evidence_quality_score: number;
  model_version: string;
  scoring_method: string;
  top_drivers: RawScoreDriver[];
  weak_signal_summary: Record<string, number | boolean | null>;
  graph_fragility_summary: {
    most_likely_break_node: string;
    unresolved_critical_nodes: number;
  };
}

// ---------------------------------------------------------------------------
// Transformation helpers
// ---------------------------------------------------------------------------

function quarterLabel(dateStr: string | null): string {
  if (!dateStr) return "unknown";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  const q = Math.ceil((d.getMonth() + 1) / 3);
  return `${d.getFullYear()}-Q${q}`;
}

function formatWeakSignalSummary(raw: Record<string, number | boolean | null>): string {
  const parts: string[] = [];
  if (raw.E2_label === true) parts.push("E2 power-linked disruption signal present");
  if (typeof raw.E3_intensity === "number" && raw.E3_intensity > 0)
    parts.push(`E3 regional stress intensity: ${raw.E3_intensity.toFixed(2)}`);
  if (raw.E4_label === true) parts.push("E4 workaround/adaptation indicator present");
  if (parts.length === 0) return "No E2/E3/E4 signals detected.";
  return parts.join(". ") + ".";
}

// Normalize backend risk tier values to the frontend RiskTier union.
// Backend _risk_tier() returns "high" / "medium" / "low".
// Frontend type uses "elevated" for the middle band (not "medium").
function normalizeRiskTier(raw: string | null | undefined): ProjectListItem["risk_tier"] {
  if (!raw) return "unknown";
  if (raw === "medium") return "elevated";
  return raw as ProjectListItem["risk_tier"];
}

// Derive risk_tier from deadline_probability using the same thresholds as the
// backend _risk_tier() function in project_service.py:
//   >= 0.66 → high, >= 0.33 → elevated (medium), else low
function deriveRiskTier(deadlineProbability: number): ProjectListItem["risk_tier"] {
  if (deadlineProbability >= 0.66) return "high";
  if (deadlineProbability >= 0.33) return "elevated";
  return "low";
}

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function finiteNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function nullableFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function cleanCountMap(value: unknown): Record<string, number> {
  if (!isObjectRecord(value)) return {};
  const entries = Object.entries(value)
    .filter((entry): entry is [string, number] => {
      const [key, count] = entry;
      return key.trim().length > 0 && typeof count === "number" && Number.isFinite(count);
    })
    .map(([key, count]) => [key, Math.max(0, count)] as const);
  return Object.fromEntries(entries);
}

function cleanStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function normalizeConstraintSummaryItem(value: unknown): ConstraintSummaryItem | null {
  if (!isObjectRecord(value)) return null;
  const candidateId = nullableString(value.candidate_id);
  const candidateName = nullableString(value.candidate_name);
  if (!candidateId || !candidateName) return null;
  const csvProvenance = isObjectRecord(value.csv_provenance)
    ? {
        provenance: nullableString(value.csv_provenance.provenance),
        dataset_name: nullableString(value.csv_provenance.dataset_name),
        duplicate_status: nullableString(value.csv_provenance.duplicate_status),
        imported_row_count: finiteNumber(value.csv_provenance.imported_row_count),
      }
    : null;
  return {
    candidate_id: candidateId,
    candidate_name: candidateName,
    state: nullableString(value.state),
    triage_tier: nullableString(value.triage_tier),
    triage_score: nullableFiniteNumber(value.triage_score),
    recommended_action: nullableString(value.recommended_action),
    review_decision: nullableString(value.review_decision),
    verification_status: nullableString(value.verification_status),
    status: nullableString(value.status) ?? "unknown",
    energy_strategy: nullableString(value.energy_strategy) as ConstraintSummaryItem["energy_strategy"],
    siting_friction_categories: cleanStringList(value.siting_friction_categories) as ConstraintSummaryItem["siting_friction_categories"],
    csv_provenance: csvProvenance,
    primary_source_url: nullableString(value.primary_source_url),
  };
}

function normalizeConstraintSummary(value: unknown): ConstraintSummaryResponse {
  if (!isObjectRecord(value)) return { ...EMPTY_CONSTRAINT_SUMMARY, top_review_priority_candidates: [] };
  const topCandidates = Array.isArray(value.top_review_priority_candidates)
    ? value.top_review_priority_candidates
        .map(normalizeConstraintSummaryItem)
        .filter((item): item is ConstraintSummaryItem => item !== null)
    : [];
  return {
    total_candidates: finiteNumber(value.total_candidates),
    by_status: cleanCountMap(value.by_status),
    by_verification_status: cleanCountMap(value.by_verification_status),
    by_triage_tier: cleanCountMap(value.by_triage_tier),
    by_review_decision: cleanCountMap(value.by_review_decision),
    csv_backed_count: finiteNumber(value.csv_backed_count),
    web_discovered_count: finiteNumber(value.web_discovered_count),
    with_energy_strategy_count: finiteNumber(value.with_energy_strategy_count),
    by_energy_strategy: cleanCountMap(value.by_energy_strategy),
    by_energy_risk_tag: cleanCountMap(value.by_energy_risk_tag),
    with_siting_friction_count: finiteNumber(value.with_siting_friction_count),
    by_siting_friction_category: cleanCountMap(value.by_siting_friction_category),
    by_siting_friction_warning: cleanCountMap(value.by_siting_friction_warning),
    high_priority_review_count: finiteNumber(value.high_priority_review_count),
    needs_source_count: finiteNumber(value.needs_source_count),
    ready_for_verification_count: finiteNumber(value.ready_for_verification_count),
    likely_duplicate_count: finiteNumber(value.likely_duplicate_count),
    dataset_only_rejected_count: finiteNumber(value.dataset_only_rejected_count),
    top_review_priority_candidates: topCandidates,
  };
}

function setNonEmptyParam(qs: URLSearchParams, key: string, value: unknown): void {
  if (typeof value === "string" && value.trim()) qs.set(key, value.trim());
}

function transformProjectListItem(raw: RawProjectListItem): ProjectListItem {
  return {
    project_id: raw.id,
    project_name: raw.canonical_name,
    developer: raw.developer ?? null,
    state: raw.state ?? "",
    county: raw.county ?? null,
    latitude: raw.latitude ?? null,
    longitude: raw.longitude ?? null,
    coordinate_status: raw.coordinate_status ?? null,
    coordinate_precision: raw.coordinate_precision ?? null,
    coordinate_source: raw.coordinate_source ?? null,
    coordinate_source_url: raw.coordinate_source_url ?? null,
    coordinate_notes: raw.coordinate_notes ?? null,
    coordinate_confidence: raw.coordinate_confidence ?? null,
    coordinate_updated_at: raw.coordinate_updated_at ?? null,
    coordinate_verified_at: raw.coordinate_verified_at ?? null,
    region_or_rto: "",
    modeled_primary_load_mw: raw.modeled_primary_load_mw ?? 0,
    lifecycle_state: raw.lifecycle_state as LifecycleState,
    risk_tier: normalizeRiskTier(raw.risk_tier),
    current_hazard: raw.current_hazard ?? 0,
    deadline_probability: raw.deadline_probability ?? 0,
    latest_update_date: raw.latest_update_date ?? "",
    phase_count: raw.phase_count,
  };
}

// Map raw backend phase status strings to frontend PhaseStatus type.
// The backend uses hyphenated values (e.g. "active-planning") that don't
// directly match the frontend enum — normalize them here.
const PHASE_STATUS_MAP: Record<string, PhaseStatus> = {
  "active-planning": "planning",
  "planning":        "planning",
  "permitting":      "permitting",
  "construction":    "construction",
  "energized":       "energized",
  "delayed":         "delayed",
  "canceled":        "canceled",
};

function normalizePhaseStatus(raw: string | null): PhaseStatus {
  if (!raw) return "planning";
  return PHASE_STATUS_MAP[raw] ?? "planning";
}

function transformPhase(raw: RawPhase): Phase {
  return {
    phase_id: raw.id,
    phase_name: raw.phase_name,
    modeled_primary_load_mw: raw.modeled_primary_load_mw ?? 0,
    optional_expansion_mw: raw.optional_expansion_mw,
    target_energization_date: raw.target_energization_date,
    status: normalizePhaseStatus(raw.status),
    utility: null,                       // not in phase endpoint
    interconnection_status_known: false, // not in phase endpoint
    new_transmission_required: false,    // not in phase endpoint
  };
}

function transformScore(raw: RawScore): Score {
  return {
    project_id: raw.project_id,
    phase_id: raw.phase_id,
    current_hazard: raw.current_hazard,
    deadline_probability: raw.deadline_probability,
    project_stress_score: raw.project_stress_score,
    regional_stress_score: raw.regional_stress_score,
    anomaly_score: raw.anomaly_score,
    evidence_quality_score: raw.evidence_quality_score,
    top_drivers: raw.top_drivers.map((d) => d.signal),
    weak_signal_summary: formatWeakSignalSummary(raw.weak_signal_summary),
    graph_fragility_summary: raw.graph_fragility_summary,
    as_of_quarter: quarterLabel(raw.quarter),
  };
}

// ---------------------------------------------------------------------------
// Fetch utilities
// ---------------------------------------------------------------------------

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status} ${res.statusText} — ${path}${text ? `: ${text}` : ""}`);
  }
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status} ${res.statusText} — ${path}${text ? `: ${text}` : ""}`);
  }
  return res.json() as Promise<T>;
}

async function patchJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status} ${res.statusText} — ${path}${text ? `: ${text}` : ""}`);
  }
  return res.json() as Promise<T>;
}

async function deleteJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, { method: "DELETE" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status} ${res.statusText} — ${path}${text ? `: ${text}` : ""}`);
  }
  return res.json() as Promise<T>;
}

function delay(ms = 120): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// ---------------------------------------------------------------------------
// Public API — all components use only these functions
// ---------------------------------------------------------------------------

export async function getProjects(): Promise<ProjectListItem[]> {
  if (USE_MOCK) {
    await delay();
    return MOCK_PROJECTS;
  }
  const raw = await fetchJson<RawProjectListItem[]>("/projects");
  return raw.map(transformProjectListItem);
}

export async function getProject(id: string): Promise<ProjectDetail> {
  if (USE_MOCK) {
    await delay();
    const detail = MOCK_PROJECT_DETAILS[id];
    if (!detail) throw new Error(`Project ${id} not found in mock data`);
    return detail;
  }

  // Three parallel calls: detail + phases + score
  const [rawProject, rawPhases, rawScore] = await Promise.all([
    fetchJson<RawProjectDetail>(`/projects/${id}`),
    fetchJson<RawPhase[]>(`/projects/${id}/phases`),
    fetchJson<RawScore>(`/projects/${id}/score`),
  ]);

  const phases = rawPhases.map(transformPhase);
  const score = transformScore(rawScore);

  return {
    project_id: rawProject.id,
    project_name: rawProject.canonical_name,
    developer: rawProject.developer ?? null,
    state: rawProject.state ?? "",
    county: rawProject.county ?? null,
    latitude: rawProject.latitude ?? null,
    longitude: rawProject.longitude ?? null,
    coordinate_status: rawProject.coordinate_status ?? null,
    coordinate_precision: rawProject.coordinate_precision ?? null,
    coordinate_source: rawProject.coordinate_source ?? null,
    coordinate_source_url: rawProject.coordinate_source_url ?? null,
    coordinate_notes: rawProject.coordinate_notes ?? null,
    coordinate_confidence: rawProject.coordinate_confidence ?? null,
    coordinate_updated_at: rawProject.coordinate_updated_at ?? null,
    coordinate_verified_at: rawProject.coordinate_verified_at ?? null,
    region_or_rto: "",            // region_id UUID only — name lookup not yet available
    utility: null,                // utility_id UUID only — name lookup not yet available
    modeled_primary_load_mw: rawProject.modeled_primary_load_mw ?? 0,
    headline_load_mw: null,       // not in backend schema yet
    optional_expansion_mw: null,  // not in project record — available per-phase
    lifecycle_state: rawProject.lifecycle_state as LifecycleState,
    // Derive risk_tier from score deadline_probability, consistent with backend
    // _risk_tier() in project_service.py. The /projects/{id} endpoint does not
    // return risk_tier directly, so we compute it here.
    risk_tier: deriveRiskTier(rawScore.deadline_probability),
    announce_date: rawProject.announcement_date,
    phases,
    score,
    data_quality_score: Math.round(score.evidence_quality_score * 100),
    latest_update_date: rawProject.latest_update_date ?? "",
  };
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

export async function getProjectEvents(id: string): Promise<ProjectEventsData> {
  if (USE_MOCK) {
    await delay();
    return { project_id: id, project_name: "", events: [] };
  }
  return fetchJson<ProjectEventsData>(`/projects/${id}/events`);
}

// ---------------------------------------------------------------------------
// Stress
// ---------------------------------------------------------------------------

export async function getProjectStress(id: string): Promise<ProjectStressData> {
  if (USE_MOCK) {
    await delay();
    return { project_id: id, project_name: "", current_stress: null, signals: [] };
}
  return fetchJson<ProjectStressData>(`/projects/${id}/stress`);
}

// ---------------------------------------------------------------------------
// History
// ---------------------------------------------------------------------------

export async function getProjectHistory(id: string): Promise<ProjectHistoryData> {
  if (USE_MOCK) {
    await delay();
    return { project_id: id, project_name: "", history: [] };
  }
  return fetchJson<ProjectHistoryData>(`/projects/${id}/history`);
}

// ---------------------------------------------------------------------------
// Evidence
// ---------------------------------------------------------------------------

export async function getProjectEnrichment(id: string): Promise<ProjectEnrichmentData> {
  if (USE_MOCK) {
    await delay();
    return { utility: null, confidence: null, source: null };
  }
  return fetchJson<ProjectEnrichmentData>(`/projects/${id}/enrichment`);
}

export async function getProjectEvidence(id: string): Promise<ProjectEvidenceData> {
  if (USE_MOCK) {
    await delay();
    return { project_id: id, project_name: "", evidence: [] };
  }
  return fetchJson<ProjectEvidenceData>(`/projects/${id}/evidence`);
}

export async function patchEvidenceReview(
  evidenceId: string,
  reviewerStatus: string,
  reviewedBy: string,
): Promise<{ reviewer_status: string }> {
  return patchJson<{ reviewer_status: string }>(`/evidence/${evidenceId}/review`, {
    reviewer_status: reviewerStatus,
    reviewed_by: reviewedBy,
  });
}

// ---------------------------------------------------------------------------
// Ingest Workbench
// ---------------------------------------------------------------------------

export async function postIntakePacket(req: IntakePacketRequest): Promise<IntakePacketResponse> {
  return postJson<IntakePacketResponse>("/automation/intake/packet", req);
}

export async function createEvidence(req: IngestEvidencePayload): Promise<IngestEvidenceResponse> {
  return postJson<IngestEvidenceResponse>("/evidence", req);
}

export async function createEvidenceClaims(
  evidenceId: string,
  claims: IngestClaimItem[],
): Promise<IngestClaimsCreateResponse> {
  return postJson<IngestClaimsCreateResponse>(`/evidence/${evidenceId}/claims`, { claims });
}

export async function linkClaim(
  claimId: string,
  projectId: string,
): Promise<IngestClaimResponse> {
  return postJson<IngestClaimResponse>(`/claims/${claimId}/link`, { project_id: projectId });
}

export async function reviewClaim(
  claimId: string,
  reviewer: string,
): Promise<IngestClaimResponse> {
  return postJson<IngestClaimResponse>(`/claims/${claimId}/review`, {
    review_status: "accepted_candidate",
    reviewer,
    is_contradictory: false,
  });
}

export async function acceptClaim(
  claimId: string,
  acceptedBy: string,
): Promise<IngestClaimAcceptResponse> {
  return postJson<IngestClaimAcceptResponse>(`/claims/${claimId}/accept`, { accepted_by: acceptedBy });
}

// ---------------------------------------------------------------------------
// Risk Signal
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Discovery Review
// ---------------------------------------------------------------------------

export async function getProjectCandidates(params?: {
  status?: string;
  state?: string;
  triage_tier?: string;
  recommended_action?: string;
  review_decision?: ProjectCandidateReviewDecision;
  has_review_decision?: boolean;
  energy_strategy?: ProjectCandidate["energy_strategy"];
  siting_friction_category?: ProjectCandidate["siting_friction_categories"][number];
  min_triage_score?: number;
  limit?: number;
}): Promise<ProjectCandidateListResponse> {
  if (USE_MOCK) {
    await delay();
    return { items: [] };
  }
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.state) qs.set("state", params.state);
  if (params?.triage_tier) qs.set("triage_tier", params.triage_tier);
  if (params?.recommended_action) qs.set("recommended_action", params.recommended_action);
  if (params?.review_decision) qs.set("review_decision", params.review_decision);
  if (params?.has_review_decision != null) qs.set("has_review_decision", String(params.has_review_decision));
  if (params?.energy_strategy) qs.set("energy_strategy", params.energy_strategy);
  if (params?.siting_friction_category) qs.set("siting_friction_category", params.siting_friction_category);
  if (params?.min_triage_score != null) qs.set("min_triage_score", String(params.min_triage_score));
  if (params?.limit != null) qs.set("limit", String(params.limit));
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson<ProjectCandidateListResponse>(`/project-candidates${query}`);
}

export async function promoteProjectCandidate(
  candidateId: string,
  options: {
    confirm: boolean;
    allow_unresolved_name?: boolean;
    allow_incomplete?: boolean;
  },
): Promise<ProjectCandidatePromotionResponse> {
  const body: ProjectCandidatePromotionRequest = {
    confirm: options.confirm,
    allow_unresolved_name: options.allow_unresolved_name ?? false,
    allow_incomplete: options.allow_incomplete ?? false,
  };
  const res = await fetch(`${BASE_URL}/project-candidates/${candidateId}/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = await res.json().catch(() => null);
  if (!res.ok) {
    // Backend raises HTTPException with detail = summary dict when errors exist
    const detail = json?.detail ?? json ?? {};
    const errors: string[] = Array.isArray(detail.errors) ? detail.errors : [String(json ?? res.statusText)];
    const warnings: string[] = Array.isArray(detail.warnings) ? detail.warnings : [];
    return {
      dry_run: true,
      candidate_id: candidateId,
      promoted: false,
      project_created: false,
      project_updated: false,
      would_promote: false,
      would_create_project: false,
      would_update_project: false,
      evidence_created: 0,
      warnings,
      errors,
      promoted_project_id: null,
    };
  }
  return json as ProjectCandidatePromotionResponse;
}

export async function getConstraintSummary(params?: {
  status?: string;
  verification_status?: string;
  triage_tier?: string;
  review_decision?: string;
  energy_strategy?: string;
  siting_friction_category?: string;
  has_csv_provenance?: boolean;
  limit_top_candidates?: number;
}): Promise<ConstraintSummaryResponse> {
  if (USE_MOCK) {
    await delay();
    return { ...EMPTY_CONSTRAINT_SUMMARY, top_review_priority_candidates: [] };
  }
  const qs = new URLSearchParams();
  setNonEmptyParam(qs, "status", params?.status);
  setNonEmptyParam(qs, "verification_status", params?.verification_status);
  setNonEmptyParam(qs, "triage_tier", params?.triage_tier);
  setNonEmptyParam(qs, "review_decision", params?.review_decision);
  setNonEmptyParam(qs, "energy_strategy", params?.energy_strategy);
  setNonEmptyParam(qs, "siting_friction_category", params?.siting_friction_category);
  if (typeof params?.has_csv_provenance === "boolean") {
    qs.set("has_csv_provenance", params.has_csv_provenance ? "true" : "false");
  }
  if (typeof params?.limit_top_candidates === "number" && Number.isFinite(params.limit_top_candidates)) {
    const limit = Math.max(0, Math.min(50, Math.trunc(params.limit_top_candidates)));
    qs.set("limit_top_candidates", String(limit));
  }
  const query = qs.toString() ? `?${qs.toString()}` : "";
  const raw = await fetchJson<unknown>(`/project-candidates/constraint-summary${query}`);
  return normalizeConstraintSummary(raw);
}

export async function updateProjectCandidateReviewDecision(
  candidateId: string,
  req: ProjectCandidateReviewDecisionRequest,
): Promise<ProjectCandidate> {
  return patchJson<ProjectCandidate>(`/project-candidates/${candidateId}/review-decision`, req);
}

export async function getDiscoveredSourceClaims(params?: {
  claim_type?: string;
  status?: string;
  discovered_source_id?: string;
  limit?: number;
}): Promise<DiscoveredSourceClaimListResponse> {
  if (USE_MOCK) {
    await delay();
    return { items: [], total: 0 };
  }
  const qs = new URLSearchParams();
  if (params?.claim_type) qs.set("claim_type", params.claim_type);
  if (params?.status) qs.set("status", params.status);
  if (params?.discovered_source_id) qs.set("discovered_source_id", params.discovered_source_id);
  if (params?.limit != null) qs.set("limit", String(params.limit));
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson<DiscoveredSourceClaimListResponse>(`/discovered-source-claims${query}`);
}

export async function getDiscoveredSources(): Promise<DiscoveredSource[]> {
  if (USE_MOCK) {
    await delay();
    return [];
  }
  return fetchJson<DiscoveredSource[]>("/discover/sources");
}

export async function getDiscoveredSourceReview(params?: {
  discovery_run_id?: string;
  source_registry_id?: string;
  adapter_id?: string;
  source_type?: string;
  geography?: string;
  status?: string;
  publisher?: string;
  source_url_quality?: string;
  has_weak_url_quality?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<DiscoveredSourceReviewListResponse> {
  if (USE_MOCK) {
    await delay();
    return { items: [], total: 0, limit: params?.limit ?? 50, offset: params?.offset ?? 0, applied_filters: {} };
  }
  const qs = new URLSearchParams();
  setNonEmptyParam(qs, "discovery_run_id", params?.discovery_run_id);
  setNonEmptyParam(qs, "source_registry_id", params?.source_registry_id);
  setNonEmptyParam(qs, "adapter_id", params?.adapter_id);
  setNonEmptyParam(qs, "source_type", params?.source_type);
  setNonEmptyParam(qs, "geography", params?.geography);
  setNonEmptyParam(qs, "status", params?.status);
  setNonEmptyParam(qs, "publisher", params?.publisher);
  setNonEmptyParam(qs, "source_url_quality", params?.source_url_quality);
  setNonEmptyParam(qs, "q", params?.q);
  if (typeof params?.has_weak_url_quality === "boolean") {
    qs.set("has_weak_url_quality", params.has_weak_url_quality ? "true" : "false");
  }
  if (typeof params?.limit === "number" && Number.isFinite(params.limit)) {
    qs.set("limit", String(Math.max(1, Math.min(200, Math.trunc(params.limit)))));
  }
  if (typeof params?.offset === "number" && Number.isFinite(params.offset)) {
    qs.set("offset", String(Math.max(0, Math.trunc(params.offset))));
  }
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson<DiscoveredSourceReviewListResponse>(`/discovered-sources${query}`);
}

export async function getDiscoveredSourceReviewSummary(params?: {
  discovery_run_id?: string;
  source_registry_id?: string;
  adapter_id?: string;
  source_type?: string;
  geography?: string;
  status?: string;
  publisher?: string;
  source_url_quality?: string;
  has_weak_url_quality?: boolean;
  q?: string;
}): Promise<DiscoveredSourceReviewSummaryResponse> {
  if (USE_MOCK) {
    await delay();
    return {
      total: 0,
      counts_by_status: {},
      counts_by_source_type: {},
      counts_by_geography: {},
      counts_by_source_registry_id: {},
      counts_by_adapter_id: {},
      counts_by_discovery_run_id: {},
      weak_url_quality_count: 0,
      weak_url_quality_examples: [],
      applied_filters: {},
    };
  }
  const qs = new URLSearchParams();
  setNonEmptyParam(qs, "discovery_run_id", params?.discovery_run_id);
  setNonEmptyParam(qs, "source_registry_id", params?.source_registry_id);
  setNonEmptyParam(qs, "adapter_id", params?.adapter_id);
  setNonEmptyParam(qs, "source_type", params?.source_type);
  setNonEmptyParam(qs, "geography", params?.geography);
  setNonEmptyParam(qs, "status", params?.status);
  setNonEmptyParam(qs, "publisher", params?.publisher);
  setNonEmptyParam(qs, "source_url_quality", params?.source_url_quality);
  setNonEmptyParam(qs, "q", params?.q);
  if (typeof params?.has_weak_url_quality === "boolean") {
    qs.set("has_weak_url_quality", params.has_weak_url_quality ? "true" : "false");
  }
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson<DiscoveredSourceReviewSummaryResponse>(`/discovered-sources/summary${query}`);
}

export async function getDiscoverDecisions(): Promise<DiscoverDecisions> {
  if (USE_MOCK) {
    await delay();
    return { approved: [], rejected: [], updated_at: null };
  }
  return fetchJson<DiscoverDecisions>("/discover/decisions");
}

export async function postDiscoverDecisions(
  approved_ids: string[],
  rejected_ids: string[],
): Promise<DiscoverDecisions> {
  if (USE_MOCK) {
    await delay();
    return { approved: approved_ids, rejected: rejected_ids, updated_at: new Date().toISOString() };
  }
  return postJson<DiscoverDecisions>("/discover/decisions", { approved_ids, rejected_ids });
}

export async function getManualCaptures(): Promise<ManualCapturesResponse> {
  if (USE_MOCK) {
    await delay();
    return { captures: [], updated_at: null };
  }
  return fetchJson<ManualCapturesResponse>("/discover/manual-captures");
}

export async function postManualCapture(req: ManualCaptureRequest): Promise<ManualCapture> {
  if (USE_MOCK) {
    await delay();
    return {
      discovery_id: req.discovery_id,
      manual_extracted_text: req.manual_extracted_text,
      source_date: req.source_date ?? "",
      notes: req.notes ?? "",
      captured_at: new Date().toISOString(),
      captured_by: req.captured_by ?? "analyst",
      latitude: req.latitude ?? null,
      longitude: req.longitude ?? null,
      coordinate_source: req.coordinate_source ?? "",
      coordinate_confidence: req.coordinate_confidence ?? "",
    };
  }
  return postJson<ManualCapture>("/discover/manual-captures", req);
}

export async function patchProjectCoordinates(
  projectId: string,
  req: ProjectCoordinatesRequest,
): Promise<ProjectDetail> {
  const raw = await patchJson<RawProjectDetail>(`/projects/${projectId}/coordinates`, req);
  // Re-fetch score for complete ProjectDetail (coordinates patch returns detail shape)
  const [rawPhases, rawScore] = await Promise.all([
    fetchJson<RawPhase[]>(`/projects/${projectId}/phases`),
    fetchJson<RawScore>(`/projects/${projectId}/score`),
  ]);
  const phases = rawPhases.map(transformPhase);
  const score = transformScore(rawScore);
  return {
    project_id: raw.id,
    project_name: raw.canonical_name,
    developer: raw.developer ?? null,
    state: raw.state ?? "",
    county: raw.county ?? null,
    latitude: raw.latitude ?? null,
    longitude: raw.longitude ?? null,
    coordinate_status: raw.coordinate_status ?? null,
    coordinate_precision: raw.coordinate_precision ?? null,
    coordinate_source: raw.coordinate_source ?? null,
    coordinate_source_url: raw.coordinate_source_url ?? null,
    coordinate_notes: raw.coordinate_notes ?? null,
    coordinate_confidence: raw.coordinate_confidence ?? null,
    coordinate_updated_at: raw.coordinate_updated_at ?? null,
    coordinate_verified_at: raw.coordinate_verified_at ?? null,
    region_or_rto: "",
    utility: null,
    modeled_primary_load_mw: raw.modeled_primary_load_mw ?? 0,
    headline_load_mw: null,
    optional_expansion_mw: null,
    lifecycle_state: raw.lifecycle_state as LifecycleState,
    risk_tier: deriveRiskTier(rawScore.deadline_probability),
    announce_date: raw.announcement_date,
    phases,
    score,
    data_quality_score: Math.round(score.evidence_quality_score * 100),
    latest_update_date: raw.latest_update_date ?? "",
  };
}

export async function clearProjectCoordinates(projectId: string): Promise<ProjectDetail> {
  const raw = await deleteJson<RawProjectDetail>(`/projects/${projectId}/coordinates`);
  const [rawPhases, rawScore] = await Promise.all([
    fetchJson<RawPhase[]>(`/projects/${projectId}/phases`),
    fetchJson<RawScore>(`/projects/${projectId}/score`),
  ]);
  const phases = rawPhases.map(transformPhase);
  const score = transformScore(rawScore);
  return {
    project_id: raw.id,
    project_name: raw.canonical_name,
    developer: raw.developer ?? null,
    state: raw.state ?? "",
    county: raw.county ?? null,
    latitude: raw.latitude ?? null,
    longitude: raw.longitude ?? null,
    coordinate_status: raw.coordinate_status ?? null,
    coordinate_precision: raw.coordinate_precision ?? null,
    coordinate_source: raw.coordinate_source ?? null,
    coordinate_source_url: raw.coordinate_source_url ?? null,
    coordinate_notes: raw.coordinate_notes ?? null,
    coordinate_confidence: raw.coordinate_confidence ?? null,
    coordinate_updated_at: raw.coordinate_updated_at ?? null,
    coordinate_verified_at: raw.coordinate_verified_at ?? null,
    region_or_rto: "",
    utility: null,
    modeled_primary_load_mw: raw.modeled_primary_load_mw ?? 0,
    headline_load_mw: null,
    optional_expansion_mw: null,
    lifecycle_state: raw.lifecycle_state as LifecycleState,
    risk_tier: deriveRiskTier(rawScore.deadline_probability),
    announce_date: raw.announcement_date,
    phases,
    score,
    data_quality_score: Math.round(score.evidence_quality_score * 100),
    latest_update_date: raw.latest_update_date ?? "",
  };
}

export async function getMissingCoordinateProjects(): Promise<MissingCoordinateProject[]> {
  if (USE_MOCK) {
    await delay();
    return [];
  }
  return fetchJson<MissingCoordinateProject[]>("/projects/missing-coordinates");
}

export async function getProjectCoordinateHistory(projectId: string): Promise<ProjectCoordinateHistoryItem[]> {
  if (USE_MOCK) {
    await delay();
    return [];
  }
  return fetchJson<ProjectCoordinateHistoryItem[]>(`/projects/${projectId}/coordinates/history`);
}

// ---------------------------------------------------------------------------
// Prediction
// ---------------------------------------------------------------------------

export async function getProjectPrediction(id: string): Promise<ProjectPredictionData> {
  if (USE_MOCK) {
    await delay();
    return {
      model_version: "deterministic_baseline_v1",
      prediction_type: "power_delivery_delay",
      p_delay_6mo: 0.18,
      p_delay_12mo: 0.32,
      p_delay_18mo: 0.45,
      risk_tier: "elevated",
      confidence: "medium",
      drivers: [
        { driver: "baseline prior", direction: "unknown", weight: 0.12, evidence: "Fixed prior for a deterministic baseline; not learned from data." },
        { driver: "accepted load > 300 MW", direction: "increases", weight: 0.16, evidence: "Accepted modeled load is 500 MW." },
        { driver: "near-term target without accepted power-path evidence", direction: "increases", weight: 0.18, evidence: "Accepted target energization date is 2026-06-30 (14 months away)." },
        { driver: "accepted power-path support", direction: "decreases", weight: -0.08, evidence: "Accepted power-path evidence indicates an identified path." },
      ],
      missing_inputs: ["utility_named", "region_or_rto_named"],
      method_note: "This is a deterministic baseline, not a trained ML model.",
    };
  }
  return fetchJson<ProjectPredictionData>(`/projects/${id}/prediction`);
}

export async function runProjectPrediction(projectId: string): Promise<ProjectPredictionRunResponse> {
  if (USE_MOCK) {
    await delay(800);
    return {
      project_id: projectId,
      prediction_created: false,
      prediction_updated: true,
      prediction_skipped: false,
      warnings: ["utility_named missing — prediction confidence is reduced"],
      errors: [],
      prediction_id: null,
    };
  }
  const res = await fetch(`${BASE_URL}/projects/${projectId}/prediction/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  const json = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = json?.detail ?? json ?? {};
    const errors: string[] = Array.isArray(detail.errors) ? detail.errors : [String(json ?? res.statusText)];
    const warnings: string[] = Array.isArray(detail.warnings) ? detail.warnings : [];
    return {
      project_id: projectId,
      prediction_created: false,
      prediction_updated: false,
      prediction_skipped: false,
      warnings,
      errors,
      prediction_id: null,
    };
  }
  return json as ProjectPredictionRunResponse;
}

export async function getProjectRiskSignal(id: string): Promise<ProjectRiskSignalData> {
  if (USE_MOCK) {
    await delay();
    return {
      project_id: id,
      risk_signal: "power_path_underresolved",
      risk_signal_score: 0.75,
      risk_signal_tier: "high",
      drivers: [],
      missing_fields: [],
      evidence_summary: { evidence_count: 0, accepted_claim_count: 0, unresolved_claim_count: 0 },
      method: "deterministic_evidence_backed_v1",
    };
  }
  return fetchJson<ProjectRiskSignalData>(`/projects/${id}/risk-signal`);
}
