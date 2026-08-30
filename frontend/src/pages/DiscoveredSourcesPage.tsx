import { useEffect, useMemo, useState } from "react";
import type { DiscoveredSourceReviewItem, DiscoveredSourceReviewSummaryResponse } from "../api/types";
import { getDiscoveredSourceReview, getDiscoveredSourceReviewSummary } from "../api/adapter";

interface Filters {
  discovery_run_id: string;
  source_registry_id: string;
  adapter_id: string;
  source_type: string;
  geography: string;
  status: string;
  has_weak_url_quality: boolean;
  q: string;
}

const EMPTY_FILTERS: Filters = {
  discovery_run_id: "",
  source_registry_id: "",
  adapter_id: "",
  source_type: "",
  geography: "",
  status: "",
  has_weak_url_quality: false,
  q: "",
};

const PAGE_LIMIT = 100;

function formatCount(value: number | null | undefined): string {
  return value == null ? "0" : value.toLocaleString("en-US");
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return date.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

function sourceTypeLabel(value: string | null | undefined): string {
  if (!value) return "-";
  return value.replace(/_/g, " ");
}

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function isWeakQuality(source: DiscoveredSourceReviewItem): boolean {
  return source.source_url_quality === "public_comment_form" || source.source_url_quality === "fallback_reference";
}

function apiFilters(filters: Filters, offset = 0) {
  return {
    discovery_run_id: filters.discovery_run_id || undefined,
    source_registry_id: filters.source_registry_id || undefined,
    adapter_id: filters.adapter_id || undefined,
    source_type: filters.source_type || undefined,
    geography: filters.geography || undefined,
    status: filters.status || undefined,
    has_weak_url_quality: filters.has_weak_url_quality ? true : undefined,
    q: filters.q || undefined,
    limit: PAGE_LIMIT,
    offset,
  };
}

function topKey(counts: Record<string, number>): string {
  const entries = Object.entries(counts);
  if (entries.length === 0) return "-";
  return entries.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0][0];
}

function shortId(value: string | null | undefined): string {
  if (!value) return "-";
  return value.length > 22 ? `${value.slice(0, 22)}...` : value;
}

function filterActive(filters: Filters): boolean {
  return Object.entries(filters).some(([key, value]) => key === "has_weak_url_quality" ? value === true : value !== "");
}

const inputStyle: React.CSSProperties = {
  background: "rgba(255,255,255,0.06)",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 4,
  color: "#e2e8f0",
  fontSize: 12,
  minWidth: 0,
  outline: "none",
  padding: "6px 8px",
};

const labelStyle: React.CSSProperties = {
  color: "var(--text-dim)",
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: "0.07em",
  textTransform: "uppercase",
};

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{
      border: "1px solid var(--border)",
      borderRadius: 6,
      background: "rgba(255,255,255,0.03)",
      padding: "10px 12px",
      minWidth: 0,
    }}>
      <div style={labelStyle}>{label}</div>
      <div style={{ color: "#f1f5f9", fontSize: 20, fontWeight: 750, lineHeight: 1.15, marginTop: 6 }}>
        {value}
      </div>
      {sub && (
        <div style={{ color: "var(--text-muted)", fontSize: 11, marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {sub}
        </div>
      )}
    </div>
  );
}

function QualityBadge({ source }: { source: DiscoveredSourceReviewItem }) {
  const quality = source.source_url_quality;
  if (!quality) return <span style={{ color: "var(--text-dim)" }}>-</span>;
  const weak = isWeakQuality(source);
  return (
    <span title={source.url_quality_warning ?? undefined} style={{
      background: weak ? "rgba(245,158,11,0.12)" : "rgba(34,197,94,0.1)",
      border: `1px solid ${weak ? "rgba(245,158,11,0.35)" : "rgba(34,197,94,0.28)"}`,
      borderRadius: 3,
      color: weak ? "#fbbf24" : "#4ade80",
      display: "inline-block",
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: "0.05em",
      padding: "3px 7px",
      textTransform: "uppercase",
      whiteSpace: "nowrap",
    }}>
      {quality.replace(/_/g, " ")}
    </span>
  );
}

function DetailLine({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={labelStyle}>{label}</div>
      <div style={{ color: "#cbd5e1", fontSize: 12, lineHeight: 1.45, marginTop: 3, overflowWrap: "anywhere" }}>
        {value || "-"}
      </div>
    </div>
  );
}

function SourceDetails({ source }: { source: DiscoveredSourceReviewItem }) {
  return (
    <div style={{
      background: "rgba(0,0,0,0.24)",
      borderTop: "1px solid rgba(255,255,255,0.08)",
      padding: "14px 16px",
    }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
        <DetailLine label="Source Query" value={source.source_query} />
        <DetailLine label="Publisher" value={source.publisher} />
        <DetailLine label="Discovery Method" value={source.discovery_method} />
        <DetailLine label="Registry" value={source.source_registry_id} />
        <DetailLine label="Adapter" value={source.adapter_id} />
        <DetailLine label="Run ID" value={source.discovery_run_id} />
      </div>
      {source.snippet && (
        <div style={{ marginTop: 14 }}>
          <div style={labelStyle}>Snippet</div>
          <div style={{ color: "#cbd5e1", fontSize: 12, lineHeight: 1.6, marginTop: 5 }}>
            {source.snippet}
          </div>
        </div>
      )}
      {source.alternate_urls.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={labelStyle}>Alternate URLs</div>
          <div style={{ display: "grid", gap: 4, marginTop: 5 }}>
            {source.alternate_urls.map((url) => (
              <a key={url} href={url} target="_blank" rel="noopener noreferrer" style={{ color: "#7ec8e3", fontSize: 12, overflowWrap: "anywhere" }}>
                {url}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SourceRow({ source }: { source: DiscoveredSourceReviewItem }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <>
      <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.07)", verticalAlign: "top" }}>
        <td style={{ padding: "11px 10px", minWidth: 0 }}>
          <button
            onClick={() => setExpanded((value) => !value)}
            title={expanded ? "Hide details" : "Show details"}
            style={{
              background: "transparent",
              border: "none",
              color: expanded ? "#7ec8e3" : "#94a3b8",
              cursor: "pointer",
              fontSize: 14,
              padding: 0,
            }}
          >
            {expanded ? "▾" : "▸"}
          </button>
        </td>
        <td style={{ padding: "11px 10px", minWidth: 0 }}>
          <div style={{ color: "#e2e8f0", fontSize: 13, fontWeight: 650, lineHeight: 1.35, overflowWrap: "anywhere" }}>
            {source.source_title || "Untitled source"}
          </div>
          <a href={source.source_url} target="_blank" rel="noopener noreferrer" style={{
            color: "#7ec8e3",
            display: "block",
            fontSize: 11,
            marginTop: 4,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}>
            {hostname(source.source_url)}
          </a>
        </td>
        <td style={{ padding: "11px 10px", color: "#cbd5e1", fontSize: 12 }}>{sourceTypeLabel(source.source_type)}</td>
        <td style={{ padding: "11px 10px", color: "#cbd5e1", fontSize: 12 }}>{source.geography || "-"}</td>
        <td style={{ padding: "11px 10px", color: "#cbd5e1", fontSize: 12 }}>{source.publisher || "-"}</td>
        <td style={{ padding: "11px 10px", color: "#cbd5e1", fontSize: 12 }}>{source.status}</td>
        <td style={{ padding: "11px 10px" }}><QualityBadge source={source} /></td>
        <td style={{ padding: "11px 10px", color: "#94a3b8", fontSize: 12 }}>{shortId(source.discovery_run_id)}</td>
        <td style={{ padding: "11px 10px", color: "#94a3b8", fontSize: 12, whiteSpace: "nowrap" }}>{formatDate(source.created_at)}</td>
      </tr>
      {expanded && (
        <tr style={{ borderBottom: "1px solid rgba(126,200,227,0.2)" }}>
          <td colSpan={9} style={{ padding: 0 }}>
            <SourceDetails source={source} />
          </td>
        </tr>
      )}
    </>
  );
}

function FilterInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label style={{ display: "grid", gap: 4, minWidth: 150, flex: "1 1 150px" }}>
      <span style={labelStyle}>{label}</span>
      <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} style={inputStyle} />
    </label>
  );
}

export function DiscoveredSourcesPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [sources, setSources] = useState<DiscoveredSourceReviewItem[]>([]);
  const [summary, setSummary] = useState<DiscoveredSourceReviewSummaryResponse | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [listResponse, summaryResponse] = await Promise.all([
          getDiscoveredSourceReview(apiFilters(filters)),
          getDiscoveredSourceReviewSummary(apiFilters(filters)),
        ]);
        if (!cancelled) {
          setSources(listResponse.items);
          setTotal(listResponse.total);
          setSummary(summaryResponse);
        }
      } catch (err) {
        if (!cancelled) setError(String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [filters]);

  const sourceTypeSummary = useMemo(() => {
    const counts = summary?.counts_by_source_type ?? {};
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 3);
    return entries.length > 0 ? entries.map(([key, value]) => `${sourceTypeLabel(key)} ${value}`).join(" · ") : "No source types";
  }, [summary]);

  const active = filterActive(filters);

  function updateFilter(key: keyof Filters, value: string | boolean) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <div style={{ borderBottom: "1px solid var(--border)", flexShrink: 0, padding: "14px 20px 12px" }}>
        <div style={{ alignItems: "baseline", display: "flex", flexWrap: "wrap", gap: 12 }}>
          <h1 style={{ color: "#f1f5f9", fontSize: 16, fontWeight: 750, margin: 0 }}>Discovered Sources</h1>
          <span style={{ color: "#94a3b8", fontSize: 12 }}>Read-only pre-extraction review</span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10, marginTop: 12 }}>
          <Metric label="Total" value={formatCount(summary?.total ?? total)} />
          <Metric label="Weak URL Quality" value={formatCount(summary?.weak_url_quality_count)} sub="Review signal only" />
          <Metric label="Top Run ID" value={topKey(summary?.counts_by_discovery_run_id ?? {})} />
          <Metric label="Source Types" value={formatCount(Object.keys(summary?.counts_by_source_type ?? {}).length)} sub={sourceTypeSummary} />
        </div>
      </div>

      <div style={{
        background: "rgba(0,0,0,0.12)",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        flexShrink: 0,
        flexWrap: "wrap",
        gap: 10,
        padding: "10px 20px",
      }}>
        <FilterInput label="Search" value={filters.q} onChange={(value) => updateFilter("q", value)} placeholder="title, URL, snippet, query" />
        <FilterInput label="Run ID" value={filters.discovery_run_id} onChange={(value) => updateFilter("discovery_run_id", value)} />
        <FilterInput label="Registry" value={filters.source_registry_id} onChange={(value) => updateFilter("source_registry_id", value)} />
        <FilterInput label="Adapter" value={filters.adapter_id} onChange={(value) => updateFilter("adapter_id", value)} />
        <FilterInput label="Source Type" value={filters.source_type} onChange={(value) => updateFilter("source_type", value)} />
        <FilterInput label="Geography" value={filters.geography} onChange={(value) => updateFilter("geography", value)} />
        <label style={{ display: "grid", gap: 4, minWidth: 140 }}>
          <span style={labelStyle}>Status</span>
          <select value={filters.status} onChange={(event) => updateFilter("status", event.target.value)} style={{ ...inputStyle, cursor: "pointer" }}>
            <option value="">All statuses</option>
            <option value="discovered">Discovered</option>
            <option value="candidate">Candidate</option>
            <option value="rejected">Rejected</option>
            <option value="promoted">Promoted</option>
          </select>
        </label>
        <label style={{ alignItems: "center", color: "#cbd5e1", display: "flex", fontSize: 12, gap: 8, paddingTop: 17 }}>
          <input
            checked={filters.has_weak_url_quality}
            onChange={(event) => updateFilter("has_weak_url_quality", event.target.checked)}
            type="checkbox"
          />
          Weak URL only
        </label>
        {active && (
          <button
            onClick={() => setFilters(EMPTY_FILTERS)}
            style={{
              alignSelf: "end",
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.14)",
              borderRadius: 4,
              color: "#e2e8f0",
              cursor: "pointer",
              fontSize: 12,
              fontWeight: 650,
              padding: "6px 10px",
            }}
          >
            Clear
          </button>
        )}
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "0 20px 24px" }}>
        {loading && (
          <div style={{ color: "#94a3b8", fontSize: 13, padding: "42px 0", textAlign: "center" }}>
            Loading discovered sources...
          </div>
        )}

        {!loading && error && (
          <div style={{
            background: "rgba(239,68,68,0.08)",
            border: "1px solid rgba(239,68,68,0.3)",
            borderRadius: 6,
            color: "#fca5a5",
            fontSize: 12,
            lineHeight: 1.6,
            marginTop: 16,
            padding: "14px 16px",
          }}>
            {error}
          </div>
        )}

        {!loading && !error && sources.length === 0 && (
          <div style={{ color: "#94a3b8", fontSize: 13, padding: "42px 0", textAlign: "center" }}>
            No discovered sources match the current filters.
          </div>
        )}

        {!loading && !error && sources.length > 0 && (
          <div style={{ marginTop: 12, overflowX: "auto" }}>
            <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 8 }}>
              Showing {sources.length} of {total} sources
            </div>
            <table style={{ borderCollapse: "collapse", minWidth: 1040, tableLayout: "fixed", width: "100%" }}>
              <colgroup>
                <col style={{ width: 34 }} />
                <col style={{ width: 300 }} />
                <col style={{ width: 150 }} />
                <col style={{ width: 120 }} />
                <col style={{ width: 140 }} />
                <col style={{ width: 95 }} />
                <col style={{ width: 150 }} />
                <col style={{ width: 150 }} />
                <col style={{ width: 105 }} />
              </colgroup>
              <thead>
                <tr style={{ borderBottom: "2px solid rgba(255,255,255,0.1)" }}>
                  {["", "Source", "Type", "Geography", "Publisher", "Status", "URL Quality", "Run ID", "Created"].map((label) => (
                    <th key={label} style={{
                      background: "var(--bg)",
                      color: "#94a3b8",
                      fontSize: 10,
                      fontWeight: 750,
                      letterSpacing: "0.08em",
                      padding: "9px 10px",
                      position: "sticky",
                      textAlign: "left",
                      textTransform: "uppercase",
                      top: 0,
                      whiteSpace: "nowrap",
                      zIndex: 1,
                    }}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sources.map((source) => <SourceRow key={source.id} source={source} />)}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
