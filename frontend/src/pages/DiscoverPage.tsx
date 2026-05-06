import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import type { DiscoveredSource, ManualCapture } from "../api/types";
import {
  getDiscoveredSources,
  getDiscoverDecisions,
  postDiscoverDecisions,
  getManualCaptures,
  postManualCapture,
} from "../api/adapter";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Decision     = "approved" | "rejected";
type StatusFilter = "all" | "pending" | "approved" | "rejected";
type SaveState    = "idle" | "saving" | "saved" | "error";

interface ModalState {
  source: DiscoveredSource;
  existing: ManualCapture | null;
}

// ---------------------------------------------------------------------------
// Constants — flags that indicate manual capture is needed
// ---------------------------------------------------------------------------

const BLOCKED_KEYWORDS = [
  "robots_check_failed",
  "fetch_failed",
  "curl_fallback_failed",
  "CERTIFICATE",
  "SSL",
];

function needsManualCapture(source: DiscoveredSource): boolean {
  if (!source.extracted_text) return true;
  const reason = source.requires_review_reason ?? "";
  return BLOCKED_KEYWORDS.some(kw => reason.includes(kw));
}

// ---------------------------------------------------------------------------
// Style constants
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

function formatDate(iso: string | null | undefined): string {
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

function decisionsToSets(decisions: Record<string, Decision>) {
  const approved: string[] = [];
  const rejected: string[] = [];
  for (const [id, dec] of Object.entries(decisions)) {
    if (dec === "approved") approved.push(id);
    else rejected.push(id);
  }
  return { approved, rejected };
}

// ---------------------------------------------------------------------------
// Small shared components
// ---------------------------------------------------------------------------

function Badge({ label, color, bg }: { label: string; color: string; bg: string }) {
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

function SaveIndicator({ state, updatedAt }: { state: SaveState; updatedAt: string | null }) {
  if (state === "idle" && !updatedAt) return null;
  if (state === "saving") {
    return (
      <span style={{ fontSize: 11, color: "var(--text-dim)", display: "flex", alignItems: "center", gap: 4 }}>
        <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "#f59e0b" }} />
        Saving…
      </span>
    );
  }
  if (state === "error") {
    return <span style={{ fontSize: 11, color: "#ef4444" }}>Save failed — check backend connection</span>;
  }
  return (
    <span style={{ fontSize: 11, color: "#22c55e" }}>
      ✓ Decisions saved{updatedAt ? ` · ${formatDate(updatedAt)}` : ""}
    </span>
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

// ---------------------------------------------------------------------------
// Manual Capture Modal
// ---------------------------------------------------------------------------

function ManualCaptureModal({
  source,
  existing,
  onSave,
  onClose,
}: {
  source: DiscoveredSource;
  existing: ManualCapture | null;
  onSave: (capture: ManualCapture) => void;
  onClose: () => void;
}) {
  const [text, setText]         = useState(existing?.manual_extracted_text ?? "");
  const [date, setDate]         = useState(existing?.source_date ?? source.source_date ?? "");
  const [notes, setNotes]       = useState(existing?.notes ?? "");
  const [latStr, setLatStr]     = useState(existing?.latitude != null ? String(existing.latitude) : "");
  const [lonStr, setLonStr]     = useState(existing?.longitude != null ? String(existing.longitude) : "");
  const [coordSource, setCoordSource]       = useState(existing?.coordinate_source ?? "");
  const [coordConfidence, setCoordConfidence] = useState(existing?.coordinate_confidence ?? "");
  const [saving, setSaving]     = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const textareaRef             = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handleSave() {
    if (!text.trim()) { setError("Please paste the text before saving."); return; }
    const lat = latStr.trim() !== "" ? parseFloat(latStr) : undefined;
    const lon = lonStr.trim() !== "" ? parseFloat(lonStr) : undefined;
    if (lat !== undefined && (isNaN(lat) || lat < -90 || lat > 90)) {
      setError("Latitude must be a number between -90 and 90."); return;
    }
    if (lon !== undefined && (isNaN(lon) || lon < -180 || lon > 180)) {
      setError("Longitude must be a number between -180 and 180."); return;
    }
    setSaving(true);
    setError(null);
    try {
      const result = await postManualCapture({
        discovery_id: source.discovery_id,
        manual_extracted_text: text.trim(),
        source_date: date.trim(),
        notes: notes.trim(),
        captured_by: "analyst",
        latitude: lat ?? null,
        longitude: lon ?? null,
        coordinate_source: coordSource.trim(),
        coordinate_confidence: coordConfidence.trim(),
      });
      onSave(result);
    } catch (e) {
      setError(String(e));
      setSaving(false);
    }
  }

  return (
    <div
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: "fixed", inset: 0, zIndex: 1000,
        background: "rgba(0,0,0,0.65)", display: "flex",
        alignItems: "center", justifyContent: "center",
        padding: "20px",
      }}
    >
      <div style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        width: "100%", maxWidth: 640,
        maxHeight: "90vh",
        display: "flex", flexDirection: "column",
        boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
      }}>

        {/* Modal header */}
        <div style={{
          padding: "16px 20px 12px",
          borderBottom: "1px solid var(--border)",
          display: "flex", alignItems: "flex-start", gap: 12,
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", marginBottom: 3 }}>
              {existing ? "Edit Manual Text" : "Add Manual Text"}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.4 }}>
              {source.candidate_project_name || "—"}
              {source.developer ? <span style={{ color: "var(--text-dim)" }}> · {source.developer}</span> : null}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none", border: "none", cursor: "pointer",
              color: "var(--text-dim)", fontSize: 18, lineHeight: 1,
              padding: "2px 4px", borderRadius: 3,
            }}
          >
            ×
          </button>
        </div>

        {/* Source info */}
        <div style={{
          padding: "12px 20px",
          borderBottom: "1px solid var(--border)",
          background: "rgba(0,0,0,0.15)",
        }}>
          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <div style={{ flex: 1 }}>
              {source.title && (
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4, lineHeight: 1.4 }}>
                  <span style={{ color: "var(--text-dim)", fontSize: 10 }}>Title </span>
                  {truncate(source.title, 100)}
                </div>
              )}
              {source.source_url && (
                <div style={{ fontSize: 11 }}>
                  <span style={{ color: "var(--text-dim)", fontSize: 10 }}>URL </span>
                  <a
                    href={source.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: "var(--accent)", textDecoration: "none", wordBreak: "break-all" }}
                  >
                    {source.source_url.length > 80 ? source.source_url.slice(0, 80) + "…" : source.source_url}
                  </a>
                </div>
              )}
            </div>
            {source.source_url && (
              <a
                href={source.source_url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  fontSize: 11, fontWeight: 600, padding: "5px 12px",
                  borderRadius: 4, border: "1px solid var(--accent)",
                  color: "var(--accent)", textDecoration: "none", whiteSpace: "nowrap",
                  flexShrink: 0,
                }}
              >
                ↗ Open source
              </a>
            )}
          </div>

          {source.requires_review_reason && (
            <div style={{
              marginTop: 8, fontSize: 10, color: "#f59e0b",
              background: "rgba(245,158,11,0.08)", borderRadius: 3,
              padding: "4px 8px", lineHeight: 1.5,
            }}>
              <span style={{ fontWeight: 700 }}>Blocked reason: </span>
              {source.requires_review_reason}
            </div>
          )}
        </div>

        {/* Scrollable body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>

          <label style={{ display: "block", marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", marginBottom: 5 }}>
              Paste text from source
              <span style={{ fontWeight: 400, color: "var(--text-dim)", marginLeft: 6 }}>
                — open the link above in your browser, select and copy the relevant content, then paste here
              </span>
            </div>
            <textarea
              ref={textareaRef}
              value={text}
              onChange={e => setText(e.target.value)}
              placeholder="Paste article text, document excerpt, or press release content here…"
              rows={10}
              style={{
                width: "100%", resize: "vertical",
                background: "var(--bg)", border: "1px solid var(--border)",
                borderRadius: 4, padding: "8px 10px",
                fontSize: 12, color: "var(--text)", lineHeight: 1.6,
                fontFamily: "inherit",
                boxSizing: "border-box",
              }}
            />
            <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 3 }}>
              {text.trim().length} characters
            </div>
          </label>

          <div style={{ display: "flex", gap: 12 }}>
            <label style={{ flex: 1 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", marginBottom: 5 }}>
                Source date override
                <span style={{ fontWeight: 400, color: "var(--text-dim)", marginLeft: 4 }}>(optional, YYYY-MM-DD)</span>
              </div>
              <input
                type="text"
                value={date}
                onChange={e => setDate(e.target.value)}
                placeholder="e.g. 2025-03-15"
                style={{
                  width: "100%", boxSizing: "border-box",
                  background: "var(--bg)", border: "1px solid var(--border)",
                  borderRadius: 4, padding: "6px 10px",
                  fontSize: 12, color: "var(--text)",
                }}
              />
            </label>
          </div>

          {/* ── Coordinates ── */}
          <div style={{ marginTop: 14, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Coordinates
              <span style={{ fontWeight: 400, color: "var(--text-dim)", marginLeft: 6, textTransform: "none", letterSpacing: 0 }}>
                — optional, stored with the capture for later ingest
              </span>
            </div>
            <div style={{ display: "flex", gap: 10, marginBottom: 8 }}>
              <label style={{ flex: 1 }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text-dim)", marginBottom: 4 }}>Latitude</div>
                <input
                  type="number"
                  value={latStr}
                  onChange={e => setLatStr(e.target.value)}
                  placeholder="e.g. 33.749"
                  step="any"
                  style={{
                    width: "100%", boxSizing: "border-box",
                    background: "var(--bg)", border: "1px solid var(--border)",
                    borderRadius: 4, padding: "6px 10px",
                    fontSize: 12, color: "var(--text)",
                  }}
                />
              </label>
              <label style={{ flex: 1 }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text-dim)", marginBottom: 4 }}>Longitude</div>
                <input
                  type="number"
                  value={lonStr}
                  onChange={e => setLonStr(e.target.value)}
                  placeholder="e.g. -84.388"
                  step="any"
                  style={{
                    width: "100%", boxSizing: "border-box",
                    background: "var(--bg)", border: "1px solid var(--border)",
                    borderRadius: 4, padding: "6px 10px",
                    fontSize: 12, color: "var(--text)",
                  }}
                />
              </label>
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <label style={{ flex: 1 }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text-dim)", marginBottom: 4 }}>Coordinate source</div>
                <input
                  type="text"
                  value={coordSource}
                  onChange={e => setCoordSource(e.target.value)}
                  placeholder="e.g. county parcel map, Google Maps"
                  style={{
                    width: "100%", boxSizing: "border-box",
                    background: "var(--bg)", border: "1px solid var(--border)",
                    borderRadius: 4, padding: "6px 10px",
                    fontSize: 12, color: "var(--text)",
                  }}
                />
              </label>
              <label style={{ flex: 1 }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text-dim)", marginBottom: 4 }}>Confidence</div>
                <select
                  value={coordConfidence}
                  onChange={e => setCoordConfidence(e.target.value)}
                  style={{
                    width: "100%", boxSizing: "border-box",
                    background: "var(--bg)", border: "1px solid var(--border)",
                    borderRadius: 4, padding: "6px 10px",
                    fontSize: 12, color: coordConfidence ? "var(--text)" : "var(--text-dim)",
                    cursor: "pointer",
                  }}
                >
                  <option value="">— select —</option>
                  <option value="parcel">Parcel (high)</option>
                  <option value="city">City centroid</option>
                  <option value="county">County centroid</option>
                  <option value="inferred">Inferred</option>
                </select>
              </label>
            </div>
          </div>

          <label style={{ display: "block", marginTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", marginBottom: 5 }}>
              Notes
              <span style={{ fontWeight: 400, color: "var(--text-dim)", marginLeft: 4 }}>(optional)</span>
            </div>
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="e.g. copied from page 3 of the PDF; article paywall bypassed via web archive"
              rows={2}
              style={{
                width: "100%", resize: "vertical",
                background: "var(--bg)", border: "1px solid var(--border)",
                borderRadius: 4, padding: "6px 10px",
                fontSize: 12, color: "var(--text)", lineHeight: 1.5,
                fontFamily: "inherit",
                boxSizing: "border-box",
              }}
            />
          </label>

          {existing && (
            <div style={{
              marginTop: 10, fontSize: 10, color: "var(--text-dim)",
              background: "rgba(34,197,94,0.06)", borderRadius: 3, padding: "5px 8px",
              border: "1px solid rgba(34,197,94,0.15)",
            }}>
              Previously captured {formatDate(existing.captured_at)} by {existing.captured_by}.
              Saving will overwrite the existing capture.
            </div>
          )}

          {error && (
            <div style={{ marginTop: 10, fontSize: 11, color: "#ef4444", background: "rgba(239,68,68,0.08)", borderRadius: 3, padding: "6px 10px" }}>
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: "12px 20px",
          borderTop: "1px solid var(--border)",
          display: "flex", gap: 10, justifyContent: "flex-end",
          background: "rgba(0,0,0,0.1)",
        }}>
          <button
            onClick={onClose}
            style={{
              fontSize: 12, padding: "6px 16px", borderRadius: 4,
              background: "transparent", border: "1px solid var(--border)",
              color: "var(--text-muted)", cursor: "pointer",
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !text.trim()}
            style={{
              fontSize: 12, fontWeight: 600, padding: "6px 18px", borderRadius: 4,
              background: saving || !text.trim() ? "rgba(34,197,94,0.3)" : "rgba(34,197,94,0.15)",
              border: "1px solid rgba(34,197,94,0.5)", color: "#22c55e",
              cursor: saving || !text.trim() ? "default" : "pointer",
            }}
          >
            {saving ? "Saving…" : existing ? "Update capture" : "Save capture"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Source card
// ---------------------------------------------------------------------------

function SourceCard({
  source, decision, capture, saving, onApprove, onReject, onUndo, onAddManual,
}: {
  source: DiscoveredSource;
  decision: Decision | undefined;
  capture: ManualCapture | null;
  saving: boolean;
  onApprove: () => void;
  onReject: () => void;
  onUndo: () => void;
  onAddManual: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const status: "pending" | "approved" | "rejected" = decision ?? "pending";
  const confColor = CONF_COLOR[source.confidence] ?? "#94a3b8";
  const confBg    = CONF_BG[source.confidence]    ?? "rgba(148,163,184,0.1)";
  const needsManual = needsManualCapture(source);

  const borderColor = status === "approved"
    ? "rgba(34,197,94,0.35)"
    : status === "rejected"
    ? "rgba(239,68,68,0.25)"
    : "var(--border)";

  // Preview: use manual text if extracted_text is missing
  const displayText = source.extracted_text || capture?.manual_extracted_text || "";

  return (
    <div style={{
      border: `1px solid ${borderColor}`,
      borderRadius: 6,
      background: "var(--bg-surface)",
      padding: "14px 16px",
      marginBottom: 10,
      transition: "border-color 0.15s",
      opacity: saving ? 0.7 : 1,
    }}>
      {/* ── Top row: badges + status + actions ── */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", flex: 1 }}>
          <Badge
            label={source.confidence ? `Confidence: ${source.confidence}` : "Confidence: —"}
            color={confColor} bg={confBg}
          />
          <Badge
            label={SOURCE_TYPE_LABEL[source.source_type] ?? source.source_type}
            color="#94a3b8" bg="rgba(148,163,184,0.08)"
          />
          <Badge
            label={source.discovery_method.replace(/_/g, " ")}
            color="#60a5fa" bg="rgba(96,165,250,0.08)"
          />
          {capture && (
            <Badge label="Manual text added" color="#a78bfa" bg="rgba(167,139,250,0.12)" />
          )}
          {needsManual && !capture && (
            <Badge label="Text blocked" color="#f59e0b" bg="rgba(245,158,11,0.1)" />
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0, flexWrap: "wrap" }}>
          <StatusBadge status={status} />

          {decision ? (
            <button
              onClick={onUndo}
              disabled={saving}
              style={{
                fontSize: 11, padding: "3px 10px", borderRadius: 4,
                cursor: saving ? "default" : "pointer",
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
                disabled={saving}
                style={{
                  fontSize: 11, fontWeight: 600, padding: "3px 12px", borderRadius: 4,
                  cursor: saving ? "default" : "pointer",
                  background: "rgba(34,197,94,0.1)",
                  border: "1px solid rgba(34,197,94,0.45)", color: "#22c55e",
                }}
              >
                Approve
              </button>
              <button
                onClick={onReject}
                disabled={saving}
                style={{
                  fontSize: 11, fontWeight: 600, padding: "3px 12px", borderRadius: 4,
                  cursor: saving ? "default" : "pointer",
                  background: "rgba(239,68,68,0.08)",
                  border: "1px solid rgba(239,68,68,0.35)", color: "#ef4444",
                }}
              >
                Reject
              </button>
            </>
          )}

          {/* Add / Edit manual text button — shown when fetch was blocked or text is missing */}
          {needsManual && (
            <button
              onClick={onAddManual}
              style={{
                fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 4,
                cursor: "pointer",
                background: capture
                  ? "rgba(167,139,250,0.12)"
                  : "rgba(245,158,11,0.1)",
                border: capture
                  ? "1px solid rgba(167,139,250,0.4)"
                  : "1px solid rgba(245,158,11,0.4)",
                color: capture ? "#a78bfa" : "#f59e0b",
                whiteSpace: "nowrap",
              }}
            >
              {capture ? "✎ Edit text" : "+ Add Manual Text"}
            </button>
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

      {/* ── Detected facts ── */}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 8 }}>
        <Fact label="Load"        value={source.detected_load_mw != null ? `${source.detected_load_mw.toLocaleString()} MW` : "—"} />
        <Fact label="Region"      value={source.detected_region  || "—"} />
        <Fact label="Utility"     value={source.detected_utility || "—"} />
        <Fact label="Source date" value={capture?.source_date || source.source_date || "—"} />
      </div>

      {/* ── Source title ── */}
      {source.title && (
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6, lineHeight: 1.4 }}>
          <span style={{ color: "var(--text-dim)", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Title{" "}
          </span>
          {source.source_url ? (
            <a href={source.source_url} target="_blank" rel="noopener noreferrer"
              style={{ color: "var(--accent)", textDecoration: "none" }}>
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

      {/* ── Manual text + coordinate preview ── */}
      {capture && (
        <div style={{
          marginBottom: 6,
          background: "rgba(167,139,250,0.06)",
          border: "1px solid rgba(167,139,250,0.2)",
          borderRadius: 4, padding: "7px 10px",
        }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", color: "#a78bfa", marginBottom: 3, fontWeight: 700 }}>
            Manual text preview
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5 }}>
            {truncate(capture.manual_extracted_text, 220)}
          </div>
          {capture.latitude != null && capture.longitude != null && (
            <div style={{ fontSize: 10, color: "#a78bfa", marginTop: 5, fontFamily: "monospace" }}>
              📍 {capture.latitude.toFixed(5)}, {capture.longitude.toFixed(5)}
              {capture.coordinate_confidence && (
                <span style={{ color: "var(--text-dim)", marginLeft: 6, fontFamily: "inherit" }}>
                  · {capture.coordinate_confidence}
                </span>
              )}
            </div>
          )}
          {capture.notes && (
            <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 4 }}>
              Notes: {capture.notes}
            </div>
          )}
          <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 3 }}>
            Captured {formatDate(capture.captured_at)} by {capture.captured_by}
          </div>
        </div>
      )}

      {/* ── Extracted text preview (when available from fetch) ── */}
      {!capture && displayText && (
        <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6, lineHeight: 1.5 }}>
          <span style={{ color: "var(--text-dim)", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Text preview{" "}
          </span>
          {expanded ? displayText : truncate(displayText, 200)}
          {displayText.length > 200 && (
            <button
              onClick={() => setExpanded(e => !e)}
              style={{ fontSize: 10, color: "var(--accent)", background: "none", border: "none", cursor: "pointer", padding: "0 4px" }}
            >
              {expanded ? "less" : "more"}
            </button>
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
            {expanded ? source.requires_review_reason : truncate(source.requires_review_reason, 100)}
          </span>
          {source.requires_review_reason.length > 100 && (
            <button
              onClick={() => setExpanded(e => !e)}
              style={{ fontSize: 10, color: "var(--accent)", background: "none", border: "none", cursor: "pointer", padding: "0 4px" }}
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

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function DiscoverPage() {
  const [sources,   setSources]   = useState<DiscoveredSource[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [captures,  setCaptures]  = useState<Record<string, ManualCapture>>({});
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [modal,     setModal]     = useState<ModalState | null>(null);
  const savedTimerRef             = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Filters
  const [filterStatus,     setFilterStatus]     = useState<StatusFilter>("all");
  const [filterConfidence, setFilterConfidence] = useState("all");
  const [filterState,      setFilterState]      = useState("all");
  const [filterManual,     setFilterManual]      = useState(false);
  const [search,           setSearch]           = useState("");

  // Load sources + decisions + manual captures in parallel on mount
  useEffect(() => {
    setLoading(true);
    Promise.all([
      getDiscoveredSources(),
      getDiscoverDecisions(),
      getManualCaptures(),
    ])
      .then(([srcs, dec, man]) => {
        setSources(srcs);
        const hydrated: Record<string, Decision> = {};
        for (const id of dec.approved) hydrated[id] = "approved";
        for (const id of dec.rejected) hydrated[id] = "rejected";
        setDecisions(hydrated);
        setUpdatedAt(dec.updated_at);
        const cap: Record<string, ManualCapture> = {};
        for (const c of man.captures) cap[c.discovery_id] = c;
        setCaptures(cap);
        setLoading(false);
      })
      .catch(e => { setError(String(e)); setLoading(false); });
  }, []);

  // Save decisions
  const saveDecisions = useCallback(async (next: Record<string, Decision>) => {
    setSaveState("saving");
    if (savedTimerRef.current) clearTimeout(savedTimerRef.current);
    try {
      const { approved, rejected } = decisionsToSets(next);
      const result = await postDiscoverDecisions(approved, rejected);
      setUpdatedAt(result.updated_at);
      setSaveState("saved");
      savedTimerRef.current = setTimeout(() => setSaveState("idle"), 3000);
    } catch {
      setSaveState("error");
    }
  }, []);

  const makeDecision = useCallback(async (id: string, dec: Decision | null) => {
    const next = { ...decisions };
    if (dec === null) delete next[id]; else next[id] = dec;
    setDecisions(next);
    await saveDecisions(next);
  }, [decisions, saveDecisions]);

  const approve = useCallback((id: string) => makeDecision(id, "approved"), [makeDecision]);
  const reject  = useCallback((id: string) => makeDecision(id, "rejected"),  [makeDecision]);
  const undo    = useCallback((id: string) => makeDecision(id, null),         [makeDecision]);

  const handleManualSave = useCallback((capture: ManualCapture) => {
    setCaptures(prev => ({ ...prev, [capture.discovery_id]: capture }));
    setModal(null);
  }, []);

  const openModal = useCallback((source: DiscoveredSource) => {
    setModal({ source, existing: captures[source.discovery_id] ?? null });
  }, [captures]);

  const allStates = useMemo(
    () => [...new Set(sources.map(s => s.state).filter(Boolean))].sort(),
    [sources],
  );

  const isSaving = saveState === "saving";

  const filtered = useMemo(() => sources.filter(s => {
    const dec = decisions[s.discovery_id];
    const status = dec ?? "pending";
    if (filterStatus !== "all" && status !== filterStatus) return false;
    if (filterConfidence !== "all" && s.confidence !== filterConfidence) return false;
    if (filterState !== "all" && s.state !== filterState) return false;
    if (filterManual && !needsManualCapture(s)) return false;
    if (search) {
      const q = search.toLowerCase();
      if (
        !s.candidate_project_name.toLowerCase().includes(q) &&
        !s.developer.toLowerCase().includes(q) &&
        !s.title.toLowerCase().includes(q)
      ) return false;
    }
    return true;
  }), [sources, decisions, filterStatus, filterConfidence, filterState, filterManual, search]);

  const pendingCount    = sources.filter(s => !decisions[s.discovery_id]).length;
  const approvedCount   = Object.values(decisions).filter(d => d === "approved").length;
  const rejectedCount   = Object.values(decisions).filter(d => d === "rejected").length;
  const capturedCount   = Object.keys(captures).length;
  const blockedCount    = sources.filter(needsManualCapture).length;

  const sel: React.CSSProperties = {
    padding: "5px 8px", fontSize: 11, background: "var(--bg)", border: "1px solid var(--border)",
    borderRadius: 4, color: "var(--text)", cursor: "pointer",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>

      {/* Modal */}
      {modal && (
        <ManualCaptureModal
          source={modal.source}
          existing={modal.existing}
          onSave={handleManualSave}
          onClose={() => setModal(null)}
        />
      )}

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

        <div style={{ marginLeft: 8 }}>
          <SaveIndicator state={saveState} updatedAt={updatedAt} />
        </div>

        {!loading && !error && sources.length > 0 && (
          <div style={{ marginLeft: "auto", display: "flex", gap: 16, alignItems: "center" }}>
            <CountPill label="Total"    value={sources.length}  color="var(--text-muted)" />
            <CountPill label="Pending"  value={pendingCount}    color="#94a3b8" />
            <CountPill label="Approved" value={approvedCount}   color="#22c55e" />
            <CountPill label="Rejected" value={rejectedCount}   color="#ef4444" />
            <CountPill label="Blocked"  value={blockedCount}    color="#f59e0b" />
            <CountPill label="Captured" value={capturedCount}   color="#a78bfa" />
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
          {/* Status tabs */}
          <div style={{ display: "flex", border: "1px solid var(--border)", borderRadius: 4, overflow: "hidden" }}>
            {STATUS_FILTER_LABELS.map(({ value, label }) => {
              const active = filterStatus === value;
              return (
                <button key={value} onClick={() => setFilterStatus(value)} style={{
                  fontSize: 11, fontWeight: active ? 700 : 400, padding: "4px 12px", cursor: "pointer",
                  background: active ? "var(--accent)" : "transparent",
                  color: active ? "#fff" : "var(--text-muted)",
                  border: "none", borderRight: "1px solid var(--border)",
                }}>
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

          <button
            onClick={() => setFilterManual(b => !b)}
            style={{
              ...sel,
              background: filterManual ? "rgba(245,158,11,0.15)" : "var(--bg)",
              border: filterManual ? "1px solid rgba(245,158,11,0.5)" : "1px solid var(--border)",
              color: filterManual ? "#f59e0b" : "var(--text-muted)",
              fontWeight: filterManual ? 700 : 400,
              cursor: "pointer",
            }}
          >
            {filterManual ? "⚠ Blocked only" : "All sources"}
          </button>

          <input
            type="text"
            placeholder="Search name, developer, title…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ ...sel, width: 220, cursor: "text" }}
          />

          {(filterStatus !== "all" || filterConfidence !== "all" || filterState !== "all" || filterManual || search) && (
            <button
              onClick={() => { setFilterStatus("all"); setFilterConfidence("all"); setFilterState("all"); setFilterManual(false); setSearch(""); }}
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
            <div style={{ fontSize: 11, marginTop: 8 }}>
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
              No discovered sources yet. Run discovery first.
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
            capture={captures[source.discovery_id] ?? null}
            saving={isSaving}
            onApprove={() => approve(source.discovery_id)}
            onReject={()  => reject(source.discovery_id)}
            onUndo={()    => undo(source.discovery_id)}
            onAddManual={() => openModal(source)}
          />
        ))}
      </div>
    </div>
  );
}
