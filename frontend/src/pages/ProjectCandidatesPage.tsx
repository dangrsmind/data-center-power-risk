import { useEffect, useState, useMemo, useCallback } from "react";
import type { ProjectCandidate, ProjectCandidatePromotionResponse } from "../api/types";
import { getProjectCandidates, promoteProjectCandidate } from "../api/adapter";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

function confDisplay(v: number): string {
  return `${Math.round(v * 100)}%`;
}

function confColor(v: number): { color: string; bg: string } {
  if (v >= 0.7) return { color: "#22c55e", bg: "rgba(34,197,94,0.15)" };
  if (v >= 0.4) return { color: "#f59e0b", bg: "rgba(245,158,11,0.15)" };
  return { color: "#ef4444", bg: "rgba(239,68,68,0.15)" };
}

function statusColor(s: string): { color: string; bg: string } {
  const map: Record<string, { color: string; bg: string }> = {
    candidate:    { color: "#94a3b8", bg: "rgba(148,163,184,0.1)" },
    needs_review: { color: "#f59e0b", bg: "rgba(245,158,11,0.12)" },
    rejected:     { color: "#ef4444", bg: "rgba(239,68,68,0.1)" },
    promoted:     { color: "#22c55e", bg: "rgba(34,197,94,0.12)" },
  };
  return map[s] ?? { color: "#94a3b8", bg: "rgba(148,163,184,0.1)" };
}

function lifecycleLabel(s: string | null): string {
  if (!s) return "—";
  return s.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function isUnresolved(name: string): boolean {
  return !name || name.trim().toLowerCase().startsWith("unresolved");
}

// ---------------------------------------------------------------------------
// Small shared components
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
      {status.replace(/_/g, " ")}
    </span>
  );
}

function ConfBadge({ value }: { value: number }) {
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

function CopyButton({ text, label = "⎘ Copy URL" }: { text: string; label?: string }) {
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
      {copied ? "✓ Copied" : label}
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
// Promotion modal
// ---------------------------------------------------------------------------

type ModalPhase = "review" | "pending" | "success" | "failed";

function PromoteModal({
  candidate,
  onClose,
  onSuccess,
}: {
  candidate: ProjectCandidate;
  onClose: () => void;
  onSuccess: (resp: ProjectCandidatePromotionResponse) => void;
}) {
  const [phase, setPhase] = useState<ModalPhase>("review");
  const [allowUnresolved, setAllowUnresolved] = useState(false);
  const [allowIncomplete, setAllowIncomplete] = useState(false);
  const [result, setResult] = useState<ProjectCandidatePromotionResponse | null>(null);

  const needsUnresolvedOverride = isUnresolved(candidate.candidate_name);
  const needsIncompleteOverride = !candidate.state;

  const handlePromote = useCallback(async () => {
    setPhase("pending");
    try {
      const resp = await promoteProjectCandidate(candidate.id, {
        confirm: true,
        allow_unresolved_name: allowUnresolved,
        allow_incomplete: allowIncomplete,
      });
      setResult(resp);
      if (resp.promoted) {
        setPhase("success");
        onSuccess(resp);
      } else {
        setPhase("failed");
      }
    } catch (err) {
      setResult({
        dry_run: false,
        candidate_id: candidate.id,
        promoted: false,
        project_created: false,
        project_updated: false,
        would_promote: false,
        would_create_project: false,
        would_update_project: false,
        evidence_created: 0,
        warnings: [],
        errors: [String(err)],
        promoted_project_id: null,
      });
      setPhase("failed");
    }
  }, [candidate.id, allowUnresolved, allowIncomplete, onSuccess]);

  const canPromote =
    phase === "review" &&
    (!needsUnresolvedOverride || allowUnresolved) &&
    (!needsIncompleteOverride || allowIncomplete);

  const overlayStyle: React.CSSProperties = {
    position: "fixed", inset: 0, zIndex: 1000,
    background: "rgba(0,0,0,0.72)",
    display: "flex", alignItems: "center", justifyContent: "center",
    padding: 24,
  };

  const panelStyle: React.CSSProperties = {
    background: "#0f172a",
    border: "1px solid rgba(255,255,255,0.12)",
    borderRadius: 10,
    width: "100%", maxWidth: 560,
    maxHeight: "90vh",
    overflowY: "auto",
    boxShadow: "0 24px 48px rgba(0,0,0,0.6)",
  };

  const sectionLabel: React.CSSProperties = {
    fontSize: 10, fontWeight: 700, textTransform: "uppercase",
    letterSpacing: "0.08em", color: "#64748b", marginBottom: 4,
  };

  return (
    <div style={overlayStyle} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={panelStyle}>

        {/* Header */}
        <div style={{
          padding: "18px 20px 14px",
          borderBottom: "1px solid rgba(255,255,255,0.08)",
          display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12,
        }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "#e2e8f0" }}>
              Promote Candidate
            </div>
            <div style={{ fontSize: 12, color: "#64748b", marginTop: 3 }}>
              Single-candidate promotion — no bulk actions
            </div>
          </div>
          <button onClick={onClose} style={{
            background: "none", border: "none", color: "#64748b", cursor: "pointer",
            fontSize: 18, lineHeight: 1, padding: "2px 4px", flexShrink: 0,
          }}>✕</button>
        </div>

        {/* Body */}
        <div style={{ padding: "18px 20px" }}>

          {/* Success state */}
          {phase === "success" && result && (
            <div>
              <div style={{
                background: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.35)",
                borderRadius: 8, padding: "14px 16px", marginBottom: 16,
              }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#22c55e", marginBottom: 4 }}>
                  ✓ Candidate promoted successfully
                </div>
                {result.project_created && (
                  <div style={{ fontSize: 12, color: "#86efac" }}>A new Project record was created.</div>
                )}
                {result.project_updated && (
                  <div style={{ fontSize: 12, color: "#86efac" }}>An existing Project record was updated.</div>
                )}
                {result.evidence_created > 0 && (
                  <div style={{ fontSize: 12, color: "#86efac" }}>
                    {result.evidence_created} evidence record{result.evidence_created !== 1 ? "s" : ""} created.
                  </div>
                )}
              </div>
              {result.promoted_project_id && (
                <div style={{ marginBottom: 14 }}>
                  <div style={sectionLabel}>Promoted Project ID</div>
                  <div style={{
                    fontFamily: "monospace", fontSize: 12, color: "#a5b4fc",
                    background: "rgba(99,102,241,0.1)", padding: "8px 10px",
                    borderRadius: 6, wordBreak: "break-all",
                  }}>
                    {result.promoted_project_id}
                  </div>
                </div>
              )}
              {result.warnings.length > 0 && (
                <div style={{
                  background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.25)",
                  borderRadius: 6, padding: "10px 12px", marginBottom: 14,
                }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#fbbf24", marginBottom: 6 }}>
                    Warnings
                  </div>
                  {result.warnings.map((w, i) => (
                    <div key={i} style={{ fontSize: 11, color: "#fcd34d", marginBottom: 2 }}>• {w}</div>
                  ))}
                </div>
              )}
              <button onClick={onClose} style={{
                width: "100%", padding: "10px 16px",
                fontSize: 13, fontWeight: 700, cursor: "pointer",
                background: "rgba(34,197,94,0.15)", color: "#22c55e",
                border: "1px solid rgba(34,197,94,0.4)",
                borderRadius: 6,
              }}>
                Close
              </button>
            </div>
          )}

          {/* Failed state */}
          {phase === "failed" && result && (
            <div>
              <div style={{
                background: "rgba(239,68,68,0.09)", border: "1px solid rgba(239,68,68,0.3)",
                borderRadius: 8, padding: "14px 16px", marginBottom: 16,
              }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#ef4444", marginBottom: 6 }}>
                  Promotion failed
                </div>
                {result.errors.map((e, i) => (
                  <div key={i} style={{ fontSize: 12, color: "#fca5a5", marginBottom: 2 }}>• {e}</div>
                ))}
              </div>
              {result.warnings.length > 0 && (
                <div style={{
                  background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.25)",
                  borderRadius: 6, padding: "10px 12px", marginBottom: 14,
                }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#fbbf24", marginBottom: 4 }}>
                    Warnings
                  </div>
                  {result.warnings.map((w, i) => (
                    <div key={i} style={{ fontSize: 11, color: "#fcd34d", marginBottom: 2 }}>• {w}</div>
                  ))}
                </div>
              )}
              <div style={{ display: "flex", gap: 10 }}>
                <button onClick={() => { setPhase("review"); setResult(null); }} style={{
                  flex: 1, padding: "9px 16px",
                  fontSize: 12, fontWeight: 600, cursor: "pointer",
                  background: "rgba(255,255,255,0.06)", color: "#94a3b8",
                  border: "1px solid rgba(255,255,255,0.12)", borderRadius: 6,
                }}>
                  ← Try again
                </button>
                <button onClick={onClose} style={{
                  flex: 1, padding: "9px 16px",
                  fontSize: 12, fontWeight: 600, cursor: "pointer",
                  background: "transparent", color: "#64748b",
                  border: "1px solid rgba(255,255,255,0.08)", borderRadius: 6,
                }}>
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Review / pending state */}
          {(phase === "review" || phase === "pending") && (
            <div>
              {/* Warning banner */}
              <div style={{
                background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.35)",
                borderRadius: 7, padding: "12px 14px", marginBottom: 18,
              }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#fbbf24", marginBottom: 4 }}>
                  Review required
                </div>
                <div style={{ fontSize: 12, color: "#fcd34d", lineHeight: 1.5 }}>
                  This will create a real Project record from this candidate.
                  Continue only after review.
                </div>
              </div>

              {/* Candidate summary */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 20px", marginBottom: 18 }}>
                <div style={{ gridColumn: "1 / -1" }}>
                  <div style={sectionLabel}>Candidate Name</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#e2e8f0" }}>
                    {candidate.candidate_name}
                  </div>
                </div>

                {(candidate.state || candidate.county || candidate.city) && (
                  <div>
                    <div style={sectionLabel}>Location</div>
                    <div style={{ fontSize: 12, color: "#cbd5e1" }}>
                      {[candidate.city, candidate.county, candidate.state].filter(Boolean).join(", ")}
                    </div>
                  </div>
                )}

                <div>
                  <div style={sectionLabel}>Confidence</div>
                  <ConfBadge value={candidate.confidence} />
                </div>

                <div>
                  <div style={sectionLabel}>Sources / Claims</div>
                  <div style={{ fontSize: 12, color: "#cbd5e1" }}>
                    {candidate.source_count} source{candidate.source_count !== 1 ? "s" : ""},
                    {" "}{candidate.claim_count} claim{candidate.claim_count !== 1 ? "s" : ""}
                  </div>
                </div>

                {candidate.primary_source_url && (
                  <div style={{ gridColumn: "1 / -1" }}>
                    <div style={sectionLabel}>Primary Source</div>
                    <a href={candidate.primary_source_url} target="_blank" rel="noopener noreferrer"
                      style={{ fontSize: 11, color: "#818cf8", wordBreak: "break-all" }}>
                      {candidate.primary_source_url}
                    </a>
                  </div>
                )}

                {candidate.evidence_excerpt && (
                  <div style={{ gridColumn: "1 / -1" }}>
                    <div style={sectionLabel}>Evidence Excerpt</div>
                    <div style={{
                      fontSize: 11, color: "#94a3b8", lineHeight: 1.55,
                      background: "rgba(255,255,255,0.04)", borderRadius: 5,
                      padding: "8px 10px", maxHeight: 110, overflowY: "auto",
                      whiteSpace: "pre-wrap", wordBreak: "break-word",
                    }}>
                      {candidate.evidence_excerpt}
                    </div>
                  </div>
                )}
              </div>

              {/* Safety gates */}
              {needsUnresolvedOverride && (
                <div style={{
                  background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.28)",
                  borderRadius: 7, padding: "12px 14px", marginBottom: 12,
                }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#ef4444", marginBottom: 6 }}>
                    Unresolved name detected
                  </div>
                  <div style={{ fontSize: 12, color: "#fca5a5", marginBottom: 10, lineHeight: 1.5 }}>
                    Candidates with unresolved names are blocked by default.
                    Only override if you have verified the name is acceptable.
                  </div>
                  <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={allowUnresolved}
                      onChange={e => setAllowUnresolved(e.target.checked)}
                      style={{ width: 14, height: 14, accentColor: "#f59e0b", cursor: "pointer" }}
                    />
                    <span style={{ fontSize: 12, color: "#fbbf24", fontWeight: 600 }}>
                      Allow unresolved name
                    </span>
                  </label>
                </div>
              )}

              {needsIncompleteOverride && (
                <div style={{
                  background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.28)",
                  borderRadius: 7, padding: "12px 14px", marginBottom: 12,
                }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#ef4444", marginBottom: 6 }}>
                    Incomplete candidate
                  </div>
                  <div style={{ fontSize: 12, color: "#fca5a5", marginBottom: 10, lineHeight: 1.5 }}>
                    Required fields (state) are missing. Promotion is blocked by default
                    for incomplete candidates.
                  </div>
                  <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={allowIncomplete}
                      onChange={e => setAllowIncomplete(e.target.checked)}
                      style={{ width: 14, height: 14, accentColor: "#f59e0b", cursor: "pointer" }}
                    />
                    <span style={{ fontSize: 12, color: "#fbbf24", fontWeight: 600 }}>
                      Allow incomplete candidate
                    </span>
                  </label>
                </div>
              )}

              {/* Action row */}
              <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
                <button
                  onClick={handlePromote}
                  disabled={!canPromote}
                  style={{
                    flex: 1, padding: "11px 16px",
                    fontSize: 13, fontWeight: 700, cursor: canPromote ? "pointer" : "not-allowed",
                    background: canPromote
                      ? "rgba(99,102,241,0.22)"
                      : "rgba(99,102,241,0.07)",
                    color: canPromote ? "#a5b4fc" : "#475569",
                    border: canPromote
                      ? "1px solid rgba(99,102,241,0.5)"
                      : "1px solid rgba(99,102,241,0.15)",
                    borderRadius: 6,
                    transition: "all 0.12s",
                  }}
                >
                  {phase === "pending" ? "Promoting…" : "Promote candidate"}
                </button>
                <button
                  onClick={onClose}
                  disabled={phase === "pending"}
                  style={{
                    padding: "11px 20px",
                    fontSize: 12, fontWeight: 600, cursor: "pointer",
                    background: "transparent", color: "#64748b",
                    border: "1px solid rgba(255,255,255,0.08)", borderRadius: 6,
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Details expansion panel
// ---------------------------------------------------------------------------

function DetailsPanel({ c }: { c: ProjectCandidate }) {
  const sourceIds: string[] = Array.isArray(c.discovered_source_ids_json)
    ? (c.discovered_source_ids_json as string[])
    : [];
  const claimIds: string[] = Array.isArray(c.discovered_source_claim_ids_json)
    ? (c.discovered_source_claim_ids_json as string[])
    : [];

  const sectionLabel: React.CSSProperties = {
    fontSize: 10, fontWeight: 700, textTransform: "uppercase",
    letterSpacing: "0.08em", color: "#64748b", marginBottom: 4,
  };

  return (
    <tr>
      <td colSpan={10} style={{ padding: 0 }}>
        <div style={{
          background: "rgba(15,23,42,0.95)",
          borderTop: "1px solid rgba(255,255,255,0.06)",
          borderBottom: "1px solid rgba(255,255,255,0.06)",
          padding: "18px 20px",
        }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px 32px", fontSize: 12 }}>

            {c.evidence_excerpt && (
              <div style={{ gridColumn: "1 / -1" }}>
                <div style={sectionLabel}>Evidence Excerpt</div>
                <div style={{ color: "#cbd5e1", lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                  {c.evidence_excerpt}
                </div>
              </div>
            )}

            <div>
              <div style={sectionLabel}>Primary Source URL</div>
              {c.primary_source_url ? (
                <a href={c.primary_source_url} target="_blank" rel="noopener noreferrer"
                  style={{ color: "#818cf8", wordBreak: "break-all" }}>
                  {c.primary_source_url}
                </a>
              ) : (
                <span style={{ color: "#64748b" }}>—</span>
              )}
            </div>

            <div>
              <div style={sectionLabel}>Evidence Counts</div>
              <div style={{ color: "#cbd5e1" }}>
                {c.source_count} source{c.source_count !== 1 ? "s" : ""},&nbsp;
                {c.claim_count} claim{c.claim_count !== 1 ? "s" : ""}
              </div>
            </div>

            <div>
              <div style={sectionLabel}>Confidence</div>
              <div style={{ color: "#cbd5e1" }}>{confDisplay(c.confidence)} (raw: {c.confidence})</div>
            </div>

            <div>
              <div style={sectionLabel}>Status</div>
              <StatusBadge status={c.status} />
            </div>

            {c.promoted_project_id && (
              <div style={{ gridColumn: "1 / -1" }}>
                <div style={sectionLabel}>Promoted Project ID</div>
                <div style={{ color: "#a5b4fc", fontFamily: "monospace", fontSize: 11 }}>
                  {c.promoted_project_id}
                </div>
              </div>
            )}

            {c.utility && (
              <div>
                <div style={sectionLabel}>Utility</div>
                <div style={{ color: "#cbd5e1" }}>{c.utility}</div>
              </div>
            )}

            {c.lifecycle_state && (
              <div>
                <div style={sectionLabel}>Lifecycle State</div>
                <div style={{ color: "#cbd5e1" }}>{lifecycleLabel(c.lifecycle_state)}</div>
              </div>
            )}

            <div>
              <div style={sectionLabel}>Created</div>
              <div style={{ color: "#94a3b8" }}>{formatDateTime(c.created_at)}</div>
            </div>
            <div>
              <div style={sectionLabel}>Updated</div>
              <div style={{ color: "#94a3b8" }}>{formatDateTime(c.updated_at)}</div>
            </div>

            <div style={{ gridColumn: "1 / -1" }}>
              <div style={sectionLabel}>Candidate ID</div>
              <div style={{ color: "#64748b", fontFamily: "monospace", fontSize: 11 }}>{c.id}</div>
            </div>

            {sourceIds.length > 0 && (
              <div style={{ gridColumn: "1 / -1" }}>
                <div style={sectionLabel}>
                  Discovered Source IDs ({sourceIds.length}){" "}
                  <a href="/discovered-sources" style={{ color: "#818cf8", fontWeight: 400, textTransform: "none", fontSize: 11 }}>
                    → view sources
                  </a>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                  {sourceIds.map((sid, i) => (
                    <div key={i} style={{ color: "#94a3b8", fontFamily: "monospace", fontSize: 11 }}>{sid}</div>
                  ))}
                </div>
              </div>
            )}

            {claimIds.length > 0 && (
              <div style={{ gridColumn: "1 / -1" }}>
                <div style={sectionLabel}>
                  Discovered Source Claim IDs ({claimIds.length}){" "}
                  <a href="/discovered-source-claims" style={{ color: "#818cf8", fontWeight: 400, textTransform: "none", fontSize: 11 }}>
                    → view claims
                  </a>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                  {claimIds.map((cid, i) => (
                    <div key={i} style={{ color: "#94a3b8", fontFamily: "monospace", fontSize: 11 }}>{cid}</div>
                  ))}
                </div>
              </div>
            )}

            {c.raw_metadata_json && (
              <div style={{ gridColumn: "1 / -1" }}>
                <div style={sectionLabel}>Raw Metadata</div>
                <pre style={{
                  color: "#94a3b8", fontSize: 11, lineHeight: 1.5,
                  background: "rgba(255,255,255,0.04)", borderRadius: 4,
                  padding: "10px 12px", overflowX: "auto", maxHeight: 200,
                  margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-all",
                }}>
                  {JSON.stringify(c.raw_metadata_json, null, 2)}
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

function CandidateRow({
  c,
  onPromote,
}: {
  c: ProjectCandidate;
  onPromote: (c: ProjectCandidate) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const isPromoted = c.status === "promoted";

  return (
    <>
      <tr style={{
        borderBottom: "1px solid rgba(255,255,255,0.05)",
        background: expanded ? "rgba(15,23,42,0.6)" : "transparent",
        verticalAlign: "top",
        transition: "background 0.12s",
      }}>

        {/* Candidate Name */}
        <td style={{ padding: "11px 10px", overflow: "hidden" }}>
          <div style={{
            fontWeight: 600, color: "#e2e8f0", lineHeight: 1.35,
            overflow: "hidden",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
          } as React.CSSProperties}>
            {c.candidate_name}
          </div>
          {c.utility && (
            <div style={{
              fontSize: 10, color: "#64748b", marginTop: 2,
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>
              {c.utility}
            </div>
          )}
        </td>

        {/* Developer */}
        <td style={{
          padding: "11px 10px", color: "#cbd5e1",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const,
        }}>
          {c.developer || <span style={{ color: "#475569" }}>—</span>}
        </td>

        {/* State / County */}
        <td style={{ padding: "11px 10px", overflow: "hidden" }}>
          <div style={{
            color: "#cbd5e1", fontWeight: 600, fontSize: 12,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {c.state || "—"}
          </div>
          {c.county && (
            <div style={{
              fontSize: 11, color: "#94a3b8", marginTop: 1,
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>
              {c.county}
            </div>
          )}
        </td>

        {/* City */}
        <td style={{
          padding: "11px 10px", color: "#94a3b8", fontSize: 12,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const,
        }}>
          {c.city || <span style={{ color: "#475569" }}>—</span>}
        </td>

        {/* Load MW */}
        <td style={{ padding: "11px 10px", overflow: "hidden", textAlign: "right" as const }}>
          {c.load_mw !== null && c.load_mw !== undefined ? (
            <span style={{ color: "#e2e8f0", fontWeight: 600, fontSize: 12 }}>
              {c.load_mw % 1 === 0 ? c.load_mw.toFixed(0) : c.load_mw.toFixed(1)}
              <span style={{ color: "#64748b", fontSize: 10, marginLeft: 3 }}>MW</span>
            </span>
          ) : (
            <span style={{ color: "#475569" }}>—</span>
          )}
        </td>

        {/* Lifecycle */}
        <td style={{
          padding: "11px 10px", color: "#94a3b8", fontSize: 11,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const,
        }}>
          {lifecycleLabel(c.lifecycle_state)}
        </td>

        {/* Confidence */}
        <td style={{ padding: "11px 10px", overflow: "hidden" }}>
          <ConfBadge value={c.confidence} />
        </td>

        {/* Status */}
        <td style={{ padding: "11px 10px", overflow: "hidden" }}>
          <StatusBadge status={c.status} />
        </td>

        {/* Sources + Claims */}
        <td style={{ padding: "11px 10px", overflow: "hidden", textAlign: "center" as const }}>
          <div style={{ color: "#e2e8f0", fontSize: 12, fontWeight: 600 }}>{c.source_count}</div>
          <div style={{ fontSize: 10, color: "#64748b" }}>src</div>
          {c.claim_count > 0 && (
            <>
              <div style={{ color: "#818cf8", fontSize: 12, fontWeight: 600, marginTop: 3 }}>{c.claim_count}</div>
              <div style={{ fontSize: 10, color: "#64748b" }}>claims</div>
            </>
          )}
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
            {c.primary_source_url && <OpenSourceButton url={c.primary_source_url} />}
            {c.primary_source_url && <CopyButton text={c.primary_source_url} />}
            <DetailsToggleButton expanded={expanded} onClick={() => setExpanded(e => !e)} />

            {/* Promotion action */}
            {isPromoted ? (
              <div>
                <div style={{
                  padding: "5px 9px",
                  fontSize: 11, fontWeight: 700,
                  background: "rgba(34,197,94,0.12)", color: "#22c55e",
                  border: "1px solid rgba(34,197,94,0.35)",
                  borderRadius: 4, textAlign: "center",
                }}>
                  ✓ Promoted
                </div>
                {c.promoted_project_id && (
                  <CopyButton
                    text={c.promoted_project_id}
                    label="⎘ Copy project ID"
                  />
                )}
              </div>
            ) : (
              <button
                onClick={() => onPromote(c)}
                style={{
                  display: "block", width: "100%", padding: "5px 9px",
                  fontSize: 11, fontWeight: 700, cursor: "pointer",
                  background: "rgba(99,102,241,0.14)", color: "#818cf8",
                  border: "1px solid rgba(99,102,241,0.4)",
                  borderRadius: 4, textAlign: "center" as const,
                  whiteSpace: "nowrap" as const,
                  letterSpacing: "0.02em",
                }}
              >
                ↑ Promote
              </button>
            )}
          </div>
        </td>
      </tr>

      {expanded && <DetailsPanel c={c} />}
    </>
  );
}

// ---------------------------------------------------------------------------
// Filter select
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
        fontSize: 12, cursor: "pointer", minWidth: 140,
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

const CONF_OPTIONS = [
  { value: "0.7", label: "High (≥70%)" },
  { value: "0.4", label: "Medium+ (≥40%)" },
  { value: "0.1", label: "Low+ (≥10%)" },
];

export function ProjectCandidatesPage() {
  const [candidates, setCandidates] = useState<ProjectCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchText, setSearchText] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterState, setFilterState] = useState("");
  const [filterConf, setFilterConf] = useState("");

  const [promotingCandidate, setPromotingCandidate] = useState<ProjectCandidate | null>(null);

  const fetchCandidates = useCallback(() => {
    setLoading(true);
    setError(null);
    getProjectCandidates({ limit: 500 })
      .then(resp => setCandidates(resp.items))
      .catch(err => setError(String(err)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchCandidates(); }, [fetchCandidates]);

  const handlePromotionSuccess = useCallback((_resp: ProjectCandidatePromotionResponse) => {
    fetchCandidates();
  }, [fetchCandidates]);

  const statusOptions = useMemo(() => {
    const s = [...new Set(candidates.map(c => c.status))].sort();
    return s.map(v => ({
      value: v,
      label: v.replace(/_/g, " ").replace(/\b\w/g, ch => ch.toUpperCase()),
    }));
  }, [candidates]);

  const stateOptions = useMemo(() => {
    const s = [...new Set(candidates.map(c => c.state).filter(Boolean) as string[])].sort();
    return s.map(v => ({ value: v, label: v }));
  }, [candidates]);

  const filtered = useMemo(() => {
    const needle = searchText.toLowerCase();
    const confMin = filterConf ? parseFloat(filterConf) : null;
    return candidates.filter(c => {
      if (filterStatus && c.status !== filterStatus) return false;
      if (filterState && c.state !== filterState) return false;
      if (confMin !== null && c.confidence < confMin) return false;
      if (needle) {
        const hay = [
          c.candidate_name, c.developer, c.state,
          c.county, c.city, c.utility, c.primary_source_url,
        ].join(" ").toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
  }, [candidates, searchText, filterStatus, filterState, filterConf]);

  const countsByStatus = useMemo(() => {
    const m: Record<string, number> = {};
    for (const c of candidates) m[c.status] = (m[c.status] ?? 0) + 1;
    return m;
  }, [candidates]);

  const hasFilters = !!(searchText || filterStatus || filterState || filterConf);
  const clearFilters = () => {
    setSearchText(""); setFilterStatus(""); setFilterState(""); setFilterConf("");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden", background: "var(--bg)" }}>

      {/* Promotion modal */}
      {promotingCandidate && (
        <PromoteModal
          candidate={promotingCandidate}
          onClose={() => setPromotingCandidate(null)}
          onSuccess={handlePromotionSuccess}
        />
      )}

      {/* Header */}
      <div style={{ padding: "16px 24px 12px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 8 }}>
          <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#e2e8f0" }}>
            Project Candidates
          </h1>
          {!loading && !error && (
            <span style={{ fontSize: 13, color: "#64748b" }}>
              {filtered.length} of {candidates.length} candidates
            </span>
          )}
        </div>

        {/* Notice banners */}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" as const, marginBottom: 12 }}>
          {[
            { text: "Candidate records only — not final projects", amber: true },
            { text: "Review required before promotion", amber: false },
            { text: "No public source, no project record", amber: false },
          ].map(({ text, amber }) => (
            <span key={text} style={{
              fontSize: 12, fontWeight: 600, padding: "4px 10px", borderRadius: 4,
              background: amber ? "rgba(245,158,11,0.12)" : "rgba(148,163,184,0.08)",
              color: amber ? "#fbbf24" : "#94a3b8",
              border: amber ? "1px solid rgba(245,158,11,0.3)" : "1px solid rgba(148,163,184,0.2)",
            }}>
              {text}
            </span>
          ))}
        </div>

        {/* Count pills */}
        {!loading && !error && candidates.length > 0 && (
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" as const, marginBottom: 14 }}>
            <div style={{ textAlign: "center" as const }}>
              <div style={{ fontSize: 20, fontWeight: 700, color: "#e2e8f0", lineHeight: 1 }}>{candidates.length}</div>
              <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginTop: 2 }}>Total</div>
            </div>
            {Object.entries(countsByStatus).map(([s, n]) => {
              const { color } = statusColor(s);
              return (
                <div key={s} style={{ textAlign: "center" as const }}>
                  <div style={{ fontSize: 20, fontWeight: 700, color, lineHeight: 1 }}>{n}</div>
                  <div style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em", marginTop: 2 }}>
                    {s.replace(/_/g, " ")}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Filters */}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" as const, alignItems: "center" }}>
          <input
            type="text"
            placeholder="Search name, developer, state, city, utility, URL…"
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            style={{
              flex: "1 1 280px", minWidth: 200, maxWidth: 420,
              padding: "7px 12px", fontSize: 12,
              background: "var(--bg-surface)", color: "#e2e8f0",
              border: "1px solid rgba(255,255,255,0.12)",
              borderRadius: 6, outline: "none",
            }}
          />
          <FilterSelect value={filterStatus} onChange={setFilterStatus} options={statusOptions} placeholder="All statuses" />
          <FilterSelect value={filterState} onChange={setFilterState} options={stateOptions} placeholder="All states" />
          <FilterSelect value={filterConf} onChange={setFilterConf} options={CONF_OPTIONS} placeholder="All confidence" />
          {hasFilters && (
            <button onClick={clearFilters} style={{
              padding: "7px 12px", fontSize: 12, cursor: "pointer",
              background: "transparent", color: "#64748b",
              border: "1px solid rgba(255,255,255,0.08)", borderRadius: 6,
            }}>
              Clear filters
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0 24px 24px" }}>

        {loading && (
          <div style={{ textAlign: "center", padding: "60px 24px", color: "#64748b", fontSize: 13 }}>
            Loading candidates…
          </div>
        )}

        {!loading && error && (
          <div style={{
            margin: "24px 0", padding: "16px 20px",
            background: "rgba(239,68,68,0.08)",
            border: "1px solid rgba(239,68,68,0.25)",
            borderRadius: 8, color: "#fca5a5", fontSize: 13,
          }}>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>Failed to load candidates</div>
            <div style={{ fontSize: 12, color: "#ef4444", fontFamily: "monospace" }}>{error}</div>
          </div>
        )}

        {/* Empty — no data */}
        {!loading && !error && candidates.length === 0 && (
          <div style={{ maxWidth: 660, margin: "48px auto 0" }}>
            <div style={{
              padding: "28px 32px",
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 10,
            }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: "#94a3b8", marginBottom: 6 }}>
                No project candidates found
              </div>
              <div style={{ fontSize: 13, color: "#64748b", marginBottom: 20, lineHeight: 1.6 }}>
                Candidates are generated from extracted claims. To generate candidates, run:
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
DATABASE_URL=sqlite:///local.db python scripts/extract_discovered_source_claims.py

# 4. Generate project candidates
DATABASE_URL=sqlite:///local.db python scripts/generate_project_candidates.py`}
              </pre>
              <div style={{ fontSize: 12, color: "#64748b", marginTop: 14 }}>
                Then refresh this page to see generated candidates.
              </div>
            </div>
          </div>
        )}

        {/* Empty — filters exclude all */}
        {!loading && !error && candidates.length > 0 && filtered.length === 0 && (
          <div style={{ textAlign: "center", padding: "48px 24px", color: "#64748b", fontSize: 13 }}>
            No candidates match the current filters.{" "}
            <button onClick={clearFilters} style={{
              background: "none", border: "none", color: "#818cf8",
              cursor: "pointer", fontSize: 13, padding: 0, textDecoration: "underline",
            }}>
              Clear filters
            </button>
          </div>
        )}

        {/* Table */}
        {!loading && !error && filtered.length > 0 && (
          <div style={{ overflowX: "auto", marginTop: 12 }}>
            <table style={{
              borderCollapse: "collapse", fontSize: 12,
              tableLayout: "fixed", width: "100%", minWidth: 900,
            }}>
              {/* 190+110+100+90+72+90+88+88+70+120 = 1018px */}
              <colgroup>
                <col style={{ width: 190 }} />
                <col style={{ width: 110 }} />
                <col style={{ width: 100 }} />
                <col style={{ width: 90 }} />
                <col style={{ width: 72 }} />
                <col style={{ width: 90 }} />
                <col style={{ width: 88 }} />
                <col style={{ width: 88 }} />
                <col style={{ width: 70 }} />
                <col style={{ width: 120 }} />
              </colgroup>
              <thead>
                <tr style={{ borderBottom: "2px solid rgba(255,255,255,0.1)" }}>
                  {[
                    "Candidate", "Developer", "State / County", "City",
                    "MW", "Lifecycle", "Confidence", "Status", "Sources", "Actions",
                  ].map((label, i) => (
                    <th key={label} style={{
                      padding: "9px 10px",
                      textAlign: i === 4 ? "right" as const : "left" as const,
                      fontSize: 10, fontWeight: 700,
                      textTransform: "uppercase" as const, letterSpacing: "0.08em",
                      color: "#94a3b8", whiteSpace: "nowrap" as const, overflow: "hidden",
                      position: "sticky" as const, top: 0,
                      background: "var(--bg)", zIndex: i === 9 ? 3 : 1,
                      borderBottom: "1px solid rgba(255,255,255,0.08)",
                      ...(i === 9 ? { right: 0, boxShadow: "-2px 0 6px rgba(0,0,0,0.3)" } : {}),
                    }}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(c => (
                  <CandidateRow
                    key={c.id}
                    c={c}
                    onPromote={setPromotingCandidate}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Cross-reference footer */}
        {!loading && !error && candidates.length > 0 && (
          <div style={{ marginTop: 20, fontSize: 12, color: "#64748b" }}>
            Candidates are derived from{" "}
            <a href="/discovered-sources" style={{ color: "#818cf8" }}>Discovered Sources</a>
            {" "}and{" "}
            <a href="/discovered-source-claims" style={{ color: "#818cf8" }}>Discovered Claims</a>.
            {" "}Use the Details panel to cross-reference IDs.
          </div>
        )}
      </div>
    </div>
  );
}
