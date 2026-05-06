import { useEffect, useState, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import type {
  ProjectDetail,
  ProjectEnrichmentData,
  ProjectEventsData,
  ProjectStressData,
  ProjectHistoryData,
  ProjectEvidenceData,
  ProjectRiskSignalData,
} from "../api/types";
import {
  getProject,
  getProjectEnrichment,
  getProjectEvents,
  getProjectStress,
  getProjectHistory,
  getProjectEvidence,
  getProjectRiskSignal,
  patchProjectCoordinates,
} from "../api/adapter";
import { ProjectDetailPanel } from "../components/detail/ProjectDetailPanel";
import { PhaseList } from "../components/detail/PhaseList";
import { ScorePanel } from "../components/detail/ScorePanel";
import { EventsTab } from "../components/detail/EventsTab";
import { StressTab } from "../components/detail/StressTab";
import { HistoryTab } from "../components/detail/HistoryTab";
import { EvidenceTab } from "../components/detail/EvidenceTab";
import { RiskSignalTab } from "../components/detail/RiskSignalTab";

type TabId = "overview" | "phases" | "score" | "events" | "stress" | "history" | "evidence" | "risk-signal";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview",     label: "Overview" },
  { id: "phases",       label: "Phases" },
  { id: "score",        label: "Score" },
  { id: "events",       label: "Events" },
  { id: "stress",       label: "Stress" },
  { id: "history",      label: "History" },
  { id: "evidence",     label: "Evidence" },
  { id: "risk-signal",  label: "Evidence Signal" },
];

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();

  const [project,     setProject]     = useState<ProjectDetail | null>(null);
  const [enrichment,  setEnrichment]  = useState<ProjectEnrichmentData | null>(null);
  const [events,      setEvents]      = useState<ProjectEventsData | null>(null);
  const [stress,      setStress]      = useState<ProjectStressData | null>(null);
  const [history,     setHistory]     = useState<ProjectHistoryData | null>(null);
  const [evidence,    setEvidence]    = useState<ProjectEvidenceData | null>(null);
  const [riskSignal,  setRiskSignal]  = useState<ProjectRiskSignalData | null>(null);

  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);
  const [tab,     setTab]     = useState<TabId>("overview");

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setProject(null);
    setEnrichment(null);
    setEvents(null);
    setStress(null);
    setHistory(null);
    setEvidence(null);
    setRiskSignal(null);
    setError(null);

    Promise.all([
      getProject(id),
      getProjectEnrichment(id),
      getProjectEvents(id),
      getProjectStress(id),
      getProjectHistory(id),
      getProjectEvidence(id),
      getProjectRiskSignal(id),
    ])
      .then(([proj, enrich, evts, str, hist, evid, rs]) => {
        setProject(proj);
        setEnrichment(enrich);
        setEvents(evts);
        setStress(str);
        setHistory(hist);
        setEvidence(evid);
        setRiskSignal(rs);
      })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Breadcrumb + tabs header */}
      <div style={{
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-surface)",
        flexShrink: 0,
      }}>
        <div style={{ padding: "10px 20px 0", display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
            <Link to="/" style={{ color: "var(--accent)", textDecoration: "none" }}>
              Projects
            </Link>
            {" / "}
            <span>{project?.project_name ?? id}</span>
          </div>

          <div style={{ display: "flex", gap: 0 }}>
            {TABS.map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                style={{
                  padding: "6px 14px",
                  fontSize: 12,
                  fontWeight: tab === t.id ? 600 : 400,
                  color: tab === t.id ? "var(--text)" : "var(--text-muted)",
                  background: "transparent",
                  border: "none",
                  borderBottom: tab === t.id ? "2px solid var(--accent)" : "2px solid transparent",
                  marginBottom: -1,
                  cursor: "pointer",
                  transition: "color 0.15s",
                }}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: "auto", padding: "20px" }}>
        {loading && (
          <div style={{ color: "var(--text-muted)", padding: 20 }}>Loading project…</div>
        )}
        {error && (
          <div style={{
            padding: "10px 14px",
            background: "var(--risk-high-bg)",
            border: "1px solid var(--risk-high)",
            borderRadius: 5,
            color: "var(--risk-high)",
            fontSize: 12,
          }}>
            {error}
          </div>
        )}
        {project && !loading && (
          <>
            {tab === "overview" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 24, maxWidth: 900 }}>
                <ProjectDetailPanel project={project} />
                <InfrastructureContextCard enrichment={enrichment} />
                <CoordinateEditCard
                  project={project}
                  onSaved={(updated) => setProject(updated)}
                />
                <SectionCard title="Model Score Summary">
                  <QuickScoreRow project={project} />
                  <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 6 }}>
                    Produced by the ML scoring model. May differ from the Evidence-Based Risk Signal.
                  </div>
                </SectionCard>
                <SectionCard title="Phase Overview">
                  <PhaseList phases={project.phases} />
                </SectionCard>
              </div>
            )}

            {tab === "phases" && (
              <div style={{ maxWidth: 900 }}>
                <PhaseList phases={project.phases} />
              </div>
            )}

            {tab === "score" && (
              <div style={{ maxWidth: 680 }}>
                <ScorePanel score={project.score} />
              </div>
            )}

            {tab === "events" && (
              <div style={{ maxWidth: 1000 }}>
                <SectionCard title={`Events (${events?.events.length ?? 0})`}>
                  <EventsTab events={events?.events ?? []} />
                </SectionCard>
              </div>
            )}

            {tab === "stress" && stress && (
              <div style={{ maxWidth: 900 }}>
                <StressTab data={stress} />
              </div>
            )}

            {tab === "history" && (
              <div style={{ maxWidth: 1100 }}>
                <SectionCard title={`History (${history?.history.length ?? 0} records)`}>
                  <HistoryTab history={history?.history ?? []} />
                </SectionCard>
              </div>
            )}

            {tab === "evidence" && (
              <div style={{ maxWidth: 1000 }}>
                <SectionCard title={`Evidence (${evidence?.evidence.length ?? 0} items)`}>
                  <EvidenceTab evidence={evidence?.evidence ?? []} />
                </SectionCard>
              </div>
            )}

            {tab === "risk-signal" && riskSignal && (
              <div style={{ maxWidth: 820 }}>
                <RiskSignalTab data={riskSignal} />
              </div>
            )}
            {tab === "risk-signal" && !riskSignal && !loading && (
              <div style={{ color: "var(--text-muted)", fontSize: 13 }}>No risk signal data available.</div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function InfrastructureContextCard({ enrichment }: { enrichment: ProjectEnrichmentData | null }) {
  const hasData = enrichment && (enrichment.utility || enrichment.confidence || enrichment.source);
  return (
    <SectionCard title="Infrastructure Context">
      <div style={{ background: "var(--bg-active)", border: "1px solid var(--border)", borderRadius: 6, padding: "14px 16px" }}>
        {!hasData ? (
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            No infrastructure context available yet.
          </span>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
            <div>
              <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", fontWeight: 700, marginBottom: 4 }}>
                Utility Territory
              </div>
              <div style={{ fontSize: 13, color: "var(--text)" }}>
                {enrichment.utility ?? "—"}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", fontWeight: 700, marginBottom: 4 }}>
                Confidence
              </div>
              <div style={{ fontSize: 13, color: enrichment.confidence === "high" ? "#22c55e" : enrichment.confidence === "medium" ? "#fbbf24" : "var(--text)" }}>
                {enrichment.confidence ?? "—"}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", fontWeight: 700, marginBottom: 4 }}>
                Source
              </div>
              <div style={{ fontSize: 13, fontFamily: '"JetBrains Mono", monospace', color: "var(--text-muted)" }}>
                {enrichment.source ?? "—"}
              </div>
            </div>
          </div>
        )}
      </div>
    </SectionCard>
  );
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <h3 style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)" }}>
        {title}
      </h3>
      {children}
    </div>
  );
}

function CoordinateEditCard({
  project,
  onSaved,
}: {
  project: ProjectDetail;
  onSaved: (updated: ProjectDetail) => void;
}) {
  const [editing, setEditing]   = useState(false);
  const [latStr, setLatStr]     = useState(project.latitude != null ? String(project.latitude) : "");
  const [lonStr, setLonStr]     = useState(project.longitude != null ? String(project.longitude) : "");
  const [coordSource, setCoordSource]         = useState("");
  const [coordConfidence, setCoordConfidence] = useState("");
  const [saving, setSaving]     = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [success, setSuccess]   = useState(false);
  const latRef = useRef<HTMLInputElement>(null);

  // Reset local form when project changes (e.g. navigating between projects)
  useEffect(() => {
    setLatStr(project.latitude != null ? String(project.latitude) : "");
    setLonStr(project.longitude != null ? String(project.longitude) : "");
    setEditing(false);
    setError(null);
    setSuccess(false);
  }, [project.project_id]);

  useEffect(() => {
    if (editing) latRef.current?.focus();
  }, [editing]);

  async function handleSave() {
    const lat = parseFloat(latStr);
    const lon = parseFloat(lonStr);
    if (isNaN(lat) || lat < -90 || lat > 90) {
      setError("Latitude must be a number between -90 and 90."); return;
    }
    if (isNaN(lon) || lon < -180 || lon > 180) {
      setError("Longitude must be a number between -180 and 180."); return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await patchProjectCoordinates(project.project_id, {
        latitude: lat,
        longitude: lon,
        coordinate_source: coordSource.trim() || "analyst_manual_entry",
        coordinate_confidence: coordConfidence.trim(),
      });
      onSaved(updated);
      setEditing(false);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 4000);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  const hasCoords = project.latitude != null && project.longitude != null;

  const inp: React.CSSProperties = {
    boxSizing: "border-box", width: "100%",
    background: "var(--bg)", border: "1px solid var(--border)",
    borderRadius: 4, padding: "6px 10px",
    fontSize: 12, color: "var(--text)",
  };

  return (
    <SectionCard title="Coordinates">
      <div style={{ background: "var(--bg-active)", border: "1px solid var(--border)", borderRadius: 6, padding: "14px 16px" }}>
        {!editing ? (
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{ flex: 1 }}>
              {hasCoords ? (
                <div style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 13, color: "var(--text)" }}>
                  {project.latitude!.toFixed(6)}, {project.longitude!.toFixed(6)}
                </div>
              ) : (
                <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  No coordinates set — this project will not appear on the map.
                </span>
              )}
              {success && (
                <div style={{ fontSize: 11, color: "#22c55e", marginTop: 4 }}>✓ Coordinates saved.</div>
              )}
            </div>
            <button
              onClick={() => { setEditing(true); setError(null); }}
              style={{
                fontSize: 11, fontWeight: 600, padding: "5px 14px", borderRadius: 4,
                border: "1px solid var(--border)", background: "transparent",
                color: "var(--accent)", cursor: "pointer", whiteSpace: "nowrap",
              }}
            >
              {hasCoords ? "Edit" : "+ Set coordinates"}
            </button>
          </div>
        ) : (
          <div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10, marginBottom: 10 }}>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Latitude</div>
                <input ref={latRef} type="number" step="any" value={latStr}
                  onChange={e => setLatStr(e.target.value)}
                  placeholder="e.g. 33.749" style={inp} />
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Longitude</div>
                <input type="number" step="any" value={lonStr}
                  onChange={e => setLonStr(e.target.value)}
                  placeholder="e.g. -84.388" style={inp} />
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Source</div>
                <input type="text" value={coordSource}
                  onChange={e => setCoordSource(e.target.value)}
                  placeholder="e.g. county parcel map" style={inp} />
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Confidence</div>
                <select value={coordConfidence}
                  onChange={e => setCoordConfidence(e.target.value)}
                  style={{ ...inp, cursor: "pointer", color: coordConfidence ? "var(--text)" : "var(--text-dim)" }}
                >
                  <option value="">— select —</option>
                  <option value="parcel">Parcel (high)</option>
                  <option value="city">City centroid</option>
                  <option value="county">County centroid</option>
                  <option value="inferred">Inferred</option>
                </select>
              </div>
            </div>
            {error && (
              <div style={{ fontSize: 11, color: "#ef4444", background: "rgba(239,68,68,0.08)", borderRadius: 3, padding: "5px 8px", marginBottom: 8 }}>
                {error}
              </div>
            )}
            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={handleSave}
                disabled={saving || !latStr.trim() || !lonStr.trim()}
                style={{
                  fontSize: 12, fontWeight: 600, padding: "5px 16px", borderRadius: 4,
                  background: saving || !latStr.trim() || !lonStr.trim() ? "rgba(34,197,94,0.2)" : "rgba(34,197,94,0.12)",
                  border: "1px solid rgba(34,197,94,0.45)", color: "#22c55e",
                  cursor: saving || !latStr.trim() || !lonStr.trim() ? "default" : "pointer",
                }}
              >
                {saving ? "Saving…" : "Save coordinates"}
              </button>
              <button
                onClick={() => { setEditing(false); setError(null); }}
                style={{
                  fontSize: 12, padding: "5px 14px", borderRadius: 4,
                  background: "transparent", border: "1px solid var(--border)",
                  color: "var(--text-muted)", cursor: "pointer",
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </SectionCard>
  );
}

function QuickScoreRow({ project }: { project: ProjectDetail }) {
  const s = project.score;
  const items = [
    { label: "Q-Hazard",        value: `${(s.current_hazard * 100).toFixed(1)}%`,        highlight: s.current_hazard > 0.07 },
    { label: "Deadline P",      value: `${(s.deadline_probability * 100).toFixed(1)}%`,  highlight: s.deadline_probability > 0.2 },
    { label: "Project Stress",  value: s.project_stress_score.toFixed(2),                highlight: s.project_stress_score > 0.6 },
    { label: "Regional Stress", value: s.regional_stress_score.toFixed(2),               highlight: s.regional_stress_score > 0.5 },
    { label: "Anomaly",         value: s.anomaly_score.toFixed(2),                        highlight: s.anomaly_score > 0.4 },
    { label: "Evidence Quality",value: s.evidence_quality_score.toFixed(2),              highlight: false },
  ];
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "repeat(6, 1fr)",
      gap: 1,
      background: "var(--border)",
      border: "1px solid var(--border)",
      borderRadius: 6,
      overflow: "hidden",
    }}>
      {items.map(item => (
        <div key={item.label} style={{ background: "var(--bg)", padding: "12px 14px" }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", fontWeight: 600, marginBottom: 4 }}>
            {item.label}
          </div>
          <div style={{
            fontFamily: '"JetBrains Mono", monospace',
            fontSize: 16,
            fontWeight: 700,
            color: item.highlight ? "#ef4444" : "var(--text)",
          }}>
            {item.value}
          </div>
        </div>
      ))}
    </div>
  );
}
