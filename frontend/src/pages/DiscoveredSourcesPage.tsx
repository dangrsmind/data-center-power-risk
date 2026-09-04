import { useEffect, useMemo, useState } from "react";
import type {
  DiscoveredSourceReviewItem,
  DiscoveredSourceReviewStatus,
  DiscoveredSourceReviewSummaryResponse,
} from "../api/types";
import {
  getDiscoveredSourceReview,
  getDiscoveredSourceReviewSummary,
  updateDiscoveredSourceReview,
} from "../api/adapter";

interface Filters {
  discovery_run_id: string;
  source_registry_id: string;
  adapter_id: string;
  source_type: string;
  geography: string;
  status: string;
  has_weak_url_quality: boolean;
  review_status: string;
  reviewed_by: string;
  has_review_notes: boolean;
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
  review_status: "",
  reviewed_by: "",
  has_review_notes: false,
  q: "",
};

const PAGE_LIMIT = 100;
const REVIEW_STATUSES: DiscoveredSourceReviewStatus[] = ["unreviewed", "useful", "maybe", "noisy", "weak", "rejected"];

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

function reviewStatusLabel(value: string | null | undefined): string {
  return (value || "unreviewed").replace(/_/g, " ");
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
    review_status: filters.review_status || undefined,
    reviewed_by: filters.reviewed_by || undefined,
    has_review_notes: filters.has_review_notes ? true : undefined,
    q: filters.q || undefined,
    limit: PAGE_LIMIT,
    offset,
  };
}

function shortId(value: string | null | undefined): string {
  if (!value) return "-";
  return value.length > 22 ? `${value.slice(0, 22)}...` : value;
}

function filterActive(filters: Filters): boolean {
  return Object.entries(filters).some(([key, value]) => {
    if (key === "has_weak_url_quality" || key === "has_review_notes") return value === true;
    return value !== "";
  });
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

function ReviewBadge({ status }: { status: DiscoveredSourceReviewStatus }) {
  const palette: Record<DiscoveredSourceReviewStatus, { bg: string; border: string; color: string }> = {
    unreviewed: { bg: "rgba(148,163,184,0.08)", border: "rgba(148,163,184,0.25)", color: "#cbd5e1" },
    useful: { bg: "rgba(34,197,94,0.1)", border: "rgba(34,197,94,0.32)", color: "#4ade80" },
    maybe: { bg: "rgba(56,189,248,0.1)", border: "rgba(56,189,248,0.32)", color: "#7dd3fc" },
    noisy: { bg: "rgba(248,113,113,0.09)", border: "rgba(248,113,113,0.3)", color: "#fca5a5" },
    weak: { bg: "rgba(245,158,11,0.12)", border: "rgba(245,158,11,0.35)", color: "#fbbf24" },
    rejected: { bg: "rgba(239,68,68,0.12)", border: "rgba(239,68,68,0.38)", color: "#f87171" },
  };
  const colors = palette[status];
  return (
    <span style={{
      background: colors.bg,
      border: `1px solid ${colors.border}`,
      borderRadius: 3,
      color: colors.color,
      display: "inline-block",
      fontSize: 10,
      fontWeight: 750,
      letterSpacing: "0.05em",
      padding: "3px 7px",
      textTransform: "uppercase",
      whiteSpace: "nowrap",
    }}>
      {reviewStatusLabel(status)}
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
        <DetailLine label="Reviewed By" value={source.reviewed_by} />
        <DetailLine label="Reviewed At" value={formatDate(source.reviewed_at)} />
      </div>
      {source.review_notes && (
        <div style={{ marginTop: 14 }}>
          <div style={labelStyle}>Review Notes</div>
          <div style={{ color: "#cbd5e1", fontSize: 12, lineHeight: 1.6, marginTop: 5 }}>
            {source.review_notes}
          </div>
        </div>
      )}
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

function SourceRow({
  source,
  onSaved,
  onError,
}: {
  source: DiscoveredSourceReviewItem;
  onSaved: (source: DiscoveredSourceReviewItem) => void;
  onError: (message: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [reviewStatus, setReviewStatus] = useState<DiscoveredSourceReviewStatus>(source.review_status);
  const [reviewNotes, setReviewNotes] = useState(source.review_notes ?? "");
  const [reviewedBy, setReviewedBy] = useState(source.reviewed_by ?? "");
  const [saving, setSaving] = useState(false);
  const dirty = reviewStatus !== source.review_status || reviewNotes !== (source.review_notes ?? "") || reviewedBy !== (source.reviewed_by ?? "");

  useEffect(() => {
    setReviewStatus(source.review_status);
    setReviewNotes(source.review_notes ?? "");
    setReviewedBy(source.reviewed_by ?? "");
  }, [source.review_status, source.review_notes, source.reviewed_by]);

  async function saveReview() {
    setSaving(true);
    onError("");
    try {
      const updated = await updateDiscoveredSourceReview(source.id, {
        review_status: reviewStatus === "unreviewed" ? null : reviewStatus,
        review_notes: reviewNotes,
        reviewed_by: reviewedBy,
      });
      setReviewStatus(updated.review_status);
      setReviewNotes(updated.review_notes ?? "");
      setReviewedBy(updated.reviewed_by ?? "");
      onSaved(updated);
    } catch (err) {
      onError(String(err));
    } finally {
      setSaving(false);
    }
  }

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
        <td style={{ padding: "11px 10px" }}><ReviewBadge status={source.review_status} /></td>
        <td style={{ padding: "8px 10px" }}>
          <div style={{ display: "grid", gap: 6 }}>
            <select
              value={reviewStatus}
              onChange={(event) => setReviewStatus(event.target.value as DiscoveredSourceReviewStatus)}
              style={{ ...inputStyle, cursor: "pointer", width: "100%" }}
            >
              {REVIEW_STATUSES.map((status) => (
                <option key={status} value={status}>{reviewStatusLabel(status)}</option>
              ))}
            </select>
            <textarea
              value={reviewNotes}
              onChange={(event) => setReviewNotes(event.target.value)}
              placeholder="Notes"
              rows={2}
              style={{ ...inputStyle, fontFamily: "inherit", lineHeight: 1.35, minHeight: 48, resize: "vertical", width: "100%" }}
            />
            <div style={{ display: "flex", gap: 6 }}>
              <input
                value={reviewedBy}
                onChange={(event) => setReviewedBy(event.target.value)}
                placeholder="Reviewer"
                style={{ ...inputStyle, flex: 1, width: "100%" }}
              />
              <button
                disabled={!dirty || saving}
                onClick={saveReview}
                style={{
                  background: dirty ? "rgba(126,200,227,0.16)" : "rgba(255,255,255,0.04)",
                  border: `1px solid ${dirty ? "rgba(126,200,227,0.4)" : "rgba(255,255,255,0.12)"}`,
                  borderRadius: 4,
                  color: dirty ? "#bae6fd" : "#64748b",
                  cursor: !dirty || saving ? "default" : "pointer",
                  fontSize: 12,
                  fontWeight: 700,
                  padding: "6px 9px",
                  whiteSpace: "nowrap",
                }}
              >
                {saving ? "Saving" : "Save"}
              </button>
            </div>
          </div>
        </td>
        <td style={{ padding: "11px 10px", color: "#94a3b8", fontSize: 12 }}>{shortId(source.discovery_run_id)}</td>
        <td style={{ padding: "11px 10px", color: "#94a3b8", fontSize: 12, whiteSpace: "nowrap" }}>{formatDate(source.created_at)}</td>
      </tr>
      {expanded && (
        <tr style={{ borderBottom: "1px solid rgba(126,200,227,0.2)" }}>
          <td colSpan={11} style={{ padding: 0 }}>
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
  const [saveError, setSaveError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      setSaveError(null);
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
  }, [filters, refreshToken]);

  const sourceTypeSummary = useMemo(() => {
    const counts = summary?.counts_by_source_type ?? {};
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 3);
    return entries.length > 0 ? entries.map(([key, value]) => `${sourceTypeLabel(key)} ${value}`).join(" · ") : "No source types";
  }, [summary]);

  const active = filterActive(filters);

  function updateFilter(key: keyof Filters, value: string | boolean) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function updateSavedSource(updated: DiscoveredSourceReviewItem) {
    setSources((current) => current.map((source) => source.id === updated.id ? updated : source));
    setSaveError(null);
    setRefreshToken((value) => value + 1);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <div style={{ borderBottom: "1px solid var(--border)", flexShrink: 0, padding: "14px 20px 12px" }}>
        <div style={{ alignItems: "baseline", display: "flex", flexWrap: "wrap", gap: 12 }}>
          <h1 style={{ color: "#f1f5f9", fontSize: 16, fontWeight: 750, margin: 0 }}>Discovered Sources</h1>
          <span style={{ color: "#94a3b8", fontSize: 12 }}>Analyst triage before extraction</span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10, marginTop: 12 }}>
          <Metric label="Total" value={formatCount(summary?.total ?? total)} />
          <Metric label="Reviewed" value={formatCount(summary?.reviewed_count)} sub={`${formatCount(summary?.unreviewed_count)} unreviewed`} />
          <Metric label="Useful / Maybe" value={`${formatCount(summary?.useful_count)} / ${formatCount(summary?.maybe_count)}`} />
          <Metric label="Weak URL Quality" value={formatCount(summary?.weak_url_quality_count)} sub="Provenance warning" />
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
        <FilterInput label="Reviewed By" value={filters.reviewed_by} onChange={(value) => updateFilter("reviewed_by", value)} />
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
        <label style={{ display: "grid", gap: 4, minWidth: 150 }}>
          <span style={labelStyle}>Review Status</span>
          <select value={filters.review_status} onChange={(event) => updateFilter("review_status", event.target.value)} style={{ ...inputStyle, cursor: "pointer" }}>
            <option value="">All reviews</option>
            {REVIEW_STATUSES.map((status) => (
              <option key={status} value={status}>{reviewStatusLabel(status)}</option>
            ))}
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
        <label style={{ alignItems: "center", color: "#cbd5e1", display: "flex", fontSize: 12, gap: 8, paddingTop: 17 }}>
          <input
            checked={filters.has_review_notes}
            onChange={(event) => updateFilter("has_review_notes", event.target.checked)}
            type="checkbox"
          />
          Has notes
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

        {!loading && saveError && (
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
            {saveError}
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
            <table style={{ borderCollapse: "collapse", minWidth: 1360, tableLayout: "fixed", width: "100%" }}>
              <colgroup>
                <col style={{ width: 34 }} />
                <col style={{ width: 300 }} />
                <col style={{ width: 150 }} />
                <col style={{ width: 120 }} />
                <col style={{ width: 140 }} />
                <col style={{ width: 95 }} />
                <col style={{ width: 150 }} />
                <col style={{ width: 120 }} />
                <col style={{ width: 260 }} />
                <col style={{ width: 150 }} />
                <col style={{ width: 105 }} />
              </colgroup>
              <thead>
                <tr style={{ borderBottom: "2px solid rgba(255,255,255,0.1)" }}>
                  {["", "Source", "Type", "Geography", "Publisher", "Status", "URL Quality", "Review", "Triage", "Run ID", "Created"].map((label) => (
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
                {sources.map((source) => (
                  <SourceRow
                    key={source.id}
                    source={source}
                    onSaved={updateSavedSource}
                    onError={(message) => setSaveError(message || null)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
