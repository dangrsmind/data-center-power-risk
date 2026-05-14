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
  ProjectRiskSignalData,
  IntakePacketRequest,
  IntakePacketResponse,
  IngestEvidencePayload,
  IngestEvidenceResponse,
  ProjectCandidateListResponse,
  DiscoveredSource,
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
} from "./types";
import {
  MOCK_PROJECTS,
  MOCK_PROJECT_DETAILS,
} from "./mock";

const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

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
  limit?: number;
}): Promise<ProjectCandidateListResponse> {
  if (USE_MOCK) {
    await delay();
    return { items: [] };
  }
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.state) qs.set("state", params.state);
  if (params?.limit != null) qs.set("limit", String(params.limit));
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson<ProjectCandidateListResponse>(`/project-candidates${query}`);
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
