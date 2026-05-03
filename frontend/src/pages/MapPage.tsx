import { useEffect, useState, useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import { Link } from "react-router-dom";
import "leaflet/dist/leaflet.css";
import type { ProjectListItem } from "../api/types";
import { getProjects, getProjectRiskSignal, getProjectEnrichment } from "../api/adapter";

interface MapProject {
  project: ProjectListItem;
  signalTier: string | null;
  evidenceCount: number | null;
  utility: string | null;
  enriched: boolean;
}

const MODEL_TIER_COLOR: Record<string, string> = {
  high:     "#ef4444",
  elevated: "#f59e0b",
  medium:   "#f59e0b",
  low:      "#22c55e",
  unknown:  "#6b7280",
};

const SIGNAL_TIER_COLOR: Record<string, string> = {
  high:     "#ef4444",
  moderate: "#f59e0b",
  low:      "#22c55e",
};

const TIER_LABEL: Record<string, string> = {
  high:     "High",
  elevated: "Elevated",
  medium:   "Elevated",
  moderate: "Moderate",
  low:      "Low",
  unknown:  "—",
};

function markerRadius(mw: number): number {
  return Math.max(7, Math.min(28, Math.sqrt(mw / 60) * 4.2));
}

const SELECT_STYLE: React.CSSProperties = {
  width: "100%",
  padding: "5px 8px",
  fontSize: 11,
  background: "var(--bg)",
  border: "1px solid var(--border)",
  borderRadius: 4,
  color: "var(--text)",
  cursor: "pointer",
};

const INPUT_STYLE: React.CSSProperties = {
  width: "100%",
  padding: "5px 8px",
  fontSize: 11,
  background: "var(--bg)",
  border: "1px solid var(--border)",
  borderRadius: 4,
  color: "var(--text)",
  boxSizing: "border-box",
};

const FILTER_LABEL: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.07em",
  color: "var(--text-dim)",
  marginBottom: 4,
};

export function MapPage() {
  const [mapProjects, setMapProjects] = useState<MapProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [filterState,      setFilterState]      = useState("all");
  const [filterModelTier,  setFilterModelTier]  = useState("all");
  const [filterSignalTier, setFilterSignalTier] = useState("all");
  const [filterLoadMin,    setFilterLoadMin]    = useState("");
  const [filterLoadMax,    setFilterLoadMax]    = useState("");

  useEffect(() => {
    setLoading(true);
    setError(null);

    getProjects()
      .then(async (projects) => {
        // Seed map markers immediately
        const initial: MapProject[] = projects.map(p => ({
          project: p, signalTier: null, evidenceCount: null, utility: null, enriched: false,
        }));
        setMapProjects(initial);
        setLoading(false);

        // Enrich each project in parallel (risk signal + enrichment)
        await Promise.allSettled(projects.map(async (p) => {
          const [sig, enr] = await Promise.allSettled([
            getProjectRiskSignal(p.project_id),
            getProjectEnrichment(p.project_id),
          ]);
          setMapProjects(prev => prev.map(item =>
            item.project.project_id !== p.project_id ? item : {
              ...item,
              signalTier:    sig.status === "fulfilled" ? sig.value.risk_signal_tier : item.signalTier,
              evidenceCount: sig.status === "fulfilled" ? sig.value.evidence_summary.evidence_count : item.evidenceCount,
              utility:       enr.status === "fulfilled" ? enr.value.utility : item.utility,
              enriched: true,
            }
          ));
        }));
      })
      .catch(e => { setError(String(e)); setLoading(false); });
  }, []);

  const allStates = useMemo(() =>
    [...new Set(mapProjects.map(d => d.project.state).filter(Boolean))].sort() as string[],
    [mapProjects]
  );

  const filtered = useMemo(() => mapProjects.filter(d => {
    const p = d.project;
    if (filterState !== "all" && p.state !== filterState) return false;
    if (filterModelTier !== "all" && p.risk_tier !== filterModelTier) return false;
    if (filterSignalTier !== "all" && d.signalTier !== filterSignalTier) return false;
    const mw = p.modeled_primary_load_mw;
    if (filterLoadMin !== "" && mw < Number(filterLoadMin)) return false;
    if (filterLoadMax !== "" && mw > Number(filterLoadMax)) return false;
    return true;
  }), [mapProjects, filterState, filterModelTier, filterSignalTier, filterLoadMin, filterLoadMax]);

  const onMap  = filtered.filter(d => d.project.latitude != null && d.project.longitude != null);
  const offMap = mapProjects.filter(d => d.project.latitude == null || d.project.longitude == null);

  return (
    <div style={{ display: "flex", flex: 1, minHeight: 0, overflow: "hidden" }}>

      {/* ── Left sidebar ── */}
      <aside style={{
        width: 260,
        flexShrink: 0,
        background: "var(--bg-surface)",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}>
        {/* Header */}
        <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", marginBottom: 2 }}>
            Project Map
          </div>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
            {loading ? "Loading…" : `${onMap.length} of ${filtered.length} projects on map`}
          </div>
        </div>

        {/* Filters */}
        <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)" }}>
            Filters
          </div>

          <div>
            <div style={FILTER_LABEL}>State</div>
            <select value={filterState} onChange={e => setFilterState(e.target.value)} style={SELECT_STYLE}>
              <option value="all">All states</option>
              {allStates.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          <div>
            <div style={FILTER_LABEL}>Model Risk Tier</div>
            <select value={filterModelTier} onChange={e => setFilterModelTier(e.target.value)} style={SELECT_STYLE}>
              <option value="all">All tiers</option>
              <option value="high">High</option>
              <option value="elevated">Elevated</option>
              <option value="low">Low</option>
            </select>
          </div>

          <div>
            <div style={FILTER_LABEL}>Evidence Signal Tier</div>
            <select value={filterSignalTier} onChange={e => setFilterSignalTier(e.target.value)} style={SELECT_STYLE}>
              <option value="all">All tiers</option>
              <option value="high">High</option>
              <option value="moderate">Moderate</option>
              <option value="low">Low</option>
            </select>
          </div>

          <div>
            <div style={FILTER_LABEL}>Load Range (MW)</div>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input
                type="number"
                placeholder="Min"
                value={filterLoadMin}
                onChange={e => setFilterLoadMin(e.target.value)}
                style={{ ...INPUT_STYLE, width: "50%" }}
              />
              <span style={{ fontSize: 11, color: "var(--text-dim)" }}>–</span>
              <input
                type="number"
                placeholder="Max"
                value={filterLoadMax}
                onChange={e => setFilterLoadMax(e.target.value)}
                style={{ ...INPUT_STYLE, width: "50%" }}
              />
            </div>
          </div>

          {(filterState !== "all" || filterModelTier !== "all" || filterSignalTier !== "all" || filterLoadMin !== "" || filterLoadMax !== "") && (
            <button
              onClick={() => { setFilterState("all"); setFilterModelTier("all"); setFilterSignalTier("all"); setFilterLoadMin(""); setFilterLoadMax(""); }}
              style={{ fontSize: 10, color: "var(--accent)", background: "none", border: "none", cursor: "pointer", textAlign: "left", padding: 0 }}
            >
              ✕ Clear filters
            </button>
          )}
        </div>

        {/* Legend */}
        <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)", marginBottom: 8 }}>
            Model Risk Tier
          </div>
          {[
            { label: "High",     color: MODEL_TIER_COLOR.high },
            { label: "Elevated", color: MODEL_TIER_COLOR.elevated },
            { label: "Low",      color: MODEL_TIER_COLOR.low },
          ].map(({ label, color }) => (
            <div key={label} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
              <svg width="12" height="12"><circle cx="6" cy="6" r="5" fill={color} fillOpacity="0.85" stroke={color} strokeWidth="1"/></svg>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{label}</span>
            </div>
          ))}
          <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 4 }}>Marker size ∝ load MW</div>
        </div>

        {/* Missing coordinates list */}
        <div style={{ flex: 1, overflowY: "auto", padding: "10px 16px" }}>
          <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)", marginBottom: 8 }}>
            Missing Coordinates ({offMap.length})
          </div>
          {offMap.length === 0 ? (
            <div style={{ fontSize: 11, color: "var(--text-dim)" }}>All projects have coordinates.</div>
          ) : (
            offMap.map(d => (
              <Link
                key={d.project.project_id}
                to={`/projects/${d.project.project_id}`}
                style={{ display: "block", textDecoration: "none", marginBottom: 8 }}
              >
                <div style={{ fontSize: 11, color: "var(--accent)", fontWeight: 600, lineHeight: 1.3 }}>
                  {d.project.project_name}
                </div>
                <div style={{ fontSize: 10, color: "var(--text-dim)" }}>
                  {d.project.state}{d.project.county ? `, ${d.project.county}` : ""}
                </div>
              </Link>
            ))
          )}
        </div>
      </aside>

      {/* ── Map ── */}
      <div style={{ flex: 1, position: "relative" }}>
        {error && (
          <div style={{
            position: "absolute", top: 10, left: 10, zIndex: 1000,
            background: "#7f1d1d", border: "1px solid #ef4444", borderRadius: 6,
            padding: "8px 12px", fontSize: 12, color: "#fca5a5",
          }}>
            {error}
          </div>
        )}

        <MapContainer
          center={[38.5, -96.5]}
          zoom={4}
          style={{ width: "100%", height: "100%" }}
          zoomControl={true}
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
            maxZoom={19}
          />

          {onMap.map(({ project: p, signalTier, evidenceCount, utility }) => {
            const color = MODEL_TIER_COLOR[p.risk_tier] ?? MODEL_TIER_COLOR.unknown;
            const radius = markerRadius(p.modeled_primary_load_mw);

            return (
              <CircleMarker
                key={p.project_id}
                center={[p.latitude!, p.longitude!]}
                radius={radius}
                pathOptions={{
                  fillColor: color,
                  fillOpacity: 0.82,
                  color: color,
                  weight: 1.5,
                  opacity: 1,
                }}
              >
                <Popup
                  minWidth={240}
                  maxWidth={300}
                  className="power-risk-popup"
                >
                  <div style={{
                    fontFamily: "system-ui, -apple-system, sans-serif",
                    background: "#1a1f2e",
                    color: "#e2e8f0",
                    padding: "2px 0",
                    minWidth: 230,
                  }}>
                    {/* Project name */}
                    <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6, lineHeight: 1.3, color: "#f1f5f9" }}>
                      {p.project_name}
                    </div>

                    {/* Location */}
                    <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 10 }}>
                      {p.county ? `${p.county} County, ` : ""}{p.state}
                    </div>

                    {/* Key facts grid */}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 12px", marginBottom: 10 }}>
                      <PopupField label="Load" value={`${p.modeled_primary_load_mw.toLocaleString()} MW`} mono />
                      <PopupField
                        label="Model Risk"
                        value={TIER_LABEL[p.risk_tier] ?? p.risk_tier}
                        color={MODEL_TIER_COLOR[p.risk_tier]}
                      />
                      <PopupField
                        label="Evidence Signal"
                        value={signalTier ? (TIER_LABEL[signalTier] ?? signalTier) : "—"}
                        color={signalTier ? SIGNAL_TIER_COLOR[signalTier] : undefined}
                      />
                      <PopupField
                        label="Evidence Count"
                        value={evidenceCount != null ? String(evidenceCount) : "—"}
                        mono
                      />
                    </div>

                    {/* Utility */}
                    {utility && (
                      <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 10, lineHeight: 1.4 }}>
                        <span style={{ color: "#64748b", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Utility </span>
                        {utility}
                      </div>
                    )}

                    {/* Detail link */}
                    <div style={{ borderTop: "1px solid #2d3748", paddingTop: 8, marginTop: 2 }}>
                      <a
                        href={`/projects/${p.project_id}`}
                        style={{ fontSize: 11, color: "#60a5fa", textDecoration: "none", fontWeight: 600 }}
                      >
                        Open project detail →
                      </a>
                    </div>
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}
        </MapContainer>
      </div>
    </div>
  );
}

function PopupField({ label, value, mono, color }: {
  label: string;
  value: string;
  mono?: boolean;
  color?: string;
}) {
  return (
    <div>
      <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.07em", color: "#64748b", marginBottom: 1 }}>
        {label}
      </div>
      <div style={{
        fontSize: 12,
        fontWeight: 600,
        fontFamily: mono ? '"JetBrains Mono", monospace' : undefined,
        color: color ?? "#e2e8f0",
      }}>
        {value}
      </div>
    </div>
  );
}
