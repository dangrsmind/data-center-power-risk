import { useEffect, useState, useMemo, useCallback } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, GeoJSON } from "react-leaflet";
import { Link } from "react-router-dom";
import "leaflet/dist/leaflet.css";
import type { ProjectListItem } from "../api/types";
import { getProjects, getProjectRiskSignal, getProjectEnrichment } from "../api/adapter";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MapProject {
  project: ProjectListItem;
  signalTier: string | null;
  evidenceCount: number | null;
  utility: string | null;
  enriched: boolean;
}

type ColorMode = "evidence" | "model";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const US_STATES_GJ_URL =
  "https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json";

const MODEL_COLOR: Record<string, string> = {
  high:     "#ef4444",
  elevated: "#f59e0b",
  medium:   "#f59e0b",
  low:      "#22c55e",
  unknown:  "#475569",
};

const SIGNAL_COLOR: Record<string, string> = {
  high:     "#ef4444",
  moderate: "#f59e0b",
  low:      "#22c55e",
};

const MODEL_LABEL: Record<string, string> = {
  high: "High", elevated: "Elevated", medium: "Elevated", low: "Low", unknown: "Unknown",
};

const SIGNAL_LABEL: Record<string, string> = {
  high: "High", moderate: "Moderate", low: "Low",
};

const SIZE_EXAMPLES = [
  { mw: 300,  label: "300 MW" },
  { mw: 600,  label: "600 MW" },
  { mw: 1200, label: "1,200 MW" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function markerRadius(mw: number): number {
  return Math.max(7, Math.min(28, Math.sqrt(mw / 60) * 4.2));
}

function markerColor(mode: ColorMode, mp: MapProject): string {
  if (mode === "evidence") {
    if (!mp.signalTier) return "#475569"; // loading / unknown
    return SIGNAL_COLOR[mp.signalTier] ?? "#475569";
  }
  return MODEL_COLOR[mp.project.risk_tier] ?? MODEL_COLOR.unknown;
}

function stateBoundaryStyle() {
  return { color: "#334155", weight: 0.9, fillOpacity: 0, opacity: 0.65 };
}

// ---------------------------------------------------------------------------
// Tiny sub-components
// ---------------------------------------------------------------------------

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 9, fontWeight: 700, textTransform: "uppercase" as const,
      letterSpacing: "0.09em", color: "var(--text-dim)", marginBottom: 8,
    }}>
      {children}
    </div>
  );
}

function Divider() {
  return <div style={{ borderTop: "1px solid var(--border)", margin: "0" }} />;
}

function LayerRow({
  label, checked, onChange, disabled, note,
}: {
  label: string; checked: boolean; onChange?: (v: boolean) => void;
  disabled?: boolean; note?: string;
}) {
  return (
    <label style={{
      display: "flex", alignItems: "flex-start", gap: 8, cursor: disabled ? "default" : "pointer",
      marginBottom: 7, opacity: disabled ? 0.45 : 1,
    }}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={e => onChange?.(e.target.checked)}
        style={{ marginTop: 1, flexShrink: 0, accentColor: "var(--accent)" }}
      />
      <div>
        <div style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.3 }}>{label}</div>
        {note && (
          <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 2, fontStyle: "italic" }}>
            {note}
          </div>
        )}
      </div>
    </label>
  );
}

function ColorDot({ color, size = 10 }: { color: string; size?: number }) {
  const r = size / 2;
  return (
    <svg width={size} height={size} style={{ flexShrink: 0 }}>
      <circle cx={r} cy={r} r={r - 1} fill={color} fillOpacity={0.88} stroke={color} strokeWidth={0.8} />
    </svg>
  );
}

function PopupField({
  label, value, color, mono,
}: { label: string; value: string; color?: string; mono?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 9, textTransform: "uppercase" as const, letterSpacing: "0.07em", color: "#64748b", marginBottom: 1 }}>
        {label}
      </div>
      <div style={{ fontSize: 12, fontWeight: 600, color: color ?? "#e2e8f0", fontFamily: mono ? "monospace" : undefined }}>
        {value}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function MapPage() {
  // Data
  const [mapProjects, setMapProjects] = useState<MapProject[]>([]);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState<string | null>(null);
  const [stateGeoJSON, setStateGeoJSON] = useState<unknown>(null);
  const [geoError, setGeoError]       = useState(false);

  // Layer toggles
  const [showStates, setShowStates] = useState(true);

  // Color mode
  const [colorMode, setColorMode] = useState<ColorMode>("evidence");

  // Filters
  const [filterState,      setFilterState]      = useState("all");
  const [filterModelTier,  setFilterModelTier]  = useState("all");
  const [filterSignalTier, setFilterSignalTier] = useState("all");
  const [filterLoadMin,    setFilterLoadMin]    = useState("");
  const [filterLoadMax,    setFilterLoadMax]    = useState("");

  // Fetch US state boundaries
  useEffect(() => {
    fetch(US_STATES_GJ_URL)
      .then(r => { if (!r.ok) throw new Error("fetch failed"); return r.json(); })
      .then(setStateGeoJSON)
      .catch(() => setGeoError(true));
  }, []);

  // Fetch projects + enrich each in parallel
  useEffect(() => {
    setLoading(true);
    setError(null);
    getProjects()
      .then(async (projects) => {
        setMapProjects(projects.map(p => ({
          project: p, signalTier: null, evidenceCount: null, utility: null, enriched: false,
        })));
        setLoading(false);
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
              utility:       enr.status === "fulfilled" ? (enr.value.utility ?? item.utility) : item.utility,
              enriched:      true,
            }
          ));
        }));
      })
      .catch(e => { setError(String(e)); setLoading(false); });
  }, []);

  // Unique state list
  const allStates = useMemo(
    () => [...new Set(mapProjects.map(d => d.project.state).filter(Boolean))].sort() as string[],
    [mapProjects],
  );

  const hasActiveFilter = filterState !== "all" || filterModelTier !== "all" ||
    filterSignalTier !== "all" || filterLoadMin !== "" || filterLoadMax !== "";

  const clearFilters = useCallback(() => {
    setFilterState("all"); setFilterModelTier("all");
    setFilterSignalTier("all"); setFilterLoadMin(""); setFilterLoadMax("");
  }, []);

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

  // Stats (always from full filtered set, not just onMap)
  const stateCounts = useMemo(() => {
    const m: Record<string, number> = {};
    filtered.forEach(d => { const s = d.project.state; if (s) m[s] = (m[s] ?? 0) + 1; });
    return Object.entries(m).sort(([, a], [, b]) => b - a);
  }, [filtered]);

  const modelTierCounts = useMemo(() => {
    const m: Record<string, number> = { high: 0, elevated: 0, low: 0 };
    filtered.forEach(d => { const t = d.project.risk_tier; if (t in m) m[t]++; });
    return m;
  }, [filtered]);

  const signalTierCounts = useMemo(() => {
    const m: Record<string, number> = { high: 0, moderate: 0, low: 0 };
    const enrichedCount = filtered.filter(d => d.enriched).length;
    filtered.forEach(d => { const t = d.signalTier; if (t && t in m) m[t]++; });
    return { counts: m, enrichedCount, total: filtered.length };
  }, [filtered]);

  const sel: React.CSSProperties = {
    width: "100%", padding: "5px 8px", fontSize: 11,
    background: "var(--bg)", border: "1px solid var(--border)",
    borderRadius: 4, color: "var(--text)", cursor: "pointer",
  };
  const inp: React.CSSProperties = {
    padding: "5px 8px", fontSize: 11, background: "var(--bg)",
    border: "1px solid var(--border)", borderRadius: 4, color: "var(--text)",
    boxSizing: "border-box" as const, width: "100%",
  };
  const lbl: React.CSSProperties = {
    fontSize: 10, fontWeight: 700, textTransform: "uppercase" as const,
    letterSpacing: "0.07em", color: "var(--text-dim)", marginBottom: 4, display: "block",
  };

  return (
    <div style={{ display: "flex", flex: 1, minHeight: 0, overflow: "hidden" }}>

      {/* ─────────────── Sidebar ─────────────── */}
      <aside style={{
        width: 272, flexShrink: 0, background: "var(--bg-surface)",
        borderRight: "1px solid var(--border)", display: "flex",
        flexDirection: "column", overflow: "hidden",
      }}>

        {/* Header */}
        <div style={{ padding: "13px 16px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", marginBottom: 2 }}>
            Project Map
          </div>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
            {loading
              ? "Loading projects…"
              : `${onMap.length} of ${filtered.length} project${filtered.length !== 1 ? "s" : ""} on map`}
            {hasActiveFilter && (
              <span style={{ color: "var(--accent)", marginLeft: 6 }}>· filtered</span>
            )}
          </div>
        </div>

        <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column" }}>

          {/* ── Layers ── */}
          <div style={{ padding: "12px 16px 10px" }}>
            <SectionTitle>Layers</SectionTitle>
            <LayerRow
              label="State boundaries"
              checked={showStates}
              onChange={setShowStates}
              note={geoError ? "Failed to load — check network" : !stateGeoJSON && showStates ? "Loading…" : undefined}
            />
            <LayerRow
              label="Utility territory polygons"
              checked={false}
              disabled
              note="Territory polygons not available from backend"
            />
            <LayerRow
              label="Region / ISO overlay"
              checked={false}
              disabled
              note="Region name not in current API response"
            />
          </div>

          <Divider />

          {/* ── Color Mode ── */}
          <div style={{ padding: "12px 16px 10px" }}>
            <SectionTitle>Color markers by</SectionTitle>
            <div style={{ display: "flex", gap: 6 }}>
              {(["evidence", "model"] as ColorMode[]).map(mode => {
                const active = colorMode === mode;
                return (
                  <button
                    key={mode}
                    onClick={() => setColorMode(mode)}
                    style={{
                      flex: 1, padding: "5px 4px", fontSize: 10, fontWeight: 600,
                      border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                      borderRadius: 4, cursor: "pointer",
                      background: active ? "rgba(96,165,250,0.12)" : "transparent",
                      color: active ? "var(--accent)" : "var(--text-muted)",
                      textAlign: "center",
                    }}
                  >
                    {mode === "evidence" ? "Evidence Signal" : "Model Risk"}
                  </button>
                );
              })}
            </div>
            {colorMode === "evidence" && signalTierCounts.enrichedCount < signalTierCounts.total && (
              <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 6, fontStyle: "italic" }}>
                {signalTierCounts.total - signalTierCounts.enrichedCount} project
                {signalTierCounts.total - signalTierCounts.enrichedCount !== 1 ? "s" : ""} still loading signal data
              </div>
            )}
          </div>

          <Divider />

          {/* ── Filters ── */}
          <div style={{ padding: "12px 16px 10px", display: "flex", flexDirection: "column", gap: 10 }}>
            <SectionTitle>Filters</SectionTitle>

            <div>
              <span style={lbl}>State</span>
              <select value={filterState} onChange={e => setFilterState(e.target.value)} style={sel}>
                <option value="all">All states ({mapProjects.length})</option>
                {allStates.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>

            <div>
              <span style={lbl}>Evidence Signal Tier</span>
              <select value={filterSignalTier} onChange={e => setFilterSignalTier(e.target.value)} style={sel}>
                <option value="all">All</option>
                <option value="high">High</option>
                <option value="moderate">Moderate</option>
                <option value="low">Low</option>
              </select>
            </div>

            <div>
              <span style={lbl}>Model Risk Tier</span>
              <select value={filterModelTier} onChange={e => setFilterModelTier(e.target.value)} style={sel}>
                <option value="all">All</option>
                <option value="high">High</option>
                <option value="elevated">Elevated</option>
                <option value="low">Low</option>
              </select>
            </div>

            <div>
              <span style={lbl}>Load Range (MW)</span>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input type="number" placeholder="Min" value={filterLoadMin}
                  onChange={e => setFilterLoadMin(e.target.value)}
                  style={{ ...inp, width: "calc(50% - 10px)" }} />
                <span style={{ fontSize: 11, color: "var(--text-dim)", flexShrink: 0 }}>–</span>
                <input type="number" placeholder="Max" value={filterLoadMax}
                  onChange={e => setFilterLoadMax(e.target.value)}
                  style={{ ...inp, width: "calc(50% - 10px)" }} />
              </div>
            </div>

            {hasActiveFilter && (
              <button onClick={clearFilters} style={{
                fontSize: 10, color: "var(--accent)", background: "none",
                border: "1px solid var(--border)", borderRadius: 4,
                cursor: "pointer", padding: "4px 8px", alignSelf: "flex-start",
              }}>
                ✕ Clear all filters
              </button>
            )}
          </div>

          <Divider />

          {/* ── Legend ── */}
          <div style={{ padding: "12px 16px 10px" }}>
            <SectionTitle>
              Legend — {colorMode === "evidence" ? "Evidence Signal Tier" : "Model Risk Tier"}
            </SectionTitle>

            {/* Color scale */}
            <div style={{ marginBottom: 10 }}>
              {colorMode === "evidence" ? (
                <>
                  {([
                    ["high",     SIGNAL_COLOR.high,     "High signal strength"],
                    ["moderate", SIGNAL_COLOR.moderate, "Moderate signal"],
                    ["low",      SIGNAL_COLOR.low,      "Low signal"],
                    ["loading",  "#475569",              "Loading / unknown"],
                  ] as [string, string, string][]).map(([, color, desc]) => (
                    <div key={desc} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                      <ColorDot color={color} size={11} />
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{desc}</span>
                    </div>
                  ))}
                </>
              ) : (
                <>
                  {([
                    [MODEL_COLOR.high,     "High model risk"],
                    [MODEL_COLOR.elevated, "Elevated model risk"],
                    [MODEL_COLOR.low,      "Low model risk"],
                  ] as [string, string][]).map(([color, desc]) => (
                    <div key={desc} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                      <ColorDot color={color} size={11} />
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{desc}</span>
                    </div>
                  ))}
                </>
              )}
            </div>

            {/* Size scale */}
            <div style={{ borderTop: "1px solid var(--border)", paddingTop: 8 }}>
              <div style={{ fontSize: 10, color: "var(--text-dim)", marginBottom: 6 }}>
                Marker size = modeled load (MW)
              </div>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 10 }}>
                {SIZE_EXAMPLES.map(({ mw, label }) => {
                  const r = markerRadius(mw);
                  return (
                    <div key={mw} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
                      <svg width={r * 2 + 2} height={r * 2 + 2}>
                        <circle
                          cx={r + 1} cy={r + 1} r={r}
                          fill="#475569" fillOpacity={0.7}
                          stroke="#94a3b8" strokeWidth={1}
                        />
                      </svg>
                      <span style={{ fontSize: 9, color: "var(--text-dim)", whiteSpace: "nowrap" }}>
                        {label}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          <Divider />

          {/* ── Stats ── */}
          <div style={{ padding: "12px 16px 10px" }}>
            <SectionTitle>
              Stats{hasActiveFilter ? " (filtered)" : ""}
            </SectionTitle>

            {/* By State */}
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 10, color: "var(--text-dim)", marginBottom: 5, fontWeight: 600 }}>
                By State
              </div>
              {stateCounts.length === 0 ? (
                <div style={{ fontSize: 11, color: "var(--text-dim)" }}>No data</div>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 10px" }}>
                  {stateCounts.map(([state, count]) => (
                    <div key={state} style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      <span style={{ fontWeight: 700, color: "var(--text)" }}>{state}</span>
                      <span style={{ color: "var(--text-dim)", marginLeft: 3 }}>{count}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* By Model Risk */}
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 10, color: "var(--text-dim)", marginBottom: 5, fontWeight: 600 }}>
                Model Risk Tier
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                {(["high", "elevated", "low"] as const).map(tier => (
                  <div key={tier} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <ColorDot color={MODEL_COLOR[tier]} size={9} />
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      {MODEL_LABEL[tier]}
                    </span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text)" }}>
                      {modelTierCounts[tier]}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* By Evidence Signal */}
            <div>
              <div style={{ fontSize: 10, color: "var(--text-dim)", marginBottom: 5, fontWeight: 600 }}>
                Evidence Signal Tier
                {signalTierCounts.enrichedCount < signalTierCounts.total && (
                  <span style={{ fontStyle: "italic", fontWeight: 400, marginLeft: 4 }}>
                    ({signalTierCounts.enrichedCount}/{signalTierCounts.total} loaded)
                  </span>
                )}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                {(["high", "moderate", "low"] as const).map(tier => (
                  <div key={tier} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <ColorDot color={SIGNAL_COLOR[tier]} size={9} />
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      {SIGNAL_LABEL[tier]}
                    </span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text)" }}>
                      {signalTierCounts.counts[tier]}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <Divider />

          {/* ── Missing Coordinates ── */}
          <div style={{ padding: "12px 16px 14px" }}>
            <SectionTitle>
              No Coordinates ({offMap.length})
            </SectionTitle>
            {offMap.length === 0 ? (
              <div style={{ fontSize: 11, color: "var(--text-dim)" }}>All projects are mapped.</div>
            ) : (
              <>
                <div style={{ fontSize: 10, color: "var(--text-dim)", fontStyle: "italic", marginBottom: 8, lineHeight: 1.4 }}>
                  Add coordinates in Discover (manual capture) or on the Project Detail overview.
                </div>
                {offMap.map(d => (
                  <Link
                    key={d.project.project_id}
                    to={`/projects/${d.project.project_id}`}
                    style={{ display: "block", textDecoration: "none", marginBottom: 8 }}
                  >
                    <div style={{ fontSize: 11, color: "var(--accent)", fontWeight: 600, lineHeight: 1.3 }}>
                      {d.project.project_name}
                    </div>
                    <div style={{ fontSize: 10, color: "var(--text-dim)" }}>
                      {d.project.county ? `${d.project.county} Co., ` : ""}{d.project.state}
                    </div>
                  </Link>
                ))}
              </>
            )}
          </div>

        </div>
      </aside>

      {/* ─────────────── Map ─────────────── */}
      <div style={{ flex: 1, position: "relative" }}>
        {error && (
          <div style={{
            position: "absolute", top: 12, left: 12, zIndex: 1000,
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
          zoomControl
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
            maxZoom={19}
          />

          {/* State boundaries */}
          {showStates && stateGeoJSON && (
            <GeoJSON
              key="us-states"
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              data={stateGeoJSON as any}
              style={stateBoundaryStyle}
            />
          )}

          {/* Project markers */}
          {onMap.map((mp) => {
            const { project: p } = mp;
            const color  = markerColor(colorMode, mp);
            const radius = markerRadius(p.modeled_primary_load_mw);
            const isLoading = colorMode === "evidence" && !mp.enriched;

            return (
              <CircleMarker
                key={p.project_id}
                center={[p.latitude!, p.longitude!]}
                radius={radius}
                pathOptions={{
                  fillColor: color,
                  fillOpacity: isLoading ? 0.4 : 0.82,
                  color: "#fff",
                  weight: 1.2,
                  opacity: 0.55,
                }}
              >
                <Popup minWidth={248} maxWidth={300} className="power-risk-popup">
                  <div style={{
                    fontFamily: "system-ui, -apple-system, sans-serif",
                    color: "#e2e8f0", padding: "2px 0", minWidth: 240,
                  }}>
                    {/* Name */}
                    <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4, lineHeight: 1.3, color: "#f1f5f9" }}>
                      {p.project_name}
                    </div>

                    {/* Location */}
                    <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 10 }}>
                      {p.county ? `${p.county} County, ` : ""}{p.state}
                    </div>

                    {/* Stats grid */}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "7px 14px", marginBottom: 10 }}>
                      <PopupField label="Modeled Load" value={`${p.modeled_primary_load_mw.toLocaleString()} MW`} mono />
                      <PopupField label="Phases" value={String(p.phase_count)} mono />
                      <PopupField
                        label="Evidence Signal"
                        value={mp.signalTier ? (SIGNAL_LABEL[mp.signalTier] ?? mp.signalTier) : (mp.enriched ? "—" : "loading…")}
                        color={mp.signalTier ? SIGNAL_COLOR[mp.signalTier] : "#64748b"}
                      />
                      <PopupField
                        label="Model Risk"
                        value={MODEL_LABEL[p.risk_tier] ?? p.risk_tier}
                        color={MODEL_COLOR[p.risk_tier]}
                      />
                      <PopupField
                        label="Evidence Count"
                        value={mp.evidenceCount != null ? String(mp.evidenceCount) : (mp.enriched ? "—" : "loading…")}
                        mono
                      />
                      <PopupField
                        label="Lifecycle"
                        value={p.lifecycle_state.replace(/_/g, " ")}
                      />
                    </div>

                    {/* Utility if available */}
                    {mp.utility && (
                      <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 8, lineHeight: 1.4 }}>
                        <span style={{ color: "#475569", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                          Utility{" "}
                        </span>
                        {mp.utility}
                      </div>
                    )}

                    {/* Which tier is coloring this marker */}
                    <div style={{
                      fontSize: 10, color: "#64748b", marginBottom: 8, fontStyle: "italic",
                    }}>
                      Marker color: {colorMode === "evidence" ? "evidence signal tier" : "model risk tier"}
                    </div>

                    {/* Detail link */}
                    <div style={{ borderTop: "1px solid #2d3748", paddingTop: 8 }}>
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
