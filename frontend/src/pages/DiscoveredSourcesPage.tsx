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
    official_filing: "Official Filing",
    utility_statement: "Utility Statement",
    regulatory_record: "Regulatory Record",
    county_record: "County Record",
    press: "Press",
    url_seed: "URL Seed",
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
// Small badge components
// ---------------------------------------------------------------------------

function ConfBadge({ value }: { value: string }) {
  const cfg: Record<string, { color: string; bg: string }> = {
    high:   { color: "#22c55e", bg: "rgba(34,197,94,0.12)" },
    medium: { color: "#f59e0b", bg: "rgba(245,158,11,0.12)" },
    low:    { color: "#ef4444", bg: "rgba(239,68,68,0.12)" },
  };
  const c = cfg[value] ?? { color: "#94a3b8", bg: "rgba(148,163,184,0.1)" };
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, textTransform: "uppercase" as const,
      letterSpacing: "0.07em", padding: "2px 7px", borderRadius: 3,
      color: c.color, background: c.bg, border: `1px solid ${c.color}33`,
      whiteSpace: "nowrap" as const,
    }}>
      {value || "—"}
    </span>
  );
}

function StatusBadge({ status }: { status: Status }) {
  const cfg = {
    pending:  { label: "Pending",  color: "#94a3b8", bg: "rgba(148,163,184,0.1)" },
    approved: { label: "Approved", color: "#22c55e", bg: "rgba(34,197,94,0.12)" },
    rejected: { label: "Rejected", color: "#ef4444", bg: "rgba(239,68,68,0.12)" },
  }[status];
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, textTransform: "uppercase" as const,
      letterSpacing: "0.07em", padding: "2px 7px", borderRadius: 3,
      color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.color}33`,
      whiteSpace: "nowrap" as const,
    }}>
      {cfg.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Copy button
// ---------------------------------------------------------------------------

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  function handleCopy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }
  return (
    <button
      onClick={handleCopy}
      title="Copy URL"
      style={{
        fontSize: 10, padding: "2px 7px", borderRadius: 3,
        background: copied ? "rgba(34,197,94,0.15)" : "rgba(255,255,255,0.05)",
        border: `1px solid ${copied ? "rgba(34,197,94,0.4)" : "var(--border)"}`,
        color: copied ? "#22c55e" : "var(--text-dim)",
        cursor: "pointer", whiteSpace: "nowrap" as const,
        transition: "all 0.15s",
      }}
    >
      {copied ? "✓ Copied" : "Copy URL"}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Expandable metadata section
// ---------------------------------------------------------------------------

function MetaExpander({ source }: { source: DiscoveredSource }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginTop: 6 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          fontSize: 10, padding: "2px 7px", borderRadius: 3,
          background: "transparent",
          border: "1px solid var(--border)",
          color: "var(--text-dim)", cursor: "pointer",
          whiteSpace: "nowrap" as const,
        }}
      >
        {open ? "▲ Hide metadata" : "▼ Raw metadata"}
      </button>
      {open && (
        <div style={{
          marginTop: 8,
          padding: "10px 12px",
          background: "rgba(0,0,0,0.25)",
          border: "1px solid var(--border)",
          borderRadius: 4,
          fontSize: 11,
          color: "var(--text-muted)",
          lineHeight: 1.6,
          maxHeight: 260,
          overflowY: "auto",
        }}>
          {[
            ["Discovery ID",       source.discovery_id],
            ["Candidate name",     source.candidate_project_name],
            ["Developer",          source.developer],
            ["State",              source.state],
            ["County",             source.county],
            ["Source type",        source.source_type],
            ["Source date",        source.source_date],
            ["Discovery method",   source.discovery_method],
            ["Detected region",    source.detected_region],
            ["Detected utility",   source.detected_utility],
            ["Detected load (MW)", source.detected_load_mw != null ? String(source.detected_load_mw) : "—"],
            ["Confidence",         source.confidence],
            ["Retrieved at",       source.retrieved_at],
            ["Review reason",      source.requires_review_reason || "—"],
          ].map(([label, val]) => (
            <div key={label} style={{ display: "flex", gap: 8, marginBottom: 3 }}>
              <span style={{ color: "var(--text-dim)", minWidth: 140, flexShrink: 0 }}>{label}</span>
              <span style={{ wordBreak: "break-all" }}>{val}</span>
            </div>
          ))}
          {source.extracted_text && (
            <div style={{ marginTop: 8, borderTop: "1px solid var(--border)", paddingTop: 8 }}>
              <div style={{ color: "var(--text-dim)", marginBottom: 4 }}>Extracted text</div>
              <div style={{
                fontFamily: "monospace", fontSize: 10,
                whiteSpace: "pre-wrap", wordBreak: "break-word",
                color: "var(--text-muted)", maxHeight: 120, overflowY: "auto",
              }}>
                {source.extracted_text}
              </div>
            </div>
          )}
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
      padding: "60px 24px",
      color: "var(--text-dim)",
    }}>
      <div style={{ fontSize: 36, marginBottom: 16, opacity: 0.4 }}>⊡</div>
      <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-muted)", marginBottom: 8 }}>
        No discovered sources found
      </div>
      <div style={{ fontSize: 13, lineHeight: 1.7, maxWidth: 460, margin: "0 auto" }}>
        To generate and ingest discovered sources:
      </div>
      <ol style={{
        textAlign: "left", fontSize: 13, lineHeight: 1.9,
        maxWidth: 440, margin: "16px auto 0",
        color: "var(--text-muted)",
        paddingLeft: 20,
      }}>
        <li>Run public discovery:<br />
          <code style={{ fontSize: 11, background: "rgba(255,255,255,0.06)", padding: "2px 6px", borderRadius: 3 }}>
            python scripts/discover_starter_dataset.py
          </code>
        </li>
        <li style={{ marginTop: 8 }}>Ingest the discovered source JSON:<br />
          <code style={{ fontSize: 11, background: "rgba(255,255,255,0.06)", padding: "2px 6px", borderRadius: 3 }}>
            python scripts/ingest_discovered_sources.py
          </code>
        </li>
        <li style={{ marginTop: 8 }}>Refresh this page.</li>
      </ol>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Filter bar
// ---------------------------------------------------------------------------

const inputStyle: React.CSSProperties = {
  background: "var(--bg-surface)",
  border: "1px solid var(--border)",
  borderRadius: 4,
  padding: "5px 10px",
  fontSize: 12,
  color: "var(--text)",
  outline: "none",
};

const selectStyle: React.CSSProperties = {
  ...inputStyle,
  cursor: "pointer",
  minWidth: 130,
};

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function DiscoveredSourcesPage() {
  const [sources, setSources]     = useState<DiscoveredSource[]>([]);
  const [decisions, setDecisions] = useState<DiscoverDecisions | null>(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);

  // filters
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

  // derive unique option lists
  const typeOptions = useMemo(() => {
    const vals = [...new Set(sources.map(s => s.source_type).filter(Boolean))].sort();
    return vals;
  }, [sources]);

  const publisherOptions = useMemo(() => {
    const vals = [...new Set(sources.map(s => s.developer).filter(Boolean))].sort();
    return vals;
  }, [sources]);

  // filtered rows
  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    return sources.filter(s => {
      const status = statusFromDecisions(s.discovery_id, decisions);
      if (statusFilter !== "all" && status !== statusFilter) return false;
      if (typeFilter !== "all" && s.source_type !== typeFilter) return false;
      if (publisherFilter !== "all" && s.developer !== publisherFilter) return false;
      if (q) {
        const hay = [s.title, s.candidate_project_name, s.developer, s.source_url, s.state, s.county].join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [sources, decisions, statusFilter, typeFilter, publisherFilter, search]);

  // counts
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

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>

      {/* ── Header ── */}
      <div style={{
        padding: "14px 20px 12px",
        borderBottom: "1px solid var(--border)",
        flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
          <h1 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "var(--text)" }}>
            Discovered Sources
          </h1>
          {!loading && !error && (
            <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
              {filtered.length} of {counts.total} sources
            </span>
          )}
        </div>

        {/* Notice banners */}
        <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <span style={{
            fontSize: 10, fontWeight: 600, letterSpacing: "0.06em",
            padding: "3px 8px", borderRadius: 3,
            background: "rgba(245,158,11,0.1)", color: "#f59e0b",
            border: "1px solid rgba(245,158,11,0.25)",
          }}>
            Source candidates only — not yet projects
          </span>
          <span style={{
            fontSize: 10, fontWeight: 600, letterSpacing: "0.06em",
            padding: "3px 8px", borderRadius: 3,
            background: "rgba(148,163,184,0.08)", color: "var(--text-dim)",
            border: "1px solid var(--border)",
          }}>
            No public source, no project record
          </span>
        </div>

        {/* Summary counts */}
        {!loading && !error && counts.total > 0 && (
          <div style={{ display: "flex", gap: 20, marginTop: 10 }}>
            {[
              { label: "Total",    value: counts.total,    color: "var(--text-muted)" },
              { label: "Pending",  value: counts.pending,  color: "#94a3b8" },
              { label: "Approved", value: counts.approved, color: "#22c55e" },
              { label: "Rejected", value: counts.rejected, color: "#ef4444" },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ textAlign: "center" }}>
                <div style={{ fontSize: 15, fontWeight: 700, color, lineHeight: 1 }}>{value}</div>
                <div style={{ fontSize: 9, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em", marginTop: 2 }}>
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
        background: "rgba(0,0,0,0.1)",
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
          <option value="all">All types</option>
          {typeOptions.map(t => (
            <option key={t} value={t}>{sourceTypeLabel(t)}</option>
          ))}
        </select>

        <select
          value={publisherFilter}
          onChange={e => setPublisherFilter(e.target.value)}
          style={{ ...selectStyle, maxWidth: 200 }}
        >
          <option value="all">All publishers</option>
          {publisherOptions.map(p => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>

        {(search || statusFilter !== "all" || typeFilter !== "all" || publisherFilter !== "all") && (
          <button
            onClick={() => { setSearch(""); setStatusFilter("all"); setTypeFilter("all"); setPublisherFilter("all"); }}
            style={{
              fontSize: 11, padding: "5px 10px", borderRadius: 4,
              background: "transparent", border: "1px solid var(--border)",
              color: "var(--text-dim)", cursor: "pointer",
            }}
          >
            Clear filters
          </button>
        )}
      </div>

      {/* ── Body ── */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0 20px 20px" }}>

        {loading && (
          <div style={{ padding: "40px 0", textAlign: "center", color: "var(--text-dim)", fontSize: 13 }}>
            Loading discovered sources…
          </div>
        )}

        {!loading && error && (
          <div style={{
            margin: "20px 0", padding: "14px 16px",
            background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)",
            borderRadius: 6, fontSize: 12, color: "#ef4444", lineHeight: 1.6,
          }}>
            <strong>Failed to load discovered sources</strong><br />
            {error}<br />
            <span style={{ color: "var(--text-dim)" }}>
              Make sure the backend is running and the CSV exists at
              <code style={{ marginLeft: 4 }}>backend/runtime_data/starter_sources/discovered_sources_v0_1.csv</code>.
            </span>
          </div>
        )}

        {!loading && !error && filtered.length === 0 && sources.length === 0 && (
          <EmptyState />
        )}

        {!loading && !error && filtered.length === 0 && sources.length > 0 && (
          <div style={{ padding: "40px 0", textAlign: "center", color: "var(--text-dim)", fontSize: 13 }}>
            No sources match the current filters.
          </div>
        )}

        {!loading && !error && filtered.length > 0 && (
          <table style={{
            width: "100%", borderCollapse: "collapse",
            fontSize: 12, marginTop: 12,
          }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                {["Title / Project", "Publisher", "Type", "Geography", "Method", "Confidence", "Status", "Discovered", "Actions"].map(h => (
                  <th key={h} style={{
                    padding: "8px 10px", textAlign: "left",
                    fontSize: 10, fontWeight: 700, textTransform: "uppercase" as const,
                    letterSpacing: "0.07em", color: "var(--text-dim)",
                    whiteSpace: "nowrap" as const,
                    position: "sticky" as const, top: 0,
                    background: "var(--bg)", zIndex: 1,
                  }}>
                    {h}
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
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Table row (extracted to keep row expansion state local)
// ---------------------------------------------------------------------------

function SourceRow({
  source,
  status,
}: {
  source: DiscoveredSource;
  status: Status;
}) {
  const [expanded, setExpanded] = useState(false);
  const rowBg = expanded ? "rgba(255,255,255,0.02)" : "transparent";

  return (
    <>
      <tr
        style={{
          borderBottom: "1px solid var(--border)",
          background: rowBg,
          verticalAlign: "top",
          transition: "background 0.1s",
        }}
      >
        {/* Title / Project */}
        <td style={{ padding: "10px 10px" }}>
          <div style={{ fontWeight: 600, color: "var(--text)", marginBottom: 2, lineHeight: 1.3 }}>
            {source.title
              ? source.title.length > 80
                ? source.title.slice(0, 80) + "…"
                : source.title
              : <span style={{ color: "var(--text-dim)", fontStyle: "italic", fontWeight: 400 }}>Untitled</span>
            }
          </div>
          {source.candidate_project_name && (
            <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
              {source.candidate_project_name}
            </div>
          )}
          {source.source_url && (
            <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 2 }}>
              {hostname(source.source_url)}
            </div>
          )}
        </td>

        {/* Publisher */}
        <td style={{ padding: "10px 10px", color: "var(--text-muted)", whiteSpace: "nowrap" as const }}>
          {source.developer || <span style={{ color: "var(--text-dim)" }}>—</span>}
        </td>

        {/* Type */}
        <td style={{ padding: "10px 10px", whiteSpace: "nowrap" as const, color: "var(--text-muted)" }}>
          {sourceTypeLabel(source.source_type)}
        </td>

        {/* Geography */}
        <td style={{ padding: "10px 10px", whiteSpace: "nowrap" as const, color: "var(--text-muted)" }}>
          {[source.county, source.state].filter(Boolean).join(", ") || "—"}
        </td>

        {/* Method */}
        <td style={{ padding: "10px 10px", whiteSpace: "nowrap" as const, color: "var(--text-dim)", fontSize: 11 }}>
          {source.discovery_method || "—"}
        </td>

        {/* Confidence */}
        <td style={{ padding: "10px 10px" }}>
          <ConfBadge value={source.confidence} />
        </td>

        {/* Status */}
        <td style={{ padding: "10px 10px" }}>
          <StatusBadge status={status} />
        </td>

        {/* Discovered at */}
        <td style={{ padding: "10px 10px", whiteSpace: "nowrap" as const, color: "var(--text-dim)", fontSize: 11 }}>
          {formatDate(source.retrieved_at)}
        </td>

        {/* Actions */}
        <td style={{ padding: "10px 10px" }}>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            {source.source_url && (
              <a
                href={source.source_url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  fontSize: 10, padding: "2px 7px", borderRadius: 3,
                  background: "rgba(99,179,237,0.08)",
                  border: "1px solid rgba(99,179,237,0.3)",
                  color: "var(--accent)", textDecoration: "none",
                  whiteSpace: "nowrap" as const,
                }}
              >
                ↗ Open
              </a>
            )}
            {source.source_url && <CopyButton text={source.source_url} />}
            <button
              onClick={() => setExpanded(e => !e)}
              style={{
                fontSize: 10, padding: "2px 7px", borderRadius: 3,
                background: expanded ? "rgba(255,255,255,0.06)" : "transparent",
                border: "1px solid var(--border)",
                color: "var(--text-dim)", cursor: "pointer",
                whiteSpace: "nowrap" as const,
              }}
            >
              {expanded ? "▲ Less" : "▼ Meta"}
            </button>
          </div>
        </td>
      </tr>

      {/* Expandable metadata row */}
      {expanded && (
        <tr style={{ borderBottom: "1px solid var(--border)", background: "rgba(0,0,0,0.18)" }}>
          <td colSpan={9} style={{ padding: "10px 16px 14px 16px" }}>
            <MetaExpander source={source} />
          </td>
        </tr>
      )}
    </>
  );
}
