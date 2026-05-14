import { useEffect, useState, useMemo, useCallback } from "react";
import type { DiscoveredSourceClaim } from "../api/types";
import { getDiscoveredSourceClaims } from "../api/adapter";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      year: "numeric", month: "short", day: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-US", {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function hostname(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch { return url; }
}

function claimValueToString(v: DiscoveredSourceClaim["claim_value"]): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function confDisplay(v: number | null): string {
  if (v === null || v === undefined) return "—";
  if (v <= 1) return `${Math.round(v * 100)}%`;
  return String(v);
}

function confColor(v: number | null): { color: string; bg: string } {
  if (v === null || v === undefined) return { color: "#94a3b8", bg: "rgba(148,163,184,0.12)" };
  if (v >= 0.7) return { color: "#22c55e", bg: "rgba(34,197,94,0.15)" };
  if (v >= 0.4) return { color: "#f59e0b", bg: "rgba(245,158,11,0.15)" };
  return { color: "#ef4444", bg: "rgba(239,68,68,0.15)" };
}

function claimTypeLabel(t: string): string {
  return t
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusColor(s: string): { color: string; bg: string } {
  const map: Record<string, { color: string; bg: string }> = {
    candidate: { color: "#94a3b8", bg: "rgba(148,163,184,0.1)" },
    accepted:  { color: "#22c55e", bg: "rgba(34,197,94,0.12)" },
    rejected:  { color: "#ef4444", bg: "rgba(239,68,68,0.1)" },
    promoted:  { color: "#818cf8", bg: "rgba(129,140,248,0.12)" },
  };
  return map[s] ?? { color: "#94a3b8", bg: "rgba(148,163,184,0.1)" };
}

// ---------------------------------------------------------------------------
// Small reusable components
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: string }) {
  const { color, bg } = statusColor(status);
  return (
    <span style={{
      fontSize: 11, fontWeight: 700, textTransform: "uppercase" as const,
      letterSpacing: "0.06em", padding: "3px 8px", borderRadius: 3,
      color, background: bg, border: `1px solid ${color}44`,
      whiteSpace: "nowrap" as const, display: "inline-block",
    }}>
      {status || "—"}
    </span>
  );
}

function ConfBadge({ value }: { value: number | null }) {
  const { color, bg } = confColor(value);
  return (
    <span style={{
      fontSize: 11, fontWeight: 700, padding: "3px 8px", borderRadius: 3,
      color, background: bg, border: `1px solid ${color}44`,
      whiteSpace: "nowrap" as const, display: "inline-block",
    }}>
      {confDisplay(value)}
    </span>
  );
}

function OpenSourceButton({ url }: { url: string }) {
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" style={{
      display: "block", padding: "5px 9px",
      fontSize: 11, fontWeight: 600, textDecoration: "none",
      background: "rgba(99,102,241,0.18)", color: "#a5b4fc",
      border: "1px solid rgba(99,102,241,0.35)",
      borderRadius: 4, textAlign: "center" as const,
      whiteSpace: "nowrap" as const,
    }}>
      ↗ Open source
    </a>
  );
}

function CopyButton({ text, label = "Copy URL" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const handleClick = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  }, [text]);
  return (
    <button onClick={handleClick} style={{
      display: "block", width: "100%", padding: "5px 9px",
      fontSize: 11, fontWeight: 600, cursor: "pointer",
      background: copied ? "rgba(34,197,94,0.15)" : "rgba(255,255,255,0.06)",
      color: copied ? "#22c55e" : "#94a3b8",
      border: copied ? "1px solid rgba(34,197,94,0.4)" : "1px solid rgba(255,255,255,0.12)",
      borderRadius: 4, textAlign: "center" as const,
      whiteSpace: "nowrap" as const,
    }}>
      {copied ? "✓ Copied" : `⎘ ${label}`}
    </button>
  );
}

function DetailsToggleButton({ expanded, onClick }: { expanded: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} style={{
      display: "block", width: "100%", padding: "5px 9px",
      fontSize: 11, fontWeight: 600, cursor: "pointer",
      background: expanded ? "rgba(248,250,252,0.1)" : "rgba(255,255,255,0.05)",
      color: expanded ? "#e2e8f0" : "#64748b",
      border: expanded ? "1px solid rgba(255,255,255,0.2)" : "1px solid rgba(255,255,255,0.08)",
      borderRadius: 4, textAlign: "center" as const,
      whiteSpace: "nowrap" as const,
    }}>
      {expanded ? "▲ Close" : "▼ Details"}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Details expansion panel
// ---------------------------------------------------------------------------

function DetailsPanel({ claim }: { claim: DiscoveredSourceClaim }) {
  return (
    <tr>
      <td colSpan={9} style={{ padding: 0 }}>
        <div style={{
          background: "rgba(15,23,42,0.95)",
          borderTop: "1px solid rgba(255,255,255,0.06)",
          borderBottom: "1px solid rgba(255,255,255,0.06)",
          padding: "18px 20px",
        }}>
          <div style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "16px 32px",
            fontSize: 12,
          }}>

            {/* Evidence Excerpt */}
            <div style={{ gridColumn: "1 / -1" }}>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", marginBottom: 6 }}>
                Evidence Excerpt
              </div>
              <div style={{ color: "#cbd5e1", lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12 }}>
                {claim.evidence_excerpt || <span style={{ color: "#64748b", fontStyle: "italic" }}>No excerpt available</span>}
              </div>
            </div>

            {/* Claim Value (full) */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", marginBottom: 4 }}>
                Claim Value
              </div>
              <div style={{ color: "#e2e8f0", fontFamily: "monospace", wordBreak: "break-all", fontSize: 12 }}>
                {claimValueToString(claim.claim_value)}
                {claim.claim_unit && (
                  <span style={{ color: "#94a3b8", marginLeft: 6 }}>{claim.claim_unit}</span>
                )}
              </div>
            </div>

            {/* Claim Type */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", marginBottom: 4 }}>
                Claim Type
              </div>
              <div style={{ color: "#e2e8f0", fontFamily: "monospace", fontSize: 12 }}>
                {claim.claim_type}
              </div>
            </div>

            {/* Source URL */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", marginBottom: 4 }}>
                Source URL
              </div>
              {claim.source_url ? (
                <a href={claim.source_url} target="_blank" rel="noopener noreferrer" style={{
                  color: "#818cf8", fontSize: 12, wordBreak: "break-all",
                }}>
                  {claim.source_url}
                </a>
              ) : (
                <span style={{ color: "#64748b" }}>—</span>
              )}
            </div>

            {/* Discovered Source ID */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", marginBottom: 4 }}>
                Discovered Source ID
              </div>
              <div style={{ color: "#94a3b8", fontFamily: "monospace", fontSize: 11, wordBreak: "break-all" }}>
                {claim.discovered_source_id}
              </div>
            </div>

            {/* Extractor */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", marginBottom: 4 }}>
                Extractor
              </div>
              <div style={{ color: "#94a3b8", fontSize: 12 }}>
                {claim.extractor_name || "—"}
                {claim.extractor_version && (
                  <span style={{ color: "#64748b", marginLeft: 6 }}>v{claim.extractor_version}</span>
                )}
              </div>
            </div>

            {/* Confidence */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", marginBottom: 4 }}>
                Confidence
              </div>
              <div style={{ color: "#cbd5e1", fontSize: 12 }}>
                {claim.confidence !== null && claim.confidence !== undefined
                  ? `${confDisplay(claim.confidence)} (raw: ${claim.confidence})`
                  : "—"}
              </div>
            </div>

            {/* Status */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", marginBottom: 4 }}>
                Status
              </div>
              <StatusBadge status={claim.status} />
            </div>

            {/* Timestamps */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", marginBottom: 4 }}>
                Created
              </div>
              <div style={{ color: "#94a3b8", fontSize: 12 }}>{formatDateTime(claim.created_at)}</div>
            </div>
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", marginBottom: 4 }}>
                Updated
              </div>
              <div style={{ color: "#94a3b8", fontSize: 12 }}>{formatDateTime(claim.updated_at)}</div>
            </div>

            {/* Claim ID */}
            <div style={{ gridColumn: "1 / -1" }}>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", marginBottom: 4 }}>
                Claim ID
              </div>
              <div style={{ color: "#64748b", fontFamily: "monospace", fontSize: 11 }}>
                {claim.id}
              </div>
            </div>

            {/* raw_metadata_json */}
            {claim.raw_metadata_json && (
              <div style={{ gridColumn: "1 / -1" }}>
                <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b", marginBottom: 4 }}>
                  Raw Metadata
                </div>
                <pre style={{
                  color: "#94a3b8", fontSize: 11, lineHeight: 1.5,
                  background: "rgba(255,255,255,0.04)", borderRadius: 4,
                  padding: "10px 12px", overflowX: "auto", maxHeight: 200,
                  margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-all",
                }}>
                  {JSON.stringify(claim.raw_metadata_json, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Table row
// ---------------------------------------------------------------------------

function ClaimRow({ claim }: { claim: DiscoveredSourceClaim }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <tr style={{
        borderBottom: "1px solid rgba(255,255,255,0.05)",
        background: expanded ? "rgba(15,23,42,0.6)" : "transparent",
        verticalAlign: "top",
        transition: "background 0.12s",
      }}>

        {/* Claim Type */}
        <td style={{
          padding: "11px 10px", color: "#e2e8f0", fontWeight: 600,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const,
        }}>
          {claimTypeLabel(claim.claim_type)}
        </td>

        {/* Claim Value */}
        <td style={{ padding: "11px 10px", overflow: "hidden" }}>
          <div style={{
            color: "#cbd5e1",
            overflow: "hidden",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            fontFamily: typeof claim.claim_value === "object" && claim.claim_value !== null ? "monospace" : undefined,
            fontSize: typeof claim.claim_value === "object" && claim.claim_value !== null ? 11 : 12,
          } as React.CSSProperties}>
            {claimValueToString(claim.claim_value)}
          </div>
        </td>

        {/* Unit */}
        <td style={{
          padding: "11px 10px", color: "#94a3b8", fontSize: 11,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const,
        }}>
          {claim.claim_unit || <span style={{ color: "#475569" }}>—</span>}
        </td>

        {/* Evidence Excerpt */}
        <td style={{ padding: "11px 10px", overflow: "hidden" }}>
          <div style={{
            color: "#94a3b8", fontSize: 11, lineHeight: 1.45,
            overflow: "hidden",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
          } as React.CSSProperties}>
            {claim.evidence_excerpt || <span style={{ color: "#475569", fontStyle: "italic" }}>No excerpt</span>}
          </div>
        </td>

        {/* Confidence */}
        <td style={{ padding: "11px 10px", overflow: "hidden" }}>
          <ConfBadge value={claim.confidence} />
        </td>

        {/* Status */}
        <td style={{ padding: "11px 10px", overflow: "hidden" }}>
          <StatusBadge status={claim.status} />
        </td>

        {/* Extractor */}
        <td style={{ padding: "11px 10px", overflow: "hidden" }}>
          <div style={{
            color: "#94a3b8", fontSize: 11,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {claim.extractor_name || <span style={{ color: "#475569" }}>—</span>}
          </div>
          {claim.extractor_version && (
            <div style={{ color: "#475569", fontSize: 10, marginTop: 2 }}>
              v{claim.extractor_version}
            </div>
          )}
        </td>

        {/* Created */}
        <td style={{
          padding: "11px 10px", color: "#64748b", fontSize: 11,
          whiteSpace: "nowrap" as const, overflow: "hidden",
        }}>
          {formatDate(claim.created_at)}
        </td>

        {/* Actions — sticky right */}
        <td style={{
          padding: "9px 10px",
          position: "sticky" as const,
          right: 0,
          background: expanded ? "rgba(15,23,42,0.97)" : "var(--bg)",
          boxShadow: "-2px 0 8px rgba(0,0,0,0.35)",
          zIndex: 2,
        }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {claim.source_url && <OpenSourceButton url={claim.source_url} />}
            {claim.source_url && <CopyButton text={claim.source_url} />}
            <DetailsToggleButton expanded={expanded} onClick={() => setExpanded(e => !e)} />
          </div>
        </td>
      </tr>

      {expanded && <DetailsPanel claim={claim} />}
    </>
  );
}

// ---------------------------------------------------------------------------
// Select dropdown helper
// ---------------------------------------------------------------------------

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
        color: value ? "#e2e8f0" : "#94a3b8",
        border: "1px solid rgba(255,255,255,0.12)",
        borderRadius: 6, padding: "7px 10px",
        fontSize: 12, cursor: "pointer",
        minWidth: 140,
      }}
    >
      <option value="">{placeholder}</option>
      {options.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const CONF_THRESHOLD_OPTIONS = [
  { value: "", label: "All confidence" },
  { value: "0.7", label: "High (≥70%)" },
  { value: "0.4", label: "Medium+ (≥40%)" },
  { value: "0.1", label: "Low+ (≥10%)" },
];

export function DiscoveredSourceClaimsPage() {
  const [claims, setClaims] = useState<DiscoveredSourceClaim[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchText, setSearchText] = useState("");
  const [filterClaimType, setFilterClaimType] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterConfThreshold, setFilterConfThreshold] = useState("");

  useEffect(() => {
    setLoading(true);
    setError(null);
    getDiscoveredSourceClaims({ limit: 500 })
      .then(resp => setClaims(resp.items))
      .catch(err => setError(String(err)))
      .finally(() => setLoading(false));
  }, []);

  const claimTypeOptions = useMemo(() => {
    const types = [...new Set(claims.map(c => c.claim_type))].sort();
    return types.map(t => ({ value: t, label: claimTypeLabel(t) }));
  }, [claims]);

  const statusOptions = useMemo(() => {
    const statuses = [...new Set(claims.map(c => c.status))].sort();
    return statuses.map(s => ({ value: s, label: s.charAt(0).toUpperCase() + s.slice(1) }));
  }, [claims]);

  const filtered = useMemo(() => {
    const needle = searchText.toLowerCase();
    const confMin = filterConfThreshold ? parseFloat(filterConfThreshold) : null;
    return claims.filter(c => {
      if (filterClaimType && c.claim_type !== filterClaimType) return false;
      if (filterStatus && c.status !== filterStatus) return false;
      if (confMin !== null && (c.confidence === null || c.confidence === undefined || c.confidence < confMin)) return false;
      if (needle) {
        const haystack = [
          c.claim_type,
          claimValueToString(c.claim_value),
          c.evidence_excerpt,
          c.source_url,
          c.extractor_name,
        ].join(" ").toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      return true;
    });
  }, [claims, searchText, filterClaimType, filterStatus, filterConfThreshold]);

  const countsByStatus = useMemo(() => {
    const m: Record<string, number> = {};
    for (const c of claims) m[c.status] = (m[c.status] ?? 0) + 1;
    return m;
  }, [claims]);

  const countsByType = useMemo(() => {
    const m: Record<string, number> = {};
    for (const c of claims) m[c.claim_type] = (m[c.claim_type] ?? 0) + 1;
    return m;
  }, [claims]);

  return (
    <div style={{
      display: "flex", flexDirection: "column", height: "100%", overflow: "hidden",
      background: "var(--bg)",
    }}>

      {/* Header */}
      <div style={{
        padding: "16px 24px 12px",
        borderBottom: "1px solid var(--border)",
        flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 8 }}>
          <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#e2e8f0" }}>
            Discovered Source Claims
          </h1>
          {!loading && !error && (
            <span style={{ fontSize: 13, color: "#64748b" }}>
              {filtered.length} of {claims.length} claims
            </span>
          )}
        </div>

        {/* Notice banners */}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" as const, marginBottom: 12 }}>
          <span style={{
            fontSize: 12, fontWeight: 600, padding: "4px 10px", borderRadius: 4,
            background: "rgba(245,158,11,0.12)", color: "#fbbf24",
            border: "1px solid rgba(245,158,11,0.3)",
          }}>
            Extracted claims only — not yet projects
          </span>
          <span style={{
            fontSize: 12, fontWeight: 600, padding: "4px 10px", borderRadius: 4,
            background: "rgba(148,163,184,0.08)", color: "#94a3b8",
            border: "1px solid rgba(148,163,184,0.2)",
          }}>
            Claims require review before promotion
          </span>
        </div>

        {/* Count pills */}
        {!loading && !error && claims.length > 0 && (
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap" as const, marginBottom: 14 }}>
            <div style={{ textAlign: "center" as const }}>
              <div style={{ fontSize: 20, fontWeight: 700, color: "#e2e8f0", lineHeight: 1 }}>{claims.length}</div>
              <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginTop: 2 }}>Total</div>
            </div>
            {Object.entries(countsByStatus).map(([s, n]) => {
              const { color } = statusColor(s);
              return (
                <div key={s} style={{ textAlign: "center" as const }}>
                  <div style={{ fontSize: 20, fontWeight: 700, color, lineHeight: 1 }}>{n}</div>
                  <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginTop: 2 }}>{s}</div>
                </div>
              );
            })}
            {Object.keys(countsByType).length <= 6 && Object.entries(countsByType).map(([t, n]) => (
              <div key={t} style={{ textAlign: "center" as const }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: "#818cf8", lineHeight: 1 }}>{n}</div>
                <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginTop: 2 }}>{t.replace(/_/g, " ")}</div>
              </div>
            ))}
          </div>
        )}

        {/* Filters */}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" as const, alignItems: "center" }}>
          <input
            type="text"
            placeholder="Search claim value, excerpt, URL…"
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            style={{
              flex: "1 1 260px", minWidth: 200, maxWidth: 400,
              padding: "7px 12px", fontSize: 12,
              background: "var(--bg-surface)", color: "#e2e8f0",
              border: "1px solid rgba(255,255,255,0.12)",
              borderRadius: 6, outline: "none",
            }}
          />
          <FilterSelect
            value={filterClaimType}
            onChange={setFilterClaimType}
            options={claimTypeOptions}
            placeholder="All claim types"
          />
          <FilterSelect
            value={filterStatus}
            onChange={setFilterStatus}
            options={statusOptions}
            placeholder="All statuses"
          />
          <FilterSelect
            value={filterConfThreshold}
            onChange={setFilterConfThreshold}
            options={CONF_THRESHOLD_OPTIONS.slice(1)}
            placeholder="All confidence"
          />
          {(searchText || filterClaimType || filterStatus || filterConfThreshold) && (
            <button
              onClick={() => {
                setSearchText("");
                setFilterClaimType("");
                setFilterStatus("");
                setFilterConfThreshold("");
              }}
              style={{
                padding: "7px 12px", fontSize: 12, cursor: "pointer",
                background: "transparent", color: "#64748b",
                border: "1px solid rgba(255,255,255,0.08)", borderRadius: 6,
              }}
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0 24px 24px" }}>

        {/* Loading */}
        {loading && (
          <div style={{ textAlign: "center", padding: "60px 24px", color: "#64748b", fontSize: 13 }}>
            Loading claims…
          </div>
        )}

        {/* Error */}
        {!loading && error && (
          <div style={{
            margin: "24px 0",
            padding: "16px 20px",
            background: "rgba(239,68,68,0.08)",
            border: "1px solid rgba(239,68,68,0.25)",
            borderRadius: 8, color: "#fca5a5", fontSize: 13,
          }}>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>Failed to load claims</div>
            <div style={{ fontSize: 12, color: "#ef4444", fontFamily: "monospace" }}>{error}</div>
          </div>
        )}

        {/* Empty state — no data at all */}
        {!loading && !error && claims.length === 0 && (
          <div style={{ maxWidth: 640, margin: "48px auto 0" }}>
            <div style={{
              padding: "28px 32px",
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 10,
            }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: "#94a3b8", marginBottom: 6 }}>
                No extracted claims found
              </div>
              <div style={{ fontSize: 13, color: "#64748b", marginBottom: 20, lineHeight: 1.6 }}>
                Claims are generated by the extraction script. To generate claims, run:
              </div>
              <pre style={{
                background: "rgba(0,0,0,0.3)", borderRadius: 6,
                padding: "14px 16px", fontSize: 12, color: "#a5b4fc",
                overflowX: "auto", lineHeight: 1.7, margin: 0,
              }}>
{`cd backend
source .venv/bin/activate

# 1. Apply migrations
DATABASE_URL=sqlite:///local.db alembic upgrade head

# 2. Ingest discovered sources
DATABASE_URL=sqlite:///local.db python scripts/ingest_public_discovered_sources.py \\
  --input tests/fixtures/public_discovered_sources.json

# 3. Extract claims
DATABASE_URL=sqlite:///local.db python scripts/extract_discovered_source_claims.py`}
              </pre>
              <div style={{ fontSize: 12, color: "#64748b", marginTop: 14 }}>
                Then refresh this page to see extracted claims.
              </div>
            </div>
          </div>
        )}

        {/* Empty state — filters exclude all */}
        {!loading && !error && claims.length > 0 && filtered.length === 0 && (
          <div style={{
            textAlign: "center", padding: "48px 24px",
            color: "#64748b", fontSize: 13,
          }}>
            No claims match the current filters.{" "}
            <button
              onClick={() => { setSearchText(""); setFilterClaimType(""); setFilterStatus(""); setFilterConfThreshold(""); }}
              style={{
                background: "none", border: "none", color: "#818cf8",
                cursor: "pointer", fontSize: 13, padding: 0,
                textDecoration: "underline",
              }}
            >
              Clear filters
            </button>
          </div>
        )}

        {/* Table */}
        {!loading && !error && filtered.length > 0 && (
          <div style={{ overflowX: "auto", marginTop: 12 }}>
            <table style={{
              borderCollapse: "collapse",
              fontSize: 12,
              tableLayout: "fixed",
              width: "100%",
              minWidth: 900,
            }}>
              {/* Column widths: 120+160+70+200+90+86+110+86+120 = 1042px */}
              <colgroup>
                <col style={{ width: 120 }} />
                <col style={{ width: 160 }} />
                <col style={{ width: 70 }} />
                <col style={{ width: 200 }} />
                <col style={{ width: 90 }} />
                <col style={{ width: 86 }} />
                <col style={{ width: 110 }} />
                <col style={{ width: 86 }} />
                <col style={{ width: 120 }} />
              </colgroup>
              <thead>
                <tr style={{ borderBottom: "2px solid rgba(255,255,255,0.1)" }}>
                  {[
                    "Claim Type", "Claim Value", "Unit",
                    "Evidence Excerpt", "Confidence", "Status",
                    "Extractor", "Created", "Actions",
                  ].map((label, i) => (
                    <th key={label} style={{
                      padding: "9px 10px", textAlign: "left",
                      fontSize: 10, fontWeight: 700, textTransform: "uppercase" as const,
                      letterSpacing: "0.08em", color: "#94a3b8",
                      whiteSpace: "nowrap" as const,
                      overflow: "hidden",
                      position: "sticky" as const, top: 0,
                      background: "var(--bg)", zIndex: i === 8 ? 3 : 1,
                      borderBottom: "1px solid rgba(255,255,255,0.08)",
                      ...(i === 8 ? {
                        right: 0,
                        boxShadow: "-2px 0 6px rgba(0,0,0,0.3)",
                      } : {}),
                    }}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(claim => (
                  <ClaimRow key={claim.id} claim={claim} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Link to discovered sources */}
        {!loading && !error && claims.length > 0 && (
          <div style={{ marginTop: 20, fontSize: 12, color: "#64748b" }}>
            Claims are linked to sources on the{" "}
            <a href="/discovered-sources" style={{ color: "#818cf8" }}>
              Discovered Sources
            </a>{" "}
            page. Use the{" "}
            <span style={{ fontFamily: "monospace", color: "#94a3b8", fontSize: 11 }}>
              discovered_source_id
            </span>{" "}
            in the Details panel to cross-reference.
          </div>
        )}
      </div>
    </div>
  );
}
