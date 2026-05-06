import type { ProjectPredictionData } from "../../api/types";

const TIER_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  high:     { bg: "rgba(239,68,68,0.12)",  text: "#ef4444", border: "rgba(239,68,68,0.35)" },
  elevated: { bg: "rgba(234,179,8,0.12)",  text: "#ca8a04", border: "rgba(234,179,8,0.35)" },
  moderate: { bg: "rgba(234,179,8,0.12)",  text: "#ca8a04", border: "rgba(234,179,8,0.35)" },
  low:      { bg: "rgba(34,197,94,0.12)",  text: "#16a34a", border: "rgba(34,197,94,0.35)" },
};

const CONFIDENCE_COLORS: Record<string, string> = {
  high:   "#22c55e",
  medium: "#fbbf24",
  low:    "#f87171",
};

const DIRECTION_META: Record<string, { icon: string; color: string }> = {
  increases: { icon: "↑", color: "#ef4444" },
  decreases: { icon: "↓", color: "#22c55e" },
  unknown:   { icon: "·", color: "var(--text-dim)" },
};

const MISSING_LABELS: Record<string, string> = {
  modeled_load_mw:          "Modeled Load (MW)",
  utility_named:            "Utility Named",
  region_or_rto_named:      "Region / RTO Named",
  target_energization_date: "Target Energization Date",
  power_path_support:       "Power Path Support",
  no_phases_defined:        "No Phases Defined",
  power_path_identification: "Power Path Identification",
  utility:                  "Utility",
  region_or_rto:            "Region / RTO",
};

function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

function ProbBar({ value, color }: { value: number; color: string }) {
  const w = Math.round(value * 100);
  return (
    <div style={{ height: 6, background: "var(--border)", borderRadius: 3, overflow: "hidden", marginTop: 6 }}>
      <div style={{ width: `${w}%`, height: "100%", background: color, borderRadius: 3, transition: "width 0.4s ease" }} />
    </div>
  );
}

function Pill({ text, color, border, bg }: { text: string; color: string; border: string; bg: string }) {
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 8px",
      borderRadius: 4,
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: "0.07em",
      textTransform: "uppercase",
      background: bg,
      color,
      border: `1px solid ${border}`,
    }}>
      {text}
    </span>
  );
}

export function PredictionTab({ data }: { data: ProjectPredictionData }) {
  const tierStyle = TIER_COLORS[data.risk_tier] ?? TIER_COLORS.low;
  const confColor = CONFIDENCE_COLORS[data.confidence] ?? "var(--text-muted)";

  const horizons: { label: string; value: number }[] = [
    { label: "6-Month",  value: data.p_delay_6mo },
    { label: "12-Month", value: data.p_delay_12mo },
    { label: "18-Month", value: data.p_delay_18mo },
  ];

  const barColor = (v: number) => v >= 0.5 ? "#ef4444" : v >= 0.25 ? "#ca8a04" : "#22c55e";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* Header */}
      <div>
        <h2 style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", margin: 0, marginBottom: 4 }}>
          Delay Probability Forecast
        </h2>
        <p style={{ fontSize: 11, color: "var(--text-dim)", margin: 0 }}>
          {data.method_note}
        </p>
      </div>

      {/* Summary card */}
      <div style={{
        background: "var(--bg-surface)",
        border: `1px solid ${tierStyle.border}`,
        borderRadius: 8,
        padding: "16px 20px",
        display: "flex",
        flexDirection: "column",
        gap: 14,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <Pill text={data.risk_tier} color={tierStyle.text} border={tierStyle.border} bg={tierStyle.bg} />
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Confidence:{" "}
            <span style={{ fontWeight: 700, color: confColor }}>{data.confidence}</span>
          </span>
          <span style={{ fontSize: 11, color: "var(--text-dim)", marginLeft: "auto", fontFamily: '"JetBrains Mono", monospace' }}>
            {data.model_version}
          </span>
        </div>

        {/* Probability horizons */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 1, background: "var(--border)", border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden" }}>
          {horizons.map(h => (
            <div key={h.label} style={{ background: "var(--bg)", padding: "12px 14px" }}>
              <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", fontWeight: 600, marginBottom: 6 }}>
                {h.label}
              </div>
              <div style={{
                fontFamily: '"JetBrains Mono", monospace',
                fontSize: 22,
                fontWeight: 700,
                color: barColor(h.value),
              }}>
                {pct(h.value)}
              </div>
              <ProbBar value={h.value} color={barColor(h.value)} />
            </div>
          ))}
        </div>
      </div>

      {/* Drivers + Missing inputs */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>

        {/* Drivers */}
        <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "14px 16px" }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700, color: "var(--text-dim)", marginBottom: 10 }}>
            Risk Drivers ({data.drivers.length})
          </div>
          {data.drivers.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>No drivers identified.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {data.drivers.map((d, i) => {
                const dirKey = d.direction.replace("s_risk", "").replace("s", "");
                const meta = DIRECTION_META[dirKey] ?? DIRECTION_META.unknown;
                return (
                  <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                    <span style={{ color: meta.color, fontSize: 13, fontWeight: 700, lineHeight: "18px", flexShrink: 0, width: 14, textAlign: "center" }}>
                      {meta.icon}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, color: "var(--text)", lineHeight: "18px" }}>
                        {d.driver}
                      </div>
                      {d.weight !== 0 && (
                        <div style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 10, color: "var(--text-dim)", marginTop: 1 }}>
                          weight {d.weight > 0 ? "+" : ""}{d.weight.toFixed(3)}
                        </div>
                      )}
                      {d.evidence && (
                        <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2, lineHeight: "15px" }}>
                          {d.evidence}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Missing inputs */}
        <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "14px 16px" }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700, color: "var(--text-dim)", marginBottom: 10 }}>
            Missing Inputs ({data.missing_inputs.length})
          </div>
          {data.missing_inputs.length === 0 ? (
            <div style={{ fontSize: 12, color: "#22c55e" }}>All key inputs are present.</div>
          ) : (
            <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 7 }}>
              {data.missing_inputs.map((m, i) => (
                <li key={i} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span style={{ color: "#ca8a04", fontSize: 13, flexShrink: 0 }}>⚠</span>
                  <span style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 11, color: "var(--text-muted)" }}>
                    {MISSING_LABELS[m] ?? m}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

      </div>

    </div>
  );
}
