import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import type { ProjectListItem, RiskTier, LifecycleState } from "../../api/types";
import { RiskBadge, LifecycleBadge } from "../shared/Badge";

type SortKey = "current_hazard" | "deadline_probability" | "latest_update_date" | "modeled_primary_load_mw";
type SortDir = "asc" | "desc";

interface Props {
  projects: ProjectListItem[];
  loading: boolean;
}

const COLUMNS: { key: string; label: string; sortKey?: SortKey; width?: number }[] = [
  { key: "project_name", label: "Project" },
  { key: "state", label: "State", width: 60 },
  { key: "county", label: "County", width: 110 },
  { key: "region_or_rto", label: "RTO", width: 80 },
  { key: "lifecycle_state", label: "Lifecycle", width: 150 },
  { key: "risk_tier", label: "Model Risk", width: 100 },
  { key: "modeled_primary_load_mw", label: "Load (MW)", sortKey: "modeled_primary_load_mw", width: 100 },
  { key: "phase_count", label: "Phases", width: 70 },
  { key: "current_hazard", label: "Q-Hazard", sortKey: "current_hazard", width: 90 },
  { key: "deadline_probability", label: "Deadline P", sortKey: "deadline_probability", width: 100 },
  { key: "latest_update_date", label: "Last Update", sortKey: "latest_update_date", width: 110 },
];

function pct(v: number) {
  return `${(v * 100).toFixed(1)}%`;
}

function hazardColor(v: number) {
  if (v >= 0.12) return "#ef4444";
  if (v >= 0.07) return "#f97316";
  if (v >= 0.04) return "#eab308";
  return "#22c55e";
}

const MW_BUCKETS = ["All", "300–399 MW", "400–599 MW", "600+ MW"];
const LIFECYCLE_OPTIONS: LifecycleState[] = [
  "monitoring_ready", "under_review", "active_construction", "delayed", "canceled"
];
const RISK_OPTIONS: RiskTier[] = ["high", "elevated", "moderate", "low"];
const RTO_OPTIONS = ["ERCOT", "WECC", "PJM", "MISO", "SERC"];

function inMwBucket(mw: number, bucket: string): boolean {
  if (bucket === "All") return true;
  if (bucket === "300–399 MW") return mw >= 300 && mw < 400;
  if (bucket === "400–599 MW") return mw >= 400 && mw < 600;
  if (bucket === "600+ MW") return mw >= 600;
  return true;
}

export function ProjectListTable({ projects, loading }: Props) {
  const navigate = useNavigate();
  const [sortKey, setSortKey] = useState<SortKey>("deadline_probability");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [mwBucket, setMwBucket] = useState("All");
  const [lifecycle, setLifecycle] = useState("");
  const [risk, setRisk] = useState("");
  const [rto, setRto] = useState("");

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const filtered = useMemo(() => {
    return projects
      .filter(p => inMwBucket(p.modeled_primary_load_mw, mwBucket))
      .filter(p => !lifecycle || p.lifecycle_state === lifecycle)
      .filter(p => !risk || p.risk_tier === risk)
      .filter(p => !rto || p.region_or_rto === rto);
  }, [projects, mwBucket, lifecycle, risk, rto]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === "string" && typeof bv === "string") {
        return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      return sortDir === "asc"
        ? (av as number) - (bv as number)
        : (bv as number) - (av as number);
    });
  }, [filtered, sortKey, sortDir]);

  function SortIndicator({ col }: { col?: SortKey }) {
    if (!col || col !== sortKey) return <span style={{ color: "var(--text-dim)", marginLeft: 4 }}>↕</span>;
    return <span style={{ color: "var(--accent)", marginLeft: 4 }}>{sortDir === "asc" ? "↑" : "↓"}</span>;
  }

  const filterSelect = {
    background: "var(--bg-active)",
    border: "1px solid var(--border)",
    borderRadius: 4,
    color: "var(--text-muted)",
    fontSize: 12,
    padding: "4px 8px",
    fontFamily: "inherit",
    cursor: "pointer",
  } as const;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Filter bar */}
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "10px 16px",
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-surface)",
        flexWrap: "wrap",
      }}>
        <span style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600, marginRight: 4 }}>
          Filters
        </span>
        <select style={filterSelect} value={mwBucket} onChange={e => setMwBucket(e.target.value)}>
          {MW_BUCKETS.map(b => <option key={b}>{b}</option>)}
        </select>
        <select style={filterSelect} value={lifecycle} onChange={e => setLifecycle(e.target.value)}>
          <option value="">All Lifecycle States</option>
          {LIFECYCLE_OPTIONS.map(l => <option key={l} value={l}>{l.replace(/_/g, " ")}</option>)}
        </select>
        <select style={filterSelect} value={risk} onChange={e => setRisk(e.target.value)}>
          <option value="">All Model Risk Tiers</option>
          {RISK_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
        <select style={filterSelect} value={rto} onChange={e => setRto(e.target.value)}>
          <option value="">All RTOs</option>
          {RTO_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-dim)" }}>
          {sorted.length} of {projects.length} projects
        </span>
      </div>
      <div style={{ padding: "5px 16px", background: "var(--bg-surface)", borderBottom: "1px solid var(--border)", fontSize: 10, color: "var(--text-dim)", letterSpacing: "0.03em" }}>
        Model Risk tier is derived from the ML scoring model (Q-Hazard / Deadline P). It may differ from the Evidence-Based Risk Signal shown on each project's Evidence Signal tab.
      </div>

      {/* Table */}
      <div style={{ flex: 1, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-surface)", position: "sticky", top: 0, zIndex: 1 }}>
              {COLUMNS.map(col => (
                <th
                  key={col.key}
                  onClick={() => col.sortKey && handleSort(col.sortKey)}
                  style={{
                    textAlign: "left",
                    padding: "8px 12px",
                    fontSize: 11,
                    fontWeight: 600,
                    color: col.sortKey === sortKey ? "var(--accent)" : "var(--text-dim)",
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    cursor: col.sortKey ? "pointer" : "default",
                    userSelect: "none",
                    whiteSpace: "nowrap",
                    width: col.width,
                  }}
                >
                  {col.label}
                  {col.sortKey && <SortIndicator col={col.sortKey} />}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={COLUMNS.length} style={{ padding: "32px 16px", color: "var(--text-muted)", textAlign: "center" }}>
                  Loading…
                </td>
              </tr>
            )}
            {!loading && sorted.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length} style={{ padding: "32px 16px", color: "var(--text-muted)", textAlign: "center" }}>
                  No projects match current filters.
                </td>
              </tr>
            )}
            {!loading && sorted.map((p, i) => (
              <tr
                key={p.project_id}
                onClick={() => navigate(`/projects/${p.project_id}`)}
                style={{
                  borderBottom: "1px solid var(--border-light)",
                  background: i % 2 === 0 ? "var(--bg)" : "var(--bg-surface)",
                  cursor: "pointer",
                  transition: "background 0.1s",
                }}
                onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")}
                onMouseLeave={e => (e.currentTarget.style.background = i % 2 === 0 ? "var(--bg)" : "var(--bg-surface)")}
              >
                <td style={{ padding: "9px 12px" }}>
                  <div style={{ fontWeight: 500 }}>{p.project_name}</div>
                  {p.developer && (
                    <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>{p.developer}</div>
                  )}
                </td>
                <td style={{ padding: "9px 12px", color: "var(--text-muted)" }}>{p.state}</td>
                <td style={{ padding: "9px 12px", color: "var(--text-muted)", fontSize: 12 }}>{p.county ?? "—"}</td>
                <td style={{ padding: "9px 12px", color: "var(--text-muted)" }}>{p.region_or_rto}</td>
                <td style={{ padding: "9px 12px" }}><LifecycleBadge state={p.lifecycle_state} /></td>
                <td style={{ padding: "9px 12px" }}><RiskBadge tier={p.risk_tier} /></td>
                <td style={{ padding: "9px 12px", fontFamily: '"JetBrains Mono", monospace', fontSize: 12 }}>
                  {p.modeled_primary_load_mw} MW
                </td>
                <td style={{ padding: "9px 12px", color: "var(--text-muted)", textAlign: "center" }}>
                  {p.phase_count}
                </td>
                <td style={{ padding: "9px 12px" }}>
                  <span style={{
                    fontFamily: '"JetBrains Mono", monospace',
                    fontSize: 12,
                    fontWeight: 600,
                    color: hazardColor(p.current_hazard),
                  }}>
                    {pct(p.current_hazard)}
                  </span>
                </td>
                <td style={{ padding: "9px 12px" }}>
                  <span style={{
                    fontFamily: '"JetBrains Mono", monospace',
                    fontSize: 12,
                    fontWeight: 600,
                    color: hazardColor(p.deadline_probability / 2),
                  }}>
                    {pct(p.deadline_probability)}
                  </span>
                </td>
                <td style={{ padding: "9px 12px", color: "var(--text-muted)", fontSize: 12 }}>
                  {p.latest_update_date}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
