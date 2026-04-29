import type { ProjectRiskSignalData } from "../../api/types";

const TIER_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  high:     { bg: "rgba(239,68,68,0.12)",  text: "#ef4444", border: "rgba(239,68,68,0.35)" },
  moderate: { bg: "rgba(234,179,8,0.12)",  text: "#ca8a04", border: "rgba(234,179,8,0.35)" },
  low:      { bg: "rgba(34,197,94,0.12)",  text: "#16a34a", border: "rgba(34,197,94,0.35)" },
};

const SIGNAL_LABELS: Record<string, string> = {
  power_path_underresolved:      "Power Path Underresolved",
  capacity_timing_tension:       "Capacity / Timing Tension",
  power_path_partially_resolved: "Power Path Partially Resolved",
  power_path_more_resolved:      "Power Path More Resolved",
};

const FIELD_LABELS: Record<string, string> = {
  utility_named:            "Utility Named",
  region_or_rto_named:      "Region / RTO Named",
  target_energization_date: "Target Energization Date",
  power_path_support:       "Power Path Support",
  modeled_load_mw:          "Modeled Load (MW)",
  optional_expansion_mw:    "Optional Expansion (MW)",
};

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color = score >= 0.55 ? "#ef4444" : score >= 0.25 ? "#ca8a04" : "#16a34a";
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600 }}>
          Risk Signal Score
        </span>
        <span style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 14, fontWeight: 700, color }}>
          {pct}
        </span>
      </div>
      <div style={{ height: 6, background: "var(--border)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 3, transition: "width 0.4s ease" }} />
      </div>
    </div>
  );
}

function Pill({ text, color }: { text: string; color: string }) {
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 8px",
      borderRadius: 4,
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: "0.07em",
      textTransform: "uppercase",
      background: color === "#ef4444" ? "rgba(239,68,68,0.12)" : color === "#ca8a04" ? "rgba(234,179,8,0.12)" : "rgba(34,197,94,0.12)",
      color,
      border: `1px solid ${color === "#ef4444" ? "rgba(239,68,68,0.35)" : color === "#ca8a04" ? "rgba(234,179,8,0.35)" : "rgba(34,197,94,0.35)"}`,
    }}>
      {text}
    </span>
  );
}

export function RiskSignalTab({ data }: { data: ProjectRiskSignalData }) {
  const tierStyle = TIER_COLORS[data.risk_signal_tier] ?? TIER_COLORS.low;
  const tierColor = tierStyle.text;
  const signalLabel = SIGNAL_LABELS[data.risk_signal] ?? data.risk_signal;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* Section header */}
      <div>
        <h2 style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", margin: 0, marginBottom: 4 }}>
          Evidence-Based Risk Signal
        </h2>
        <p style={{ fontSize: 11, color: "var(--text-dim)", margin: 0 }}>
          Scores accepted evidence records and claims about the power path. Independent of the ML model score shown on the Score tab.
        </p>
      </div>

      {/* Header card */}
      <div style={{
        background: "var(--bg-surface)",
        border: `1px solid ${tierStyle.border}`,
        borderRadius: 8,
        padding: "16px 20px",
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Pill text={data.risk_signal_tier} color={tierColor} />
          <span style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 14, fontWeight: 700, color: "var(--text)" }}>
            {signalLabel}
          </span>
        </div>
        <ScoreBar score={data.risk_signal_score} />
        <div style={{ fontSize: 10, color: "var(--text-dim)", letterSpacing: "0.05em" }}>
          Method: {data.method}
        </div>
      </div>

      {/* Two-column detail */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>

        {/* Drivers */}
        <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "14px 16px" }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700, color: "var(--text-dim)", marginBottom: 10 }}>
            Risk Drivers ({data.drivers.length})
          </div>
          {data.drivers.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>No drivers identified.</div>
          ) : (
            <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 6 }}>
              {data.drivers.map((d, i) => (
                <li key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                  <span style={{ color: "#ef4444", fontSize: 13, lineHeight: "18px", flexShrink: 0 }}>›</span>
                  <span style={{ fontSize: 12, color: "var(--text)", lineHeight: "18px" }}>{d}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Missing fields */}
        <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "14px 16px" }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700, color: "var(--text-dim)", marginBottom: 10 }}>
            Missing Fields ({data.missing_fields.length})
          </div>
          {data.missing_fields.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>All key fields are present.</div>
          ) : (
            <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 6 }}>
              {data.missing_fields.map((f, i) => (
                <li key={i} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span style={{ color: "#ca8a04", fontSize: 13, flexShrink: 0 }}>⚠</span>
                  <span style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 11, color: "var(--text-muted)" }}>
                    {FIELD_LABELS[f] ?? f}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Evidence summary */}
      <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "14px 16px" }}>
        <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700, color: "var(--text-dim)", marginBottom: 10 }}>
          Evidence Summary
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 1, background: "var(--border)", border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden" }}>
          {[
            { label: "Evidence Records", value: data.evidence_summary.evidence_count },
            { label: "Accepted Claims",  value: data.evidence_summary.accepted_claim_count },
            { label: "Unresolved Claims", value: data.evidence_summary.unresolved_claim_count, warn: data.evidence_summary.unresolved_claim_count > 0 },
          ].map(item => (
            <div key={item.label} style={{ background: "var(--bg)", padding: "12px 14px" }}>
              <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", fontWeight: 600, marginBottom: 4 }}>
                {item.label}
              </div>
              <div style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 20, fontWeight: 700, color: item.warn ? "#ca8a04" : "var(--text)" }}>
                {item.value}
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
