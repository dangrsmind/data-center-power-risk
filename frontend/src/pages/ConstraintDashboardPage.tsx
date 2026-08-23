import { useEffect, useState, useCallback } from "react";
import type { ConstraintSummaryResponse, ConstraintSummaryItem } from "../api/types";
import { getConstraintSummary } from "../api/adapter";

function fmtLabel(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function TriageBadge({ tier }: { tier: string | null | undefined }) {
  if (!tier) return <span style={{ color: "#6b7280", fontSize: 11 }}>—</span>;
  const c: Record<string, { color: string; bg: string }> = {
    high:   { color: "#f87171", bg: "rgba(248,113,113,0.12)" },
    medium: { color: "#fbbf24", bg: "rgba(251,191,36,0.12)" },
    low:    { color: "#34d399", bg: "rgba(52,211,153,0.12)" },
  };
  const { color, bg } = c[tier] ?? { color: "#94a3b8", bg: "rgba(148,163,184,0.12)" };
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, padding: "2px 7px", borderRadius: 4,
      color, background: bg, border: `1px solid ${color}44`,
      whiteSpace: "nowrap" as const,
    }}>
      {tier.toUpperCase()}
    </span>
  );
}

function DecisionBadge({ decision }: { decision: string | null | undefined }) {
  if (!decision) return <span style={{ color: "#6b7280", fontSize: 11 }}>—</span>;
  const colorMap: Record<string, string> = {
    ready_for_verification:   "#34d399",
    needs_source:             "#f59e0b",
    needs_location:           "#f59e0b",
    likely_duplicate:         "#f87171",
    rejected_dataset_only:    "#ef4444",
    rejected_not_data_center: "#ef4444",
    rejected_stale:           "#ef4444",
    keep_under_review:        "#818cf8",
  };
  const color = colorMap[decision] ?? "#94a3b8";
  return (
    <span style={{
      fontSize: 11, fontWeight: 500, padding: "2px 7px", borderRadius: 4,
      color, background: `${color}18`, border: `1px solid ${color}33`,
      whiteSpace: "nowrap" as const,
    }}>
      {fmtLabel(decision)}
    </span>
  );
}

function VerifBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span style={{ color: "#6b7280", fontSize: 11 }}>—</span>;
  const color =
    status === "verified"        ? "#34d399" :
    status.startsWith("reject")  ? "#f87171" : "#94a3b8";
  return (
    <span style={{
      fontSize: 11, padding: "2px 7px", borderRadius: 4,
      color, background: `${color}18`, border: `1px solid ${color}33`,
    }}>
      {fmtLabel(status)}
    </span>
  );
}

function CsvChip() {
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, padding: "1px 5px", borderRadius: 3,
      color: "#818cf8", background: "rgba(129,140,248,0.1)", border: "1px solid rgba(129,140,248,0.3)",
    }}>
      CSV
    </span>
  );
}

function Card({
  title,
  children,
  style,
}: {
  title: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <div style={{
      background: "var(--bg-surface)",
      border: "1px solid var(--border)",
      borderRadius: 8,
      padding: "14px 16px",
      ...style,
    }}>
      <div style={{
        fontSize: 11, fontWeight: 700, letterSpacing: "0.06em",
        textTransform: "uppercase" as const, color: "var(--text-dim)", marginBottom: 10,
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function StatCard({ label, value, accent }: { label: string; value: number; accent?: string }) {
  return (
    <div style={{
      background: "var(--bg-surface)",
      border: "1px solid var(--border)",
      borderRadius: 8,
      padding: "14px 16px",
      minWidth: 110,
      flex: "1 1 110px",
    }}>
      <div style={{
        fontSize: 26, fontWeight: 700, color: accent ?? "var(--text)",
        fontVariantNumeric: "tabular-nums" as const,
      }}>
        {value}
      </div>
      <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>{label}</div>
    </div>
  );
}

function CountTable({ data, limit = 20 }: { data: Record<string, number>; limit?: number }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]).slice(0, limit);
  if (entries.length === 0) {
    return <div style={{ fontSize: 12, color: "#6b7280" }}>No data</div>;
  }
  return (
    <table style={{ width: "100%", borderCollapse: "collapse" as const, fontSize: 12 }}>
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
            <td style={{ padding: "4px 8px 4px 0", color: "#cbd5e1" }}>{fmtLabel(k)}</td>
            <td style={{
              padding: "4px 0", textAlign: "right" as const,
              color: "#f1f5f9", fontVariantNumeric: "tabular-nums" as const, fontWeight: 600,
            }}>
              {v}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function FilterSelect({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  placeholder: string;
}) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border)",
        borderRadius: 4,
        color: value ? "var(--text)" : "var(--text-dim)",
        fontSize: 12,
        padding: "5px 8px",
        cursor: "pointer",
      }}
    >
      <option value="">{placeholder}</option>
      {options.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

const TRIAGE_OPTIONS = [
  { value: "high",   label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low",    label: "Low" },
];

const DECISION_OPTIONS = [
  { value: "needs_source",             label: "Needs Source" },
  { value: "needs_location",           label: "Needs Location" },
  { value: "likely_duplicate",         label: "Likely Duplicate" },
  { value: "ready_for_verification",   label: "Ready for Verification" },
  { value: "rejected_dataset_only",    label: "Rejected (Dataset Only)" },
  { value: "rejected_not_data_center", label: "Rejected (Not Data Center)" },
  { value: "rejected_stale",           label: "Rejected (Stale)" },
  { value: "keep_under_review",        label: "Keep Under Review" },
];

const ENERGY_OPTIONS = [
  { value: "grid_only",                label: "Grid Only" },
  { value: "grid_plus_backup",         label: "Grid + Backup" },
  { value: "grid_plus_onsite",         label: "Grid + Onsite" },
  { value: "dedicated_gas_generation", label: "Dedicated Gas" },
  { value: "diesel_generation",        label: "Diesel Generation" },
  { value: "fuel_cell",                label: "Fuel Cell" },
  { value: "nuclear_or_smr",           label: "Nuclear / SMR" },
  { value: "hybrid_power",             label: "Hybrid Power" },
  { value: "unknown",                  label: "Unknown" },
];

const FRICTION_OPTIONS = [
  { value: "community_opposition",        label: "Community Opposition" },
  { value: "public_hearing",              label: "Public Hearing" },
  { value: "moratorium",                  label: "Moratorium" },
  { value: "zoning_land_use",             label: "Zoning / Land Use" },
  { value: "litigation",                  label: "Litigation" },
  { value: "permit_delay",               label: "Permit Delay" },
  { value: "environmental_review",        label: "Environmental Review" },
  { value: "air_permitting",              label: "Air Permitting" },
  { value: "emissions_concern",           label: "Emissions Concern" },
  { value: "water_cooling",              label: "Water / Cooling" },
  { value: "noise_concern",              label: "Noise Concern" },
  { value: "traffic_concern",            label: "Traffic Concern" },
  { value: "tax_incentive_backlash",     label: "Tax Incentive Backlash" },
  { value: "political_opposition",       label: "Political Opposition" },
  { value: "utility_regulatory_approval", label: "Utility / Regulatory" },
  { value: "cost_financing",             label: "Cost / Financing" },
  { value: "schedule_credibility",       label: "Schedule Credibility" },
];

const STATUS_OPTIONS = [
  { value: "active",   label: "Active" },
  { value: "archived", label: "Archived" },
  { value: "promoted", label: "Promoted" },
  { value: "rejected", label: "Rejected" },
];

const TOP_CANDIDATE_HEADERS = [
  "Candidate", "Triage", "Recommended Action", "Decision",
  "Verification", "Status", "Energy Strategy", "Siting Friction",
];

function TopCandidateRow({ item }: { item: ConstraintSummaryItem }) {
  const frictionCategories = item.siting_friction_categories.filter(s => s !== "unknown");
  return (
    <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
      {/* Name + location + source link */}
      <td style={{ padding: "8px 12px 8px 0", verticalAlign: "top" as const }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" as const }}>
          <a
            href="/project-candidates"
            style={{ color: "#93c5fd", fontSize: 13, fontWeight: 500, textDecoration: "none" }}
            title="View on Project Candidates page"
          >
            {item.candidate_name}
          </a>
          {item.csv_provenance && <CsvChip />}
        </div>
        {item.state && (
          <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>{item.state}</div>
        )}
        {item.primary_source_url && (
          <a
            href={item.primary_source_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: 11, color: "#818cf8", textDecoration: "none", marginTop: 2, display: "block" }}
          >
            ↗ source
          </a>
        )}
      </td>
      {/* Triage tier + score */}
      <td style={{ padding: "8px 12px", verticalAlign: "top" as const, whiteSpace: "nowrap" as const }}>
        <TriageBadge tier={item.triage_tier} />
        {item.triage_score != null && (
          <div style={{ fontSize: 10, color: "#6b7280", marginTop: 3, fontVariantNumeric: "tabular-nums" as const }}>
            {(item.triage_score * 100).toFixed(0)}%
          </div>
        )}
      </td>
      {/* Recommended action */}
      <td style={{ padding: "8px 12px", verticalAlign: "top" as const }}>
        {item.recommended_action
          ? <span style={{ fontSize: 11, color: "#94a3b8" }}>{fmtLabel(item.recommended_action)}</span>
          : <span style={{ fontSize: 11, color: "#4b5563" }}>—</span>}
      </td>
      {/* Review decision */}
      <td style={{ padding: "8px 12px", verticalAlign: "top" as const }}>
        <DecisionBadge decision={item.review_decision} />
      </td>
      {/* Verification status */}
      <td style={{ padding: "8px 12px", verticalAlign: "top" as const }}>
        <VerifBadge status={item.verification_status} />
      </td>
      {/* Status */}
      <td style={{ padding: "8px 12px", verticalAlign: "top" as const }}>
        <span style={{ fontSize: 11, color: "#94a3b8" }}>{item.status}</span>
      </td>
      {/* Energy strategy */}
      <td style={{ padding: "8px 12px", verticalAlign: "top" as const }}>
        {item.energy_strategy
          ? <span style={{ fontSize: 11, color: "#6ee7b7" }}>{fmtLabel(item.energy_strategy)}</span>
          : <span style={{ fontSize: 11, color: "#4b5563" }}>—</span>}
      </td>
      {/* Siting friction categories */}
      <td style={{ padding: "8px 12px", verticalAlign: "top" as const }}>
        {frictionCategories.length > 0 ? (
          <div style={{ display: "flex", flexWrap: "wrap" as const, gap: 3 }}>
            {frictionCategories.slice(0, 3).map(s => (
              <span key={s} style={{
                fontSize: 10, padding: "1px 4px", borderRadius: 3,
                color: "#fbbf24", background: "rgba(251,191,36,0.1)", border: "1px solid rgba(251,191,36,0.25)",
              }}>
                {fmtLabel(s)}
              </span>
            ))}
            {frictionCategories.length > 3 && (
              <span style={{ fontSize: 10, color: "#6b7280" }}>
                +{frictionCategories.length - 3}
              </span>
            )}
          </div>
        ) : (
          <span style={{ fontSize: 11, color: "#4b5563" }}>—</span>
        )}
      </td>
    </tr>
  );
}

export function ConstraintDashboardPage() {
  const [data, setData] = useState<ConstraintSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [filterStatus,   setFilterStatus]   = useState("");
  const [filterTriage,   setFilterTriage]   = useState("");
  const [filterDecision, setFilterDecision] = useState("");
  const [filterEnergy,   setFilterEnergy]   = useState("");
  const [filterFriction, setFilterFriction] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getConstraintSummary({
        ...(filterStatus   ? { status: filterStatus }                      : {}),
        ...(filterTriage   ? { triage_tier: filterTriage }                 : {}),
        ...(filterDecision ? { review_decision: filterDecision }           : {}),
        ...(filterEnergy   ? { energy_strategy: filterEnergy }             : {}),
        ...(filterFriction ? { siting_friction_category: filterFriction }  : {}),
      });
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [filterStatus, filterTriage, filterDecision, filterEnergy, filterFriction]);

  useEffect(() => { void load(); }, [load]);

  const hasFilters = !!(filterStatus || filterTriage || filterDecision || filterEnergy || filterFriction);

  function clearFilters() {
    setFilterStatus("");
    setFilterTriage("");
    setFilterDecision("");
    setFilterEnergy("");
    setFilterFriction("");
  }

  return (
    <div style={{ flex: 1, overflowY: "auto" as const, padding: "20px 24px 48px" }}>

      {/* Page header */}
      <div style={{ marginBottom: 16 }}>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: "var(--text)" }}>
          Constraint Dashboard
        </h1>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--text-dim)", maxWidth: 700 }}>
          Read-only summary counts from the constraint summary API. These are review signals only —
          they do not verify projects, imply promotion, or change guarded admission rules.
        </p>
      </div>

      {/* Filter bar */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" as const, alignItems: "center", marginBottom: 16 }}>
        <FilterSelect value={filterStatus}   onChange={setFilterStatus}   options={STATUS_OPTIONS}   placeholder="All statuses" />
        <FilterSelect value={filterTriage}   onChange={setFilterTriage}   options={TRIAGE_OPTIONS}   placeholder="All triage tiers" />
        <FilterSelect value={filterDecision} onChange={setFilterDecision} options={DECISION_OPTIONS} placeholder="All decisions" />
        <FilterSelect value={filterEnergy}   onChange={setFilterEnergy}   options={ENERGY_OPTIONS}   placeholder="All energy strategies" />
        <FilterSelect value={filterFriction} onChange={setFilterFriction} options={FRICTION_OPTIONS} placeholder="All friction categories" />
        {hasFilters && (
          <button
            onClick={clearFilters}
            style={{
              background: "none", border: "1px solid var(--border)", borderRadius: 4,
              color: "var(--text-dim)", fontSize: 12, padding: "5px 10px", cursor: "pointer",
            }}
          >
            Clear filters
          </button>
        )}
        <button
          onClick={() => void load()}
          disabled={loading}
          style={{
            marginLeft: "auto",
            background: "none", border: "1px solid var(--border)", borderRadius: 4,
            color: "var(--text-dim)", fontSize: 12, padding: "5px 10px",
            cursor: loading ? "not-allowed" : "pointer",
            opacity: loading ? 0.5 : 1,
          }}
        >
          {loading ? "Loading…" : "↻ Refresh"}
        </button>
      </div>

      {/* Loading */}
      {loading && (
        <div style={{ color: "var(--text-dim)", fontSize: 13, padding: "32px 0" }}>
          Loading constraint summary…
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div style={{
          background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)",
          borderRadius: 8, padding: "14px 16px", color: "#fca5a5", fontSize: 13, marginBottom: 16,
        }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && data && data.total_candidates === 0 && (
        <div style={{
          background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 8,
          padding: "40px 24px", textAlign: "center" as const, color: "var(--text-dim)", fontSize: 13,
        }}>
          No candidates found{hasFilters ? " matching the current filters" : ""}.{" "}
          {hasFilters && (
            <button
              onClick={clearFilters}
              style={{ background: "none", border: "none", color: "#818cf8", fontSize: 13, cursor: "pointer", padding: 0 }}
            >
              Clear filters
            </button>
          )}
        </div>
      )}

      {/* Dashboard content */}
      {!loading && !error && data && data.total_candidates > 0 && (
        <div style={{ display: "flex", flexDirection: "column" as const, gap: 16 }}>

          {/* Stat cards */}
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" as const }}>
            <StatCard label="Total Candidates"        value={data.total_candidates} />
            <StatCard label="High Priority Review"    value={data.high_priority_review_count}    accent="#f87171" />
            <StatCard label="Ready for Verification"  value={data.ready_for_verification_count}  accent="#34d399" />
            <StatCard label="Needs Source"            value={data.needs_source_count}            accent="#f59e0b" />
            <StatCard label="Likely Duplicate"        value={data.likely_duplicate_count}        accent="#f87171" />
            <StatCard label="Dataset-only Rejected"   value={data.dataset_only_rejected_count}   accent="#6b7280" />
          </div>

          {/* CSV vs Web provenance pills */}
          {(data.csv_backed_count > 0 || data.web_discovered_count > 0) && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" as const, alignItems: "center" }}>
              <span style={{ fontSize: 11, color: "var(--text-dim)", marginRight: 2 }}>Provenance:</span>
              {data.csv_backed_count > 0 && (
                <span style={{
                  fontSize: 12, fontWeight: 600, padding: "3px 10px", borderRadius: 6,
                  color: "#818cf8", background: "rgba(129,140,248,0.1)", border: "1px solid rgba(129,140,248,0.3)",
                }}>
                  ⊞ {data.csv_backed_count} CSV-backed
                </span>
              )}
              {data.web_discovered_count > 0 && (
                <span style={{
                  fontSize: 12, fontWeight: 600, padding: "3px 10px", borderRadius: 6,
                  color: "#60a5fa", background: "rgba(96,165,250,0.1)", border: "1px solid rgba(96,165,250,0.3)",
                }}>
                  ⊗ {data.web_discovered_count} Web-discovered
                </span>
              )}
            </div>
          )}

          {/* Status | Verification status */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Card title="By Status">
              <CountTable data={data.by_status} />
            </Card>
            <Card title="By Verification Status">
              <CountTable data={data.by_verification_status} />
            </Card>
          </div>

          {/* Triage tiers | Review decisions */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Card title="Triage Tier">
              <CountTable data={data.by_triage_tier} />
            </Card>
            <Card title="Review Decision">
              <CountTable data={data.by_review_decision} />
            </Card>
          </div>

          {/* Energy strategies | Energy risk tags */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Card title={`Energy Strategy — ${data.with_energy_strategy_count} classified`}>
              <CountTable data={data.by_energy_strategy} />
            </Card>
            <Card title="Top Energy Risk Tags">
              <CountTable data={data.by_energy_risk_tag} limit={10} />
            </Card>
          </div>

          {/* Siting friction categories | Top siting warnings */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Card title={`Siting Friction Categories — ${data.with_siting_friction_count} with friction`}>
              <CountTable data={data.by_siting_friction_category} />
            </Card>
            <Card title="Top Siting Friction Warnings">
              <CountTable data={data.by_siting_friction_warning} limit={8} />
            </Card>
          </div>

          {/* Top review-priority candidates */}
          {data.top_review_priority_candidates.length > 0 && (
            <Card title={`Top Review-Priority Candidates — ${data.top_review_priority_candidates.length} shown`}>
              <div style={{ overflowX: "auto" as const }}>
                <table style={{ width: "100%", borderCollapse: "collapse" as const, fontSize: 12 }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}>
                      {TOP_CANDIDATE_HEADERS.map(h => (
                        <th key={h} style={{
                          padding: "6px 12px 8px 0", textAlign: "left" as const, fontSize: 10,
                          fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase" as const,
                          color: "var(--text-dim)", whiteSpace: "nowrap" as const,
                        }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.top_review_priority_candidates.map(item => (
                      <TopCandidateRow key={item.candidate_id} item={item} />
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ marginTop: 12, fontSize: 11, color: "var(--text-dim)" }}>
                Sorted by high triage first, then triage score. No promote actions on this page.{" "}
                <a href="/project-candidates" style={{ color: "#818cf8", textDecoration: "none" }}>
                  Open Project Candidates page →
                </a>
              </div>
            </Card>
          )}

        </div>
      )}
    </div>
  );
}
