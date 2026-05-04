import { useEffect, useState, useMemo } from "react";
import type { DiscoveredSource } from "../api/types";
import { getDiscoveredSources } from "../api/adapter";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Decision = "approved" | "rejected";
type StatusFilter = "all" | "pending" | "approved" | "rejected";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CONF_COLOR: Record<string, string> = {
  high:   "#22c55e",
  medium: "#f59e0b",
  low:    "#ef4444",
};

const CONF_BG: Record<string, string> = {
  high:   "rgba(34,197,94,0.12)",
  medium: "rgba(245,158,11,0.12)",
  low:    "rgba(239,68,68,0.12)",
};

const SOURCE_TYPE_LABEL: Record<string, string> = {
  developer_statement: "Developer Statement",
  official_filing:     "Official Filing",
  utility_statement:   "Utility Statement",
  regulatory_record:   "Regulatory Record",
  county_record:       "County Record",
  press:               "Press",
  url_seed:            "URL Seed",
};

const STATUS_FILTER_LABELS: { value: StatusFilter; label: string }[] = [
  { value: "all",      label: "All" },
  { value: "pending",  label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return iso.slice(0, 10);
  }
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function hostname(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Badge({
  label, color, bg,
}: { label: string; color: string; bg: string }) {
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, textTransform: "uppercase" as const,
      letterSpacing: "0.07em", padding: "2px 7px", borderRadius: 3,
      color, background: bg, border: `1px solid ${color}33`,
      whiteSpace: "nowrap" as const,
    }}>
      {label}
    </span>
  );
}

function StatusBadge({ status }: { status: "pending" | "approved" | "rejected" }) {
  const cfg = {
    pending:  { label: "Pending",  color: "#94a3b8", bg: "rgba(148,163,184,0.1)" },
    approved: { label: "Approved", color: "#22c55e", bg: "rgba(34,197,94,0.12)" },
    rejected: { label: "Rejected", color: "#ef4444", bg: "rgba(239,68,68,0.12)" },
  }[status];
  return <Badge label={cfg.label} color={cfg.color} bg={cfg.bg} />;
}

function SourceCard({
  source,
  decision,
  onApprove,
  onReject,
  onUndo,
}: {
  source: DiscoveredSource;
  decision: Decision | undefined;
  onApprove: () => void;
  onReject: () => void;
  onUndo: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const status: "pending" | "approved" | "rejected" = decision ?? "pending";

  const confColor = CONF_COLOR[source.confidence] ?? "#94a3b8";
  const confBg    = CONF_BG[source.confidence]    ?? "rgba(148,163,184,0.1)";

  const borderColor = status === "approved"
    ? "rgba(34,197,94,0.35)"
    : status === "rejected"
    ? "rgba(239,68,68,0.25)"
    : "var(--border)";

  return (
    <div style={{
      border: `1px solid ${borderColor}`,
      borderRadius: 6,
      background: "var(--bg-surface)",
      padding: "14px 16px",
      marginBottom: 10,
      transition: "border-color 0.15s",
    }}>
      {/* ── Top row ── */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
        {/* Left badges */}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", flex: 1 }}>
          <Badge
            label={source.confidence ? `Confidence: ${source.confidence}` : "Confidence: —"}
            color={confColor}
            bg={confBg}
          />
          <Badge
            label={SOURCE_TYPE_LABEL[source.source_type] ?? source.source_type}
            color="#94a3b8"
            bg="rgba(148,163,184,0.08)"
          />
          <Badge
            label={source.discovery_method.replace(/_/g, " ")}
            color="#60a5fa"
            bg="rgba(96,165,250,0.08)"
          />
        </div>

        {/* Status + actions */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          <StatusBadge status={status} />

          {decision ? (
            <button
              onClick={onUndo}
              style={{
                fontSize: 11, padding: "3px 10px", borderRadius: 4, cursor: "pointer",
                background: "transparent", border: "1px solid var(--border)",
                color: "var(--text-muted)",
              }}
            >
              Undo
            </button>
          ) : (
            <>
              <button
                onClick={onApprove}
                style={{
                  fontSize: 11, fontWeight: 600, padding: "3px 12px", borderRadius: 4,
                  cursor: "pointer", background: "rgba(34,197,94,0.1)",
                  border: "1px solid rgba(34,197,94,0.45)", color: "#22c55e",
                }}
              >
                Approve
              </button>
              <button
                onClick={onReject}
                style={{
                  fontSize: 11, fontWeight: 600, padding: "3px 12px", borderRadius: 4,
                  cursor: "pointer", background: "rgba(239,68,68,0.08)",
                  border: "1px solid rgba(239,68,68,0.35)", color: "#ef4444",
                }}
              >
                Reject
              </button>
            </>
          )}

          {source.source_url && (
            <a
              href={source.source_url}
              target="_blank"
              rel="noopener noreferrer"
              title={source.source_url}
              style={{
                fontSize: 11, padding: "3px 8px", borderRadius: 4,
                border: "1px solid var(--border)", color: "var(--accent)",
                textDecoration: "none", whiteSpace: "nowrap",
              }}
            >
              ↗ Source
            </a>
          )}
        </div>
      </div>

      {/* ── Project name + location ── */}
      <div style={{ marginBottom: 6 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text)", lineHeight: 1.3, marginBottom: 2 }}>
          {source.candidate_project_name || "—"}
        </div>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          {source.developer || "Unknown developer"}
          {(source.state || source.county) && (
            <span style={{ color: "var(--text-dim)", marginLeft: 6 }}>
              · {source.county ? `${source.county} Co., ` : ""}{source.state}
            </span>
          )}
        </div>
      </div>

      {/* ── Detected facts row ── */}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 8 }}>
        <Fact label="Load" value={source.detected_load_mw != null ? `${source.detected_load_mw.toLocaleString()} MW` : "—"} />
        <Fact label="Region" value={source.detected_region || "—"} />
        <Fact label="Utility" value={source.detected_utility || "—"} />
        <Fact label="Source date" value={source.source_date || "—"} />
      </div>

      {/* ── Source title ── */}
      {source.title && (
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6, lineHeight: 1.4 }}>
          <span style={{ color: "var(--text-dim)", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Title{" "}
          </span>
          {source.source_url ? (
            <a
              href={source.source_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "var(--accent)", textDecoration: "none" }}
            >
              {truncate(source.title, 120)}
            </a>
          ) : (
            truncate(source.title, 120)
          )}
          {source.source_url && (
            <span style={{ fontSize: 10, color: "var(--text-dim)", marginLeft: 6 }}>
              ({hostname(source.source_url)})
            </span>
          )}
        </div>
      )}

      {/* ── Requires review reason ── */}
      {source.requires_review_reason && (
        <div style={{ marginBottom: 6 }}>
          <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)" }}>
            Review reason{" "}
          </span>
          <span style={{ fontSize: 11, color: "#f59e0b", lineHeight: 1.4 }}>
            {expanded
              ? source.requires_review_reason
              : truncate(source.requires_review_reason, 100)}
          </span>
          {source.requires_review_reason.length > 100 && (
            <button
              onClick={() => setExpanded(e => !e)}
              style={{
                fontSize: 10, color: "var(--accent)", background: "none",
                border: "none", cursor: "pointer", padding: "0 4px",
              }}
            >
              {expanded ? "less" : "more"}
            </button>
          )}
        </div>
      )}

      {/* ── Footer ── */}
      <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 4 }}>
        Retrieved {formatDate(source.retrieved_at)} · ID {source.discovery_id}
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ fontSize: 9, textTransform: "uppercase" as const, letterSpacing: "0.07em", color: "var(--text-dim)", marginBottom: 1 }}>
        {label}
      </div>
      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)" }}>{value}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function DiscoverPage() {
  const [sources,   setSources]   = useState<DiscoveredSource[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});

  // Filters
  const [filterStatus,     setFilterStatus]     = useState<StatusFilter>("all");
  const [filterConfidence, setFilterConfidence] = useState("all");
  const [filterState,      setFilterState]      = useState("all");
  const [search,           setSearch]           = useState("");

  useEffect(() => {
    setLoading(true);
    getDiscoveredSources()
      .then(data => { setSources(data); setLoading(false); })
      .catch(e => { setError(String(e)); setLoading(false); });
  }, []);

  const allStates = useMemo(
    () => [...new Set(sources.map(s => s.state).filter(Boolean))].sort(),
    [sources],
  );

  const filtered = useMemo(() => sources.filter(s => {
    const dec = decisions[s.discovery_id];
    const status = dec ?? "pending";
    if (filterStatus !== "all" && status !== filterStatus) return false;
    if (filterConfidence !== "all" && s.confidence !== filterConfidence) return false;
    if (filterState !== "all" && s.state !== filterState) return false;
    if (search) {
      const q = search.toLowerCase();
      if (
        !s.candidate_project_name.toLowerCase().includes(q) &&
        !s.developer.toLowerCase().includes(q) &&
        !s.title.toLowerCase().includes(q)
      ) return false;
    }
    return true;
  }), [sources, decisions, filterStatus, filterConfidence, filterState, search]);

  // Summary counts (always over all sources)
  const pendingCount  = sources.filter(s => !decisions[s.discovery_id]).length;
  const approvedCount = Object.values(decisions).filter(d => d === "approved").length;
  const rejectedCount = Object.values(decisions).filter(d => d === "rejected").length;

  const approve = (id: string) => setDecisions(prev => ({ ...prev, [id]: "approved" }));
  const reject  = (id: string) => setDecisions(prev => ({ ...prev, [id]: "rejected" }));
  const undo    = (id: string) => setDecisions(prev => { const n = { ...prev }; delete n[id]; return n; });

  const sel: React.CSSProperties = {
    padding: "5px 8px", fontSize: 11, background: "var(--bg)", border: "1px solid var(--border)",
    borderRadius: 4, color: "var(--text)", cursor: "pointer",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>

      {/* ── Header ── */}
      <div style={{
        padding: "14px 20px", borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", gap: 16, flexShrink: 0,
        background: "var(--bg-surface)",
      }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text)" }}>Discovery Review</div>
          <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 1 }}>
            Review automatically discovered sources before ingestion
          </div>
        </div>

        {/* Summary counts */}
        {!loading && !error && sources.length > 0 && (
          <div style={{ marginLeft: "auto", display: "flex", gap: 16, alignItems: "center" }}>
            <CountPill label="Total" value={sources.length} color="var(--text-muted)" />
            <CountPill label="Pending"  value={pendingCount}  color="#94a3b8" />
            <CountPill label="Approved" value={approvedCount} color="#22c55e" />
            <CountPill label="Rejected" value={rejectedCount} color="#ef4444" />
          </div>
        )}
      </div>

      {/* ── Filter bar ── */}
      {!loading && !error && sources.length > 0 && (
        <div style={{
          padding: "10px 20px", borderBottom: "1px solid var(--border)",
          display: "flex", gap: 10, alignItems: "center", flexShrink: 0,
          background: "var(--bg)", flexWrap: "wrap",
        }}>
          {/* Status filter tabs */}
          <div style={{ display: "flex", border: "1px solid var(--border)", borderRadius: 4, overflow: "hidden" }}>
            {STATUS_FILTER_LABELS.map(({ value, label }) => {
              const active = filterStatus === value;
              return (
                <button
                  key={value}
                  onClick={() => setFilterStatus(value)}
                  style={{
                    fontSize: 11, fontWeight: active ? 700 : 400,
                    padding: "4px 12px", cursor: "pointer",
                    background: active ? "var(--accent)" : "transparent",
                    color: active ? "#fff" : "var(--text-muted)",
                    border: "none",
                    borderRight: "1px solid var(--border)",
                  }}
                >
                  {label}
                </button>
              );
            })}
          </div>

          <select value={filterConfidence} onChange={e => setFilterConfidence(e.target.value)} style={sel}>
            <option value="all">All confidence</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>

          <select value={filterState} onChange={e => setFilterState(e.target.value)} style={sel}>
            <option value="all">All states</option>
            {allStates.map(s => <option key={s} value={s}>{s}</option>)}
          </select>

          <input
            type="text"
            placeholder="Search name, developer, title…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ ...sel, width: 220, cursor: "text" }}
          />

          {(filterStatus !== "all" || filterConfidence !== "all" || filterState !== "all" || search) && (
            <button
              onClick={() => { setFilterStatus("all"); setFilterConfidence("all"); setFilterState("all"); setSearch(""); }}
              style={{ fontSize: 11, color: "var(--accent)", background: "none", border: "1px solid var(--border)", borderRadius: 4, cursor: "pointer", padding: "4px 10px" }}
            >
              ✕ Clear
            </button>
          )}

          <span style={{ fontSize: 11, color: "var(--text-dim)", marginLeft: "auto" }}>
            {filtered.length} of {sources.length} shown
          </span>
        </div>
      )}

      {/* ── Body ── */}
      <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>

        {loading && (
          <div style={{ fontSize: 13, color: "var(--text-dim)", padding: "40px 0", textAlign: "center" }}>
            Loading discovered sources…
          </div>
        )}

        {error && (
          <div style={{
            background: "rgba(127,29,29,0.5)", border: "1px solid #ef4444",
            borderRadius: 6, padding: "12px 16px", fontSize: 13, color: "#fca5a5", marginBottom: 16,
          }}>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>Failed to load discovered sources</div>
            <div style={{ fontSize: 12, opacity: 0.8 }}>{error}</div>
            <div style={{ fontSize: 11, color: "#fca5a5", marginTop: 8 }}>
              Make sure the backend is running and the discovery script has been run.
            </div>
          </div>
        )}

        {!loading && !error && sources.length === 0 && (
          <div style={{
            display: "flex", flexDirection: "column", alignItems: "center",
            justifyContent: "center", padding: "80px 0", gap: 12,
          }}>
            <div style={{ fontSize: 32, opacity: 0.25 }}>◎</div>
            <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-muted)" }}>
              No discovered sources available yet
            </div>
            <div style={{ fontSize: 13, color: "var(--text-dim)", textAlign: "center", maxWidth: 380, lineHeight: 1.6 }}>
              Run the discovery script first to populate this queue:
            </div>
            <code style={{
              fontSize: 11, background: "var(--bg-surface)", border: "1px solid var(--border)",
              borderRadius: 4, padding: "6px 12px", color: "var(--accent)",
            }}>
              DATABASE_URL='' python3 scripts/discover_starter_dataset.py
            </code>
          </div>
        )}

        {!loading && !error && sources.length > 0 && filtered.length === 0 && (
          <div style={{ fontSize: 13, color: "var(--text-dim)", padding: "40px 0", textAlign: "center" }}>
            No sources match the current filters.
          </div>
        )}

        {filtered.map(source => (
          <SourceCard
            key={source.discovery_id}
            source={source}
            decision={decisions[source.discovery_id]}
            onApprove={() => approve(source.discovery_id)}
            onReject={()  => reject(source.discovery_id)}
            onUndo={()    => undo(source.discovery_id)}
          />
        ))}

        {/* Note about local state */}
        {!loading && !error && sources.length > 0 && (approvedCount + rejectedCount) > 0 && (
          <div style={{
            fontSize: 11, color: "var(--text-dim)", borderTop: "1px solid var(--border)",
            paddingTop: 12, marginTop: 4, textAlign: "center", fontStyle: "italic",
          }}>
            Decisions are stored in local session state only — no backend ingest endpoint exists yet.
            Approved rows will not be ingested until a POST /discover/approve endpoint is available.
          </div>
        )}
      </div>
    </div>
  );
}

function CountPill({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: 16, fontWeight: 700, color, lineHeight: 1 }}>{value}</div>
      <div style={{ fontSize: 10, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
        {label}
      </div>
    </div>
  );
}
