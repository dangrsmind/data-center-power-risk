import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type {
  IngestSourceType,
  IntakePacketResponse,
  IngestClaimItem,
  IngestClaimResponse,
  IngestClaimAcceptResponse,
  ProjectListItem,
} from "../api/types";
import {
  getProjects,
  postIntakePacket,
  createEvidence,
  createEvidenceClaims,
  linkClaim,
  reviewClaim,
  acceptClaim,
} from "../api/adapter";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SOURCE_TYPE_OPTIONS: { value: IngestSourceType; label: string }[] = [
  { value: "official_filing",    label: "Official Filing" },
  { value: "utility_statement",  label: "Utility Statement" },
  { value: "regulatory_record",  label: "Regulatory Record" },
  { value: "county_record",      label: "County Record" },
  { value: "press",              label: "Press" },
  { value: "developer_statement",label: "Developer Statement" },
  { value: "other",              label: "Other" },
];

const CLAIM_TYPE_LABELS: Record<string, string> = {
  project_name_mention:          "Project Name",
  developer_named:               "Developer",
  operator_named:                "Operator",
  location_state:                "State",
  location_county:               "County",
  utility_named:                 "Utility",
  region_or_rto_named:           "Region / RTO",
  modeled_load_mw:               "Modeled Load (MW)",
  optional_expansion_mw:         "Optional Expansion (MW)",
  phase_name_mention:            "Phase Name",
  target_energization_date:      "Target Energization Date",
  announcement_date:             "Announcement Date",
  latest_update_date:            "Latest Update Date",
  power_path_identified_flag:    "Power Path Identified",
  new_transmission_required_flag:"New Transmission Required",
  new_substation_required_flag:  "New Substation Required",
  onsite_generation_flag:        "Onsite Generation",
  timeline_disruption_signal:    "Timeline Disruption Signal",
  event_support_e2:              "Event Support (E2)",
  event_support_e3:              "Event Support (E3)",
  event_support_e4:              "Event Support (E4)",
};

const SAFE_CLAIM_TYPES = new Set([
  "project_name_mention",
  "developer_named",
  "location_county",
  "location_state",
]);

// Per-claim-type review warnings for non-safe claims.
// Communicate exactly what "not yet accepted" means for each type.
const CLAIM_REVIEW_WARNINGS: Record<string, string> = {
  modeled_load_mw:
    "Headline/stated capacity — requires analyst acceptance before used as modeled load in risk scoring.",
  optional_expansion_mw:
    "Stated expansion capacity — requires analyst acceptance before use in risk scoring.",
  target_energization_date:
    "Stated target date — requires analyst acceptance before used as the project's target energization date.",
  utility_named:
    "Requires analyst acceptance before linking as the project's utility.",
  region_or_rto_named:
    "Requires analyst acceptance before linking as the project's RTO / region.",
  power_path_identified_flag:
    "Power-path infrastructure flag — requires analyst acceptance before affecting the risk signal.",
  new_transmission_required_flag:
    "Transmission infrastructure flag — requires analyst acceptance before affecting the risk signal.",
  new_substation_required_flag:
    "Substation infrastructure flag — requires analyst acceptance before affecting the risk signal.",
  onsite_generation_flag:
    "Onsite generation flag — requires analyst acceptance before affecting the risk signal.",
  timeline_disruption_signal:
    "Timeline disruption signal — requires analyst acceptance before affecting the risk signal.",
  phase_name_mention:
    "Phase identity claim — verify the phase name matches an existing phase before accepting.",
  operator_named:
    "Operator identity claim — verify before accepting.",
  announcement_date:
    "Announced date claim — verify against official records before accepting.",
  latest_update_date:
    "Latest update date claim — verify the date before accepting.",
  event_support_e2:
    "E2 event support signal — requires analyst acceptance before affecting stress scoring.",
  event_support_e3:
    "E3 event support signal — requires analyst acceptance before affecting stress scoring.",
  event_support_e4:
    "E4 event support signal — requires analyst acceptance before affecting stress scoring.",
};

type Stage = "form" | "generating" | "packet" | "creating" | "claims" | "accepting" | "done";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatClaimValue(item: IngestClaimItem): string {
  const v = item.claim_value;
  if (!v) return "";
  const vals = Object.values(v);
  if (vals.length === 0) return "";
  const first = vals[0];
  if (typeof first === "boolean") return first ? "Yes" : "No";
  if (typeof first === "number") return String(first);
  if (typeof first === "string") return first;
  return JSON.stringify(v);
}

function formatClaimValueFromResponse(claim: IngestClaimResponse): string {
  return formatClaimValue({ claim_type: claim.claim_type, claim_value: claim.claim_value });
}

function confidenceColor(confidence?: string): string {
  if (confidence === "high")   return "#22c55e";
  if (confidence === "medium") return "#eab308";
  if (confidence === "low")    return "#ef4444";
  return "var(--text-dim)";
}

function isSafe(claimType: string): boolean {
  return SAFE_CLAIM_TYPES.has(claimType);
}

// ---------------------------------------------------------------------------
// Shared UI primitives
// ---------------------------------------------------------------------------

function StepPill({ n, active, done }: { n: number; active: boolean; done: boolean }) {
  return (
    <div style={{
      width: 26, height: 26,
      borderRadius: "50%",
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 11, fontWeight: 700,
      background: done ? "var(--accent)" : active ? "var(--accent)" : "var(--bg-active)",
      color: (done || active) ? "#fff" : "var(--text-dim)",
      opacity: done ? 0.6 : 1,
      flexShrink: 0,
    }}>
      {done ? "✓" : n}
    </div>
  );
}

function SectionHeader({ n, label, active, done }: { n: number; label: string; active: boolean; done: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
      <StepPill n={n} active={active} done={done} />
      <span style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: active ? "var(--text)" : "var(--text-dim)" }}>
        {label}
      </span>
    </div>
  );
}

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: "var(--bg-surface)",
      border: "1px solid var(--border)",
      borderRadius: 8,
      padding: "16px 20px",
      ...style,
    }}>
      {children}
    </div>
  );
}

function Btn({
  children, onClick, disabled, variant = "primary", style,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "secondary";
  style?: React.CSSProperties;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "8px 18px",
        borderRadius: 5,
        fontSize: 12,
        fontWeight: 600,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.45 : 1,
        background: variant === "primary" ? "var(--accent)" : "var(--bg-active)",
        color: variant === "primary" ? "#fff" : "var(--text)",
        border: variant === "primary" ? "none" : "1px solid var(--border)",
        transition: "opacity 0.15s",
        fontFamily: "inherit",
        ...style,
      }}
    >
      {children}
    </button>
  );
}

function inputStyle(): React.CSSProperties {
  return {
    background: "var(--bg)",
    border: "1px solid var(--border)",
    borderRadius: 4,
    color: "var(--text)",
    fontSize: 12,
    padding: "6px 10px",
    fontFamily: "inherit",
    width: "100%",
    boxSizing: "border-box",
  };
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div style={{
      padding: "10px 14px",
      background: "var(--risk-high-bg)",
      border: "1px solid var(--risk-high)",
      borderRadius: 5,
      color: "var(--risk-high)",
      fontSize: 12,
      marginBottom: 16,
    }}>
      {message}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Claim row used in both Step 4 and Step 6
// ---------------------------------------------------------------------------

function ClaimRow({
  claimType,
  claimValueStr,
  confidence,
  checked,
  onChange,
  warning,
}: {
  claimType: string;
  claimValueStr: string;
  confidence?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  warning?: string;
}) {
  const safe = isSafe(claimType);
  return (
    <label style={{
      display: "flex",
      alignItems: "flex-start",
      gap: 10,
      padding: "8px 10px",
      borderRadius: 4,
      cursor: "pointer",
      background: checked ? "var(--bg-active)" : "transparent",
      transition: "background 0.1s",
    }}>
      <input
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
        style={{ marginTop: 2, flexShrink: 0, accentColor: "var(--accent)" }}
      />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text)" }}>
            {CLAIM_TYPE_LABELS[claimType] ?? claimType}
          </span>
          {confidence && (
            <span style={{ fontSize: 10, fontWeight: 700, color: confidenceColor(confidence), textTransform: "uppercase", letterSpacing: "0.05em" }}>
              {confidence}
            </span>
          )}
          {!safe && (
            <span style={{ fontSize: 10, color: "#ca8a04", background: "rgba(234,179,8,0.1)", border: "1px solid rgba(234,179,8,0.3)", borderRadius: 3, padding: "1px 5px" }}>
              ⚠ Review before accepting
            </span>
          )}
        </div>
        <span style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: '"JetBrains Mono", monospace' }}>
          {claimValueStr}
        </span>
        {warning && (
          <span style={{ fontSize: 11, color: "#ca8a04" }}>{warning}</span>
        )}
      </div>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function IngestPage() {
  // Projects list
  const [projects, setProjects]           = useState<ProjectListItem[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);

  // Form fields
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [sourceType, setSourceType]       = useState<IngestSourceType>("press");
  const [sourceUrl, setSourceUrl]         = useState("");
  const [sourceDate, setSourceDate]       = useState("");
  const [title, setTitle]                 = useState("");
  const [evidenceText, setEvidenceText]   = useState("");

  // Workflow state
  const [stage, setStage]                 = useState<Stage>("form");
  const [error, setError]                 = useState<string | null>(null);

  // Packet
  const [packet, setPacket]               = useState<IntakePacketResponse | null>(null);
  const [selectedPacketClaims, setSelectedPacketClaims] = useState<Set<number>>(new Set());
  const [showDebug, setShowDebug]         = useState(false);

  // Created claims
  const [evidenceId, setEvidenceId]       = useState<string | null>(null);
  const [createdClaims, setCreatedClaims] = useState<IngestClaimResponse[]>([]);
  const [selectedCreatedClaims, setSelectedCreatedClaims] = useState<Set<string>>(new Set());

  // Results
  const [acceptResults, setAcceptResults] = useState<IngestClaimAcceptResponse[]>([]);
  const [skippedClaimIds, setSkippedClaimIds] = useState<Set<string>>(new Set());

  // Load projects on mount
  useEffect(() => {
    getProjects()
      .then(p => setProjects(p))
      .catch(() => {/* silently fail — user can still type */})
      .finally(() => setProjectsLoading(false));
  }, []);

  // When packet loads, pre-select safe claims
  useEffect(() => {
    if (!packet) return;
    const safe = new Set(
      packet.claims_payload.claims
        .map((c, i) => (isSafe(c.claim_type) ? i : -1))
        .filter(i => i >= 0),
    );
    setSelectedPacketClaims(safe);
  }, [packet]);

  // When created claims load, pre-select safe ones
  useEffect(() => {
    if (createdClaims.length === 0) return;
    const safe = new Set(
      createdClaims
        .filter(c => isSafe(c.claim_type))
        .map(c => c.claim_id),
    );
    setSelectedCreatedClaims(safe);
  }, [createdClaims]);

  // ── Step 3: Generate packet ────────────────────────────────────────────────
  async function handleGeneratePacket() {
    if (!evidenceText.trim()) return;
    setError(null);
    setStage("generating");
    try {
      const req = {
        source_type: sourceType,
        evidence_text: evidenceText,
        ...(sourceUrl.trim()  && { source_url:  sourceUrl.trim() }),
        ...(sourceDate.trim() && { source_date: sourceDate.trim() }),
        ...(title.trim()      && { title:        title.trim() }),
        ...(selectedProjectId && { project_id:   selectedProjectId }),
      };
      const result = await postIntakePacket(req);
      setPacket(result);
      setStage("packet");
    } catch (e) {
      setError(String(e));
      setStage("form");
    }
  }

  // ── Step 5: Create evidence + selected claims ──────────────────────────────
  async function handleCreateEvidence() {
    if (!packet) return;
    setError(null);
    setStage("creating");
    try {
      const evResp = await createEvidence(packet.evidence_payload);
      const selectedClaims = packet.claims_payload.claims.filter((_, i) =>
        selectedPacketClaims.has(i),
      );
      const claimsResp = await createEvidenceClaims(evResp.evidence_id, selectedClaims);
      setEvidenceId(claimsResp.evidence_id);
      setCreatedClaims(claimsResp.created_claims);
      setStage("claims");
    } catch (e) {
      setError(String(e));
      setStage("packet");
    }
  }

  // ── Step 7: Link → Review → Accept selected claims ─────────────────────────
  async function handleAcceptClaims() {
    if (!evidenceId || !selectedProjectId) return;
    setError(null);
    setStage("accepting");

    const toAccept = createdClaims.filter(c => selectedCreatedClaims.has(c.claim_id));
    const toSkip   = createdClaims.filter(c => !selectedCreatedClaims.has(c.claim_id));
    const reviewer = "analyst";

    try {
      const results = await Promise.all(
        toAccept.map(claim =>
          linkClaim(claim.claim_id, selectedProjectId)
            .then(() => reviewClaim(claim.claim_id, reviewer))
            .then(() => acceptClaim(claim.claim_id, reviewer)),
        ),
      );
      setAcceptResults(results);
      setSkippedClaimIds(new Set(toSkip.map(c => c.claim_id)));
      setStage("done");
    } catch (e) {
      setError(String(e));
      setStage("claims");
    }
  }

  function togglePacketClaim(i: number) {
    setSelectedPacketClaims(prev => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i); else next.add(i);
      return next;
    });
  }

  function toggleCreatedClaim(id: string) {
    setSelectedCreatedClaims(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  const canGenerate  = evidenceText.trim().length > 0;
  const canCreate    = selectedPacketClaims.size > 0;
  const canAccept    = selectedCreatedClaims.size > 0 && selectedProjectId.length > 0;
  const selectedProject = projects.find(p => p.project_id === selectedProjectId);

  const stepsDone: Record<Stage, number> = {
    form:       0,
    generating: 2,
    packet:     2,
    creating:   4,
    claims:     5,
    accepting:  7,
    done:       8,
  };
  const doneUpTo = stepsDone[stage];

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>

      {/* Page header */}
      <div style={{
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-surface)",
        padding: "12px 24px",
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text)" }}>Ingestion Workbench</div>

        {/* Step indicator */}
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          {[
            "Select Project",
            "Source Metadata",
            "Generate Packet",
            "Select Claims",
            "Create Evidence",
            "Review Claims",
            "Accept",
            "Done",
          ].map((label, idx) => {
            const n = idx + 1;
            const active = stage === "form" ? n <= 2 : stage === "packet" ? n <= 4 : stage === "claims" ? n <= 7 : stage === "done" ? n === 8 : false;
            const done = n <= doneUpTo;
            return (
              <div key={n} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <div title={label} style={{
                  width: 24, height: 24,
                  borderRadius: "50%",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 10, fontWeight: 700,
                  background: done ? "var(--accent)" : active ? "rgba(96,165,250,0.25)" : "var(--bg-active)",
                  color: done ? "#fff" : active ? "var(--accent)" : "var(--text-dim)",
                  border: active && !done ? "1px solid var(--accent)" : "none",
                  flexShrink: 0,
                  cursor: "default",
                }}>
                  {done ? "✓" : n}
                </div>
                {idx < 7 && (
                  <div style={{ width: 14, height: 1, background: n <= doneUpTo ? "var(--accent)" : "var(--border)" }} />
                )}
              </div>
            );
          })}
          <span style={{ marginLeft: 8, fontSize: 11, color: "var(--text-dim)" }}>
            {stage === "generating" ? "Generating…" : stage === "creating" ? "Creating…" : stage === "accepting" ? "Processing…" : ""}
          </span>
        </div>
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflow: "auto", padding: "24px", display: "flex", flexDirection: "column", gap: 24, maxWidth: 780 }}>

        {error && <ErrorBanner message={error} />}

        {/* ─── Steps 1–2: Form ──────────────────────────────────────────────── */}
        {(stage === "form" || stage === "generating" || stage === "packet" || stage === "creating") && (
          <>
            {/* Step 1 */}
            <Card>
              <SectionHeader n={1} label="Select Project" active={stage === "form"} done={doneUpTo >= 1} />
              <select
                value={selectedProjectId}
                onChange={e => setSelectedProjectId(e.target.value)}
                disabled={stage !== "form" && stage !== "packet"}
                style={{ ...inputStyle(), maxWidth: 420 }}
              >
                <option value="">— Select a project —</option>
                {projectsLoading && <option disabled>Loading…</option>}
                {projects.map(p => (
                  <option key={p.project_id} value={p.project_id}>
                    {p.project_name} ({p.state})
                  </option>
                ))}
              </select>
              {!selectedProjectId && stage === "form" && (
                <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 8 }}>
                  Select a project to enable link suggestions in the intake packet.
                </div>
              )}
            </Card>

            {/* Step 2 */}
            <Card>
              <SectionHeader n={2} label="Source Metadata" active={stage === "form"} done={doneUpTo >= 2} />
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div>
                    <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>Source Type *</label>
                    <select
                      value={sourceType}
                      onChange={e => setSourceType(e.target.value as IngestSourceType)}
                      disabled={stage !== "form" && stage !== "packet"}
                      style={inputStyle()}
                    >
                      {SOURCE_TYPE_OPTIONS.map(o => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>Source Date</label>
                    <input
                      type="date"
                      value={sourceDate}
                      onChange={e => setSourceDate(e.target.value)}
                      disabled={stage !== "form" && stage !== "packet"}
                      style={inputStyle()}
                    />
                  </div>
                </div>
                <div>
                  <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>Source URL</label>
                  <input
                    type="url"
                    value={sourceUrl}
                    onChange={e => setSourceUrl(e.target.value)}
                    placeholder="https://…"
                    disabled={stage !== "form" && stage !== "packet"}
                    style={inputStyle()}
                  />
                </div>
                <div>
                  <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>Title</label>
                  <input
                    type="text"
                    value={title}
                    onChange={e => setTitle(e.target.value)}
                    placeholder="Source title or headline"
                    disabled={stage !== "form" && stage !== "packet"}
                    style={inputStyle()}
                  />
                </div>
                <div>
                  <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>Evidence Text *</label>
                  <textarea
                    value={evidenceText}
                    onChange={e => setEvidenceText(e.target.value)}
                    placeholder="Paste the full source text here. The system will extract claims automatically."
                    rows={7}
                    disabled={stage !== "form" && stage !== "packet"}
                    style={{ ...inputStyle(), resize: "vertical", lineHeight: 1.5 }}
                  />
                </div>

                {stage === "form" && (
                  <div>
                    <Btn onClick={handleGeneratePacket} disabled={!canGenerate || stage !== "form"}>
                      Generate Intake Packet →
                    </Btn>
                  </div>
                )}
                {stage === "generating" && (
                  <div style={{ fontSize: 12, color: "var(--text-dim)" }}>Generating intake packet…</div>
                )}
              </div>
            </Card>
          </>
        )}

        {/* ─── Steps 3–4: Packet review + claim selection ────────────────────── */}
        {(stage === "packet" || stage === "creating") && packet && (
          <>
            {/* Step 3: Intake Packet */}
            <Card>
              <SectionHeader n={3} label="Intake Packet" active={stage === "packet"} done={doneUpTo >= 3} />

              {/* Evidence draft summary */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 1, background: "var(--border)", border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden", marginBottom: 12 }}>
                {[
                  { label: "Source Type",  value: packet.evidence_payload.source_type },
                  { label: "Source Date",  value: packet.evidence_payload.source_date ?? "—" },
                  { label: "Title",        value: packet.evidence_payload.title ?? "—" },
                ].map(item => (
                  <div key={item.label} style={{ background: "var(--bg)", padding: "10px 12px" }}>
                    <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", marginBottom: 3 }}>{item.label}</div>
                    <div style={{ fontSize: 12, color: "var(--text)" }}>{item.value}</div>
                  </div>
                ))}
              </div>

              {/* Warnings */}
              {packet.warnings.length > 0 && (
                <div style={{ marginBottom: 10 }}>
                  {packet.warnings.map((w, i) => (
                    <div key={i} style={{ fontSize: 11, color: "#ca8a04", display: "flex", gap: 6, marginBottom: 3 }}>
                      <span>⚠</span><span>{w}</span>
                    </div>
                  ))}
                </div>
              )}
              {packet.uncertainties.length > 0 && (
                <div style={{ marginBottom: 10 }}>
                  {packet.uncertainties.map((u, i) => (
                    <div key={i} style={{ fontSize: 11, color: "var(--text-dim)", display: "flex", gap: 6, marginBottom: 3 }}>
                      <span>?</span><span>{u}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Debug collapsible */}
              <button
                onClick={() => setShowDebug(d => !d)}
                style={{ fontSize: 11, color: "var(--text-dim)", background: "none", border: "none", cursor: "pointer", padding: 0, marginTop: 4 }}
              >
                {showDebug ? "▾ Hide raw packet" : "▸ Show raw packet (debug)"}
              </button>
              {showDebug && (
                <pre style={{
                  marginTop: 8,
                  fontSize: 10,
                  color: "var(--text-muted)",
                  background: "var(--bg)",
                  border: "1px solid var(--border)",
                  borderRadius: 4,
                  padding: "10px 12px",
                  overflow: "auto",
                  maxHeight: 220,
                  lineHeight: 1.5,
                }}>
                  {JSON.stringify(packet, null, 2)}
                </pre>
              )}
            </Card>

            {/* Step 4: Select claims */}
            <Card>
              <SectionHeader n={4} label="Select Claims to Create" active={stage === "packet"} done={doneUpTo >= 4} />

              {packet.claims_payload.claims.length === 0 ? (
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  No claims were extracted from this evidence text.
                </div>
              ) : (
                <>
                  <div style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 10 }}>
                    {selectedPacketClaims.size} of {packet.claims_payload.claims.length} claims selected.
                    Safe project-level claims are pre-checked.
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    {packet.claims_payload.claims.map((claim, i) => (
                      <ClaimRow
                        key={i}
                        claimType={claim.claim_type}
                        claimValueStr={formatClaimValue(claim)}
                        confidence={claim.confidence}
                        checked={selectedPacketClaims.has(i)}
                        onChange={v => { if (v) setSelectedPacketClaims(p => new Set([...p, i])); else togglePacketClaim(i); }}
                        warning={!isSafe(claim.claim_type)
                          ? (CLAIM_REVIEW_WARNINGS[claim.claim_type] ?? "Review required before accepting this claim.")
                          : undefined}
                      />
                    ))}
                  </div>

                  {stage === "packet" && (
                    <div style={{ marginTop: 14 }}>
                      <Btn onClick={handleCreateEvidence} disabled={!canCreate}>
                        Create Evidence + {selectedPacketClaims.size} Claim{selectedPacketClaims.size !== 1 ? "s" : ""} →
                      </Btn>
                      {!selectedProjectId && (
                        <div style={{ fontSize: 11, color: "#ca8a04", marginTop: 6 }}>
                          ⚠ No project selected — claims will be created but cannot be auto-linked.
                        </div>
                      )}
                    </div>
                  )}
                  {stage === "creating" && (
                    <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 10 }}>Creating evidence and claims…</div>
                  )}
                </>
              )}
            </Card>
          </>
        )}

        {/* ─── Steps 6–7: Created claims + accept ────────────────────────────── */}
        {(stage === "claims" || stage === "accepting") && evidenceId && (
          <>
            {/* Step 5 (success badge) */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.25)", borderRadius: 6 }}>
              <span style={{ color: "#22c55e", fontSize: 14 }}>✓</span>
              <span style={{ fontSize: 12, color: "var(--text)" }}>
                Evidence created · ID:{" "}
                <span style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 11 }}>{evidenceId}</span>
              </span>
            </div>

            {/* Step 6 */}
            <Card>
              <SectionHeader n={6} label="Review Created Claims" active={stage === "claims"} done={doneUpTo >= 6} />
              <div style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 10 }}>
                {selectedCreatedClaims.size} of {createdClaims.length} claims selected for acceptance.
                Select only claims you have verified are correct. Unselected claims will remain unlinked.
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {createdClaims.map(claim => (
                  <ClaimRow
                    key={claim.claim_id}
                    claimType={claim.claim_type}
                    claimValueStr={formatClaimValueFromResponse(claim)}
                    confidence={claim.confidence}
                    checked={selectedCreatedClaims.has(claim.claim_id)}
                    onChange={v => { if (v) setSelectedCreatedClaims(p => new Set([...p, claim.claim_id])); else toggleCreatedClaim(claim.claim_id); }}
                    warning={
                      claim.is_contradictory
                        ? "⚠ Backend flagged this claim as contradictory."
                        : !isSafe(claim.claim_type)
                        ? (CLAIM_REVIEW_WARNINGS[claim.claim_type] ?? "Review required before accepting this claim.")
                        : undefined
                    }
                  />
                ))}
              </div>
            </Card>

            {/* Step 7 */}
            <Card>
              <SectionHeader n={7} label="Link, Review, and Accept" active={stage === "claims"} done={doneUpTo >= 7} />
              {!selectedProjectId && (
                <div style={{ fontSize: 11, color: "#ef4444", marginBottom: 10 }}>
                  No project selected. Cannot link claims without a project target.
                </div>
              )}
              {stage === "claims" && (
                <>
                  <div style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 12 }}>
                    Each selected claim will be linked to <strong style={{ color: "var(--text)" }}>{selectedProject?.project_name ?? "the selected project"}</strong>,
                    marked as accepted candidate, and accepted. This action writes data into the project record.
                  </div>
                  <Btn onClick={handleAcceptClaims} disabled={!canAccept}>
                    Link, Review, and Accept {selectedCreatedClaims.size} Selected Claim{selectedCreatedClaims.size !== 1 ? "s" : ""}
                  </Btn>
                </>
              )}
              {stage === "accepting" && (
                <div style={{ fontSize: 12, color: "var(--text-dim)" }}>Processing claims…</div>
              )}
            </Card>
          </>
        )}

        {/* ─── Step 8: Done ───────────────────────────────────────────────────── */}
        {stage === "done" && evidenceId && (
          <Card>
            <SectionHeader n={8} label="Done" active={true} done={false} />

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 20, color: "#22c55e" }}>✓</span>
                <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text)" }}>Ingestion complete</span>
              </div>

              {/* Summary grid */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 1, background: "var(--border)", border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden" }}>
                {[
                  { label: "Evidence ID",      value: evidenceId.slice(0, 8) + "…" },
                  { label: "Accepted Claims",   value: String(acceptResults.length), color: "#22c55e" },
                  { label: "Skipped Claims",    value: String(skippedClaimIds.size), color: skippedClaimIds.size > 0 ? "#ca8a04" : "var(--text)" },
                ].map(item => (
                  <div key={item.label} style={{ background: "var(--bg)", padding: "12px 14px" }}>
                    <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", marginBottom: 4 }}>{item.label}</div>
                    <div style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 16, fontWeight: 700, color: item.color ?? "var(--text)" }}>
                      {item.value}
                    </div>
                  </div>
                ))}
              </div>

              {/* Accepted claim list */}
              {acceptResults.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", marginBottom: 6 }}>Accepted</div>
                  {acceptResults.map(r => (
                    <div key={r.claim_id} style={{ fontSize: 12, color: "var(--text)", display: "flex", gap: 8, marginBottom: 4 }}>
                      <span style={{ color: "#22c55e" }}>✓</span>
                      <span style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 11 }}>
                        {createdClaims.find(c => c.claim_id === r.claim_id)?.claim_type ?? r.claim_id.slice(0, 8)}
                      </span>
                      {r.entity_label && (
                        <span style={{ color: "var(--text-muted)" }}>→ {r.entity_label}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Skipped claim list */}
              {skippedClaimIds.size > 0 && (
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", marginBottom: 6 }}>Skipped (not linked or accepted)</div>
                  {createdClaims.filter(c => skippedClaimIds.has(c.claim_id)).map(c => (
                    <div key={c.claim_id} style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", gap: 8, marginBottom: 4 }}>
                      <span>–</span>
                      <span style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 11 }}>{c.claim_type}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Link to project */}
              {selectedProjectId && (
                <div style={{ marginTop: 4 }}>
                  <Link
                    to={`/projects/${selectedProjectId}`}
                    style={{ fontSize: 12, color: "var(--accent)", textDecoration: "none", fontWeight: 600 }}
                  >
                    View {selectedProject?.project_name ?? "project"} Evidence Signal →
                  </Link>
                </div>
              )}

              {/* Start another */}
              <div>
                <Btn
                  variant="secondary"
                  onClick={() => {
                    setStage("form");
                    setPacket(null);
                    setEvidenceId(null);
                    setCreatedClaims([]);
                    setAcceptResults([]);
                    setSkippedClaimIds(new Set());
                    setSelectedPacketClaims(new Set());
                    setSelectedCreatedClaims(new Set());
                    setEvidenceText("");
                    setTitle("");
                    setSourceUrl("");
                    setSourceDate("");
                    setError(null);
                  }}
                >
                  Ingest another source
                </Btn>
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
