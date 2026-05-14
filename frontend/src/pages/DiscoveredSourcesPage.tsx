import { useEffect, useState, useMemo } from "react";
import type { DiscoveredSource, DiscoverDecisions } from "../api/types";
import { getDiscoveredSources, getDiscoverDecisions } from "../api/adapter";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Status = "pending" | "approved" | "rejected";
type StatusFilter = "all" | "pending" | "approved" | "rejected";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function sourceTypeLabel(t: string): string {
  const map: Record<string, string> = {
    developer_statement: "Developer Statement",
    official_filing:     "Official Filing",
    utility_statement:   "Utility Statement",
    regulatory_record:   "Regulatory Record",
    county_record:       "County Record",
    press:               "Press",
    url_seed:            "URL Seed",
  };
  return map[t] ?? t;
}

function statusFromDecisions(
  id: string,
  decisions: DiscoverDecisions | null
): Status {
  if (!decisions) return "pending";
  if (decisions.approved.includes(id)) return "approved";
  if (decisions.rejected.includes(id)) return "rejected";
  return "pending";
}

// ---------------------------------------------------------------------------
// Badge components
// ---------------------------------------------------------------------------

function ConfBadge({ value }: { value: string }) {
  const cfg: Record<string, { color: string; bg: string }> = {
    high:   { color: "#22c55e", bg: "rgba(34,197,94,0.15)" },
    medium: { color: "#f59e0b", bg: "rgba(245,158,11,0.15)" },
    low:    { color: "#ef4444", bg: "rgba(239,68,68,0.15)" },
  };
  const c = cfg[value] ?? { color: "#94a3b8", bg: "rgba(148,163,184,0.12)" };
  return (
    <span style={{
      fontSize: 11, fontWeight: 700, textTransform: "uppercase" as const,
      letterSpacing: "0.06em", padding: "3px 8px", borderRadius: 3,
      color: c.color, background: c.bg, border: `1px solid ${c.color}44`,
      whiteSpace: "nowrap" as const, display: "inline-block",
    }}>
      {value || "—"}
    </span>
  );
}

function StatusBadge({ status }: { status: Status }) {
  const cfg = {
    pending:  { label: "Pending",  color: "#cbd5e1", bg: "rgba(148,163,184,0.14)" },
    approved: { label: "Approved", color: "#22c55e", bg: "rgba(34,197,94,0.15)" },
    rejected: { label: "Rejected", color: "#ef4444", bg: "rgba(239,68,68,0.15)" },
  }[status];
  return (
    <span style={{
      fontSize: 11, fontWeight: 700, textTransform: "uppercase" as const,
      letterSpacing: "0.06em", padding: "3px 8px", borderRadius: 3,
      color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.color}44`,
      whiteSpace: "nowrap" as const, display: "inline-block",
    }}>
      {cfg.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Action buttons — larger, always visible
// ---------------------------------------------------------------------------

const actionBtnBase: React.CSSProperties = {
  display: "block",
  width: "100%",
  fontSize: 11,
  fontWeight: 600,
  padding: "5px 10px",
  borderRadius: 4,
  cursor: "pointer",
  whiteSpace: "nowrap" as const,
  textAlign: "left" as const,
  transition: "background 0.12s",
  lineHeight: 1.4,
};

function OpenSourceButton({ url }: { url: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      style={{
        ...actionBtnBase,
        background: "rgba(99,179,237,0.1)",
        border: "1px solid rgba(99,179,237,0.35)",
        color: "#7ec8e3",
        textDecoration: "none",
      }}
    >
      ↗ Open source
    </a>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  function handleCopy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    });
  }
  return (
    <button
      onClick={handleCopy}
      style={{
        ...actionBtnBase,
        background: copied ? "rgba(34,197,94,0.12)" : "rgba(255,255,255,0.04)",
        border: `1px solid ${copied ? "rgba(34,197,94,0.4)" : "rgba(255,255,255,0.12)"}`,
        color: copied ? "#22c55e" : "#cbd5e1",
      }}
    >
      {copied ? "✓ Copied" : "⎘ Copy URL"}
    </button>
  );
}

function DetailsToggleButton({ expanded, onClick }: { expanded: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        ...actionBtnBase,
        background: expanded ? "rgba(255,255,255,0.07)" : "rgba(255,255,255,0.03)",
        border: `1px solid ${expanded ? "rgba(255,255,255,0.2)" : "rgba(255,255,255,0.1)"}`,
        color: expanded ? "#e2e8f0" : "#94a3b8",
      }}
    >
      {expanded ? "▲ Hide details" : "▼ Details"}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Expandable details panel
// ---------------------------------------------------------------------------

const DETAIL_FIELDS: [string, (s: DiscoveredSource) => string][] = [
  ["Discovery ID",       s => s.discovery_id],
  ["Candidate name",     s => s.candidate_project_name || "—"],
  ["Developer",          s => s.developer || "—"],
  ["State",              s => s.state || "—"],
  ["County",             s => s.county || "—"],
  ["Source type",        s => sourceTypeLabel(s.source_type)],
  ["Source date",        s => s.source_date || "—"],
  ["Discovery method",   s => s.discovery_method || "—"],
  ["Detected region",    s => s.detected_region || "—"],
  ["Detected utility",   s => s.detected_utility || "—"],
  ["Detected load (MW)", s => s.detected_load_mw != null ? String(s.detected_load_mw) : "—"],
  ["Confidence",         s => s.confidence || "—"],
  ["Retrieved at",       s => s.retrieved_at || "—"],
  ["Review reason",      s => s.requires_review_reason || "—"],
];

function DetailsPanel({ source }: { source: DiscoveredSource }) {
  return (
    <div style={{
      padding: "16px 20px",
      background: "rgba(0,0,0,0.28)",
      borderTop: "1px solid rgba(255,255,255,0.07)",
    }}>
      <div style={{
        fontSize: 10, fontWeight: 700, textTransform: "uppercase" as const,
        letterSpacing: "0.1em", color: "#94a3b8", marginBottom: 12,
      }}>
        Source details
      </div>

      {/* Key-value grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        gap: "8px 24px",
        marginBottom: source.extracted_text ? 16 : 0,
      }}>
        {DETAIL_FIELDS.map(([label, getter]) => (
          <div key={label} style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
            <span style={{
              fontSize: 10, fontWeight: 600, textTransform: "uppercase" as const,
              letterSpacing: "0.06em", color: "#64748b",
              minWidth: 130, flexShrink: 0,
            }}>
              {label}
            </span>
            <span style={{
              fontSize: 12, color: "#cbd5e1",
              wordBreak: "break-word",
              lineHeight: 1.4,
            }}>
              {getter(source)}
            </span>
          </div>
        ))}
      </div>

      {/* Source URL */}
      {source.source_url && (
        <div style={{ display: "flex", gap: 10, alignItems: "baseline", marginBottom: 14 }}>
          <span style={{
            fontSize: 10, fontWeight: 600, textTransform: "uppercase" as const,
            letterSpacing: "0.06em", color: "#64748b",
            minWidth: 130, flexShrink: 0,
          }}>
            Source URL
          </span>
          <a
            href={source.source_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontSize: 12, color: "#7ec8e3",
              wordBreak: "break-all", lineHeight: 1.4,
            }}
          >
            {source.source_url}
          </a>
        </div>
      )}

      {/* Extracted text */}
      {source.extracted_text && (
        <div>
          <div style={{
            fontSize: 10, fontWeight: 700, textTransform: "uppercase" as const,
            letterSpacing: "0.1em", color: "#94a3b8", marginBottom: 8,
          }}>
            Extracted text
          </div>
          <pre style={{
            margin: 0,
            fontFamily: "ui-monospace, 'Cascadia Code', 'Source Code Pro', monospace",
            fontSize: 11,
            lineHeight: 1.65,
            whiteSpace: "pre-wrap" as const,
            wordBreak: "break-word" as const,
            color: "#cbd5e1",
            background: "rgba(0,0,0,0.35)",
            border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: 4,
            padding: "12px 14px",
            maxHeight: 200,
            overflowY: "auto",
          }}>
            {source.extracted_text}
          </pre>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <div style={{
      textAlign: "center",
      padding: "56px 24px 64px",
    }}>
      <div style={{ fontSize: 38, marginBottom: 14, opacity: 0.35 }}>⊡</div>
      <div style={{ fontSize: 15, fontWeight: 700, color: "#e2e8f0", marginBottom: 6 }}>
        No discovered sources found
      </div>
      <div style={{ fontSize: 13, color: "#94a3b8", lineHeight: 1.7, maxWidth: 480, margin: "0 auto 20px" }}>
        The discovery CSV is missing or empty. Run the following commands from the
        <code style={{ fontSize: 12, background: "rgba(255,255,255,0.07)", padding: "1px 5px", borderRadius: 3, color: "#cbd5e1" }}>backend/</code> directory:
      </div>
      <ol style={{
        textAlign: "left", fontSize: 13, lineHeight: 2.1,
        maxWidth: 460, margin: "0 auto",
        color: "#94a3b8",
        paddingLeft: 22,
      }}>
        <li>
          Run public discovery:
          <div style={{ marginTop: 4, marginBottom: 4 }}>
            <code style={{
              fontSize: 12, background: "rgba(255,255,255,0.07)",
              padding: "4px 10px", borderRadius: 4, color: "#e2e8f0",
              display: "inline-block",
            }}>
              python scripts/discover_starter_dataset.py
            </code>
          </div>
        </li>
        <li>
          Ingest the discovered sources:
          <div style={{ marginTop: 4, marginBottom: 4 }}>
            <code style={{
              fontSize: 12, background: "rgba(255,255,255,0.07)",
              padding: "4px 10px", borderRadius: 4, color: "#e2e8f0",
              display: "inline-block",
            }}>
              python scripts/ingest_discovered_sources.py
            </code>
          </div>
        </li>
        <li>Refresh this page.</li>
      </ol>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Filter / input styles
// ---------------------------------------------------------------------------

const inputStyle: React.CSSProperties = {
  background: "rgba(255,255,255,0.06)",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 4,
  padding: "6px 10px",
  fontSize: 12,
  color: "#e2e8f0",
  outline: "none",
};

const selectStyle: React.CSSProperties = {
  ...inputStyle,
  cursor: "pointer",
  minWidth: 140,
};

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function DiscoveredSourcesPage() {
  const [sources, setSources]     = useState<DiscoveredSource[]>([]);
  const [decisions, setDecisions] = useState<DiscoverDecisions | null>(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);

  const [statusFilter,    setStatusFilter]    = useState<StatusFilter>("all");
  const [typeFilter,      setTypeFilter]      = useState<string>("all");
  const [publisherFilter, setPublisherFilter] = useState<string>("all");
  const [search,          setSearch]          = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [srcs, dec] = await Promise.all([
          getDiscoveredSources(),
          getDiscoverDecisions().catch(() => null),
        ]);
        if (!cancelled) {
          setSources(srcs);
          setDecisions(dec);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const typeOptions = useMemo(() => {
    return [...new Set(sources.map(s => s.source_type).filter(Boolean))].sort();
  }, [sources]);

  const publisherOptions = useMemo(() => {
    return [...new Set(sources.map(s => s.developer).filter(Boolean))].sort();
  }, [sources]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    return sources.filter(s => {
      const status = statusFromDecisions(s.discovery_id, decisions);
      if (statusFilter !== "all" && status !== statusFilter) return false;
      if (typeFilter !== "all" && s.source_type !== typeFilter) return false;
      if (publisherFilter !== "all" && s.developer !== publisherFilter) return false;
      if (q) {
        const hay = [s.title, s.candidate_project_name, s.developer, s.source_url, s.state, s.county]
          .join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [sources, decisions, statusFilter, typeFilter, publisherFilter, search]);

  const counts = useMemo(() => {
    let pending = 0, approved = 0, rejected = 0;
    for (const s of sources) {
      const st = statusFromDecisions(s.discovery_id, decisions);
      if (st === "approved") approved++;
      else if (st === "rejected") rejected++;
      else pending++;
    }
    return { pending, approved, rejected, total: sources.length };
  }, [sources, decisions]);

  const filtersActive = search !== "" || statusFilter !== "all" || typeFilter !== "all" || publisherFilter !== "all";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>

      {/* ── Header ── */}
      <div style={{
        padding: "14px 20px 12px",
        borderBottom: "1px solid var(--border)",
        flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
          <h1 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#f1f5f9" }}>
            Discovered Sources
          </h1>
          {!loading && !error && (
            <span style={{ fontSize: 13, color: "#94a3b8" }}>
              {filtered.length} of {counts.total} sources
            </span>
          )}
        </div>

        {/* Notice banners */}
        <div style={{ display: "flex", gap: 8, marginTop: 9, flexWrap: "wrap" }}>
          <span style={{
            fontSize: 11, fontWeight: 600, letterSpacing: "0.05em",
            padding: "4px 10px", borderRadius: 3,
            background: "rgba(245,158,11,0.12)", color: "#fbbf24",
            border: "1px solid rgba(245,158,11,0.3)",
          }}>
            Source candidates only — not yet projects
          </span>
          <span style={{
            fontSize: 11, fontWeight: 600, letterSpacing: "0.05em",
            padding: "4px 10px", borderRadius: 3,
            background: "rgba(255,255,255,0.05)", color: "#94a3b8",
            border: "1px solid rgba(255,255,255,0.1)",
          }}>
            No public source, no project record
          </span>
        </div>

        {/* Count pills */}
        {!loading && !error && counts.total > 0 && (
          <div style={{ display: "flex", gap: 24, marginTop: 12 }}>
            {[
              { label: "Total",    value: counts.total,    color: "#e2e8f0" },
              { label: "Pending",  value: counts.pending,  color: "#94a3b8" },
              { label: "Approved", value: counts.approved, color: "#22c55e" },
              { label: "Rejected", value: counts.rejected, color: "#f87171" },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ textAlign: "center" }}>
                <div style={{ fontSize: 17, fontWeight: 700, color, lineHeight: 1 }}>{value}</div>
                <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.07em", marginTop: 3 }}>
                  {label}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Filter bar ── */}
      <div style={{
        padding: "10px 20px",
        borderBottom: "1px solid var(--border)",
        display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center",
        flexShrink: 0,
        background: "rgba(0,0,0,0.12)",
      }}>
        <input
          type="text"
          placeholder="Search title, project, URL…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ ...inputStyle, minWidth: 220, flex: "1 1 220px" }}
        />

        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value as StatusFilter)}
          style={selectStyle}
        >
          <option value="all">All statuses</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>

        <select
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
          style={selectStyle}
        >
          <option value="all">All source types</option>
          {typeOptions.map(t => (
            <option key={t} value={t}>{sourceTypeLabel(t)}</option>
          ))}
        </select>

        <select
          value={publisherFilter}
          onChange={e => setPublisherFilter(e.target.value)}
          style={{ ...selectStyle, maxWidth: 210 }}
        >
          <option value="all">All publishers</option>
          {publisherOptions.map(p => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>

        {filtersActive && (
          <button
            onClick={() => { setSearch(""); setStatusFilter("all"); setTypeFilter("all"); setPublisherFilter("all"); }}
            style={{
              fontSize: 12, fontWeight: 600, padding: "6px 12px", borderRadius: 4,
              background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)",
              color: "#f87171", cursor: "pointer",
            }}
          >
            ✕ Clear filters
          </button>
        )}
      </div>

      {/* ── Body ── */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0 20px 24px" }}>

        {loading && (
          <div style={{ padding: "48px 0", textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
            Loading discovered sources…
          </div>
        )}

        {!loading && error && (
          <div style={{
            margin: "20px 0", padding: "16px 18px",
            background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)",
            borderRadius: 6, lineHeight: 1.7,
          }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#f87171", marginBottom: 6 }}>
              Failed to load discovered sources
            </div>
            <div style={{ fontSize: 12, color: "#fca5a5", marginBottom: 8 }}>
              {error}
            </div>
            <div style={{ fontSize: 12, color: "#94a3b8" }}>
              Make sure the backend is running and the CSV exists at{" "}
              <code style={{
                fontSize: 11, background: "rgba(255,255,255,0.07)",
                padding: "2px 6px", borderRadius: 3, color: "#cbd5e1",
              }}>
                backend/runtime_data/starter_sources/discovered_sources_v0_1.csv
              </code>.
              Run{" "}
              <code style={{
                fontSize: 11, background: "rgba(255,255,255,0.07)",
                padding: "2px 6px", borderRadius: 3, color: "#cbd5e1",
              }}>
                python scripts/discover_starter_dataset.py
              </code>{" "}
              to generate it.
            </div>
          </div>
        )}

        {!loading && !error && filtered.length === 0 && sources.length === 0 && (
          <EmptyState />
        )}

        {!loading && !error && filtered.length === 0 && sources.length > 0 && (
          <div style={{ padding: "48px 0", textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
            No sources match the current filters.{" "}
            <button
              onClick={() => { setSearch(""); setStatusFilter("all"); setTypeFilter("all"); setPublisherFilter("all"); }}
              style={{
                fontSize: 13, fontWeight: 600, background: "none", border: "none",
                color: "#7ec8e3", cursor: "pointer", padding: 0, textDecoration: "underline",
              }}
            >
              Clear filters
            </button>
          </div>
        )}

        {!loading && !error && filtered.length > 0 && (
          <div style={{ overflowX: "auto", marginTop: 12 }}>
            <table style={{
              width: "100%", borderCollapse: "collapse",
              fontSize: 12, minWidth: 860,
            }}>
              <thead>
                <tr style={{ borderBottom: "2px solid rgba(255,255,255,0.1)" }}>
                  {[
                    { label: "Title / Project", width: "auto" },
                    { label: "Publisher",        width: 140 },
                    { label: "Type",             width: 140 },
                    { label: "Geography",        width: 150 },
                    { label: "Method",           width: 110 },
                    { label: "Confidence",       width: 100 },
                    { label: "Status",           width: 90 },
                    { label: "Discovered",       width: 100 },
                    { label: "Actions",          width: 130 },
                  ].map(({ label, width }) => (
                    <th key={label} style={{
                      padding: "9px 12px", textAlign: "left",
                      fontSize: 10, fontWeight: 700, textTransform: "uppercase" as const,
                      letterSpacing: "0.08em", color: "#94a3b8",
                      whiteSpace: "nowrap" as const,
                      width: width === "auto" ? undefined : width,
                      position: "sticky" as const, top: 0,
                      background: "var(--bg)", zIndex: 1,
                      borderBottom: "1px solid rgba(255,255,255,0.08)",
                    }}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(source => {
                  const status = statusFromDecisions(source.discovery_id, decisions);
                  return (
                    <SourceRow
                      key={source.discovery_id}
                      source={source}
                      status={status}
                    />
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Table row
// ---------------------------------------------------------------------------

function SourceRow({
  source,
  status,
}: {
  source: DiscoveredSource;
  status: Status;
}) {
  const [expanded, setExpanded] = useState(false);

  const rowBorder = expanded
    ? "1px solid rgba(99,179,237,0.2)"
    : "1px solid rgba(255,255,255,0.06)";

  return (
    <>
      <tr style={{
        borderBottom: rowBorder,
        background: expanded ? "rgba(99,179,237,0.03)" : "transparent",
        verticalAlign: "top",
        transition: "background 0.12s",
      }}>

        {/* Title / Project */}
        <td style={{ padding: "12px 12px", maxWidth: 320 }}>
          <div style={{
            fontWeight: 600, color: "#e2e8f0",
            marginBottom: 3, lineHeight: 1.35,
            wordBreak: "break-word",
          }}>
            {source.title
              ? source.title.length > 90
                ? source.title.slice(0, 90) + "…"
                : source.title
              : <span style={{ color: "#64748b", fontStyle: "italic", fontWeight: 400 }}>Untitled</span>
            }
          </div>
          {source.candidate_project_name && (
            <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 2 }}>
              {source.candidate_project_name}
            </div>
          )}
          {source.source_url && (
            <div style={{ fontSize: 11, color: "#64748b" }}>
              {hostname(source.source_url)}
            </div>
          )}
        </td>

        {/* Publisher */}
        <td style={{ padding: "12px 12px" }}>
          <span style={{ color: "#cbd5e1", fontSize: 12 }}>
            {source.developer || <span style={{ color: "#64748b" }}>—</span>}
          </span>
        </td>

        {/* Type */}
        <td style={{ padding: "12px 12px", color: "#cbd5e1", whiteSpace: "nowrap" as const }}>
          {sourceTypeLabel(source.source_type)}
        </td>

        {/* Geography */}
        <td style={{ padding: "12px 12px", color: "#cbd5e1", whiteSpace: "nowrap" as const }}>
          {[source.county, source.state].filter(Boolean).join(", ") || (
            <span style={{ color: "#64748b" }}>—</span>
          )}
        </td>

        {/* Method */}
        <td style={{ padding: "12px 12px", color: "#94a3b8", fontSize: 12, whiteSpace: "nowrap" as const }}>
          {source.discovery_method || <span style={{ color: "#64748b" }}>—</span>}
        </td>

        {/* Confidence */}
        <td style={{ padding: "12px 12px" }}>
          <ConfBadge value={source.confidence} />
        </td>

        {/* Status */}
        <td style={{ padding: "12px 12px" }}>
          <StatusBadge status={status} />
        </td>

        {/* Discovered */}
        <td style={{ padding: "12px 12px", color: "#94a3b8", fontSize: 12, whiteSpace: "nowrap" as const }}>
          {formatDate(source.retrieved_at)}
        </td>

        {/* Actions — always visible, stacked */}
        <td style={{ padding: "10px 12px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 5, minWidth: 118 }}>
            {source.source_url && <OpenSourceButton url={source.source_url} />}
            {source.source_url && <CopyButton text={source.source_url} />}
            <DetailsToggleButton expanded={expanded} onClick={() => setExpanded(e => !e)} />
          </div>
        </td>

      </tr>

      {/* Expandable details row */}
      {expanded && (
        <tr style={{ borderBottom: "1px solid rgba(99,179,237,0.2)" }}>
          <td colSpan={9} style={{ padding: 0 }}>
            <DetailsPanel source={source} />
          </td>
        </tr>
      )}
    </>
  );
}
