import { useEffect, useState } from "react";
import type { ProjectPredictionData } from "../../api/types";
import { getProjectPrediction } from "../../api/adapter";

const TIER_COLOR: Record<string, string> = {
  high:     "#ef4444",
  elevated: "#f59e0b",
  medium:   "#f59e0b",
  low:      "#22c55e",
};

const DIRECTION_ICON: Record<string, string> = {
  increases: "↑",
  decreases: "↓",
  unknown:   "·",
};

const DIRECTION_COLOR: Record<string, string> = {
  increases: "#ef4444",
  decreases: "#22c55e",
  unknown:   "#64748b",
};

function pct(v: number) {
  return `${(v * 100).toFixed(1)}%`;
}

function probColor(v: number) {
  if (v >= 0.5) return "#ef4444";
  if (v >= 0.25) return "#f59e0b";
  return "#22c55e";
}

interface Props {
  projectId: string;
}

export function PredictionSummary({ projectId }: Props) {
  const [data, setData] = useState<ProjectPredictionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setData(null);
    getProjectPrediction(projectId)
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [projectId]);

  const divider: React.CSSProperties = {
    borderTop: "1px solid #2d3748",
    margin: "8px 0",
  };

  const sectionLabel: React.CSSProperties = {
    fontSize: 9,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.09em",
    color: "#475569",
    marginBottom: 6,
  };

  if (loading) {
    return (
      <>
        <div style={divider} />
        <div style={sectionLabel}>Prediction</div>
        <div style={{ fontSize: 11, color: "#64748b", fontStyle: "italic" }}>
          Loading prediction…
        </div>
      </>
    );
  }

  if (error || !data) {
    return (
      <>
        <div style={divider} />
        <div style={sectionLabel}>Prediction</div>
        <div style={{ fontSize: 11, color: "#64748b", fontStyle: "italic" }}>
          Prediction unavailable
        </div>
      </>
    );
  }

  const tierColor = TIER_COLOR[data.risk_tier] ?? "#94a3b8";
  const topDrivers = data.drivers.slice(0, 3);

  return (
    <>
      <div style={divider} />

      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={sectionLabel}>Prediction</div>
        <span style={{
          display: "inline-block",
          padding: "1px 6px",
          borderRadius: 3,
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: "0.07em",
          textTransform: "uppercase",
          background: `${tierColor}22`,
          color: tierColor,
          border: `1px solid ${tierColor}55`,
        }}>
          {data.risk_tier}
        </span>
      </div>

      {/* Delay probabilities */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr 1fr",
        gap: 1,
        background: "#1a2035",
        border: "1px solid #2d3748",
        borderRadius: 4,
        overflow: "hidden",
        marginBottom: 8,
      }}>
        {([
          { label: "6 mo",  value: data.p_delay_6mo },
          { label: "12 mo", value: data.p_delay_12mo },
          { label: "18 mo", value: data.p_delay_18mo },
        ] as const).map(h => (
          <div key={h.label} style={{ background: "#0f1729", padding: "5px 6px" }}>
            <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>
              {h.label}
            </div>
            <div style={{ fontSize: 14, fontWeight: 700, color: probColor(h.value), fontFamily: "monospace" }}>
              {pct(h.value)}
            </div>
          </div>
        ))}
      </div>

      {/* Confidence + model */}
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={{ fontSize: 10, color: "#64748b" }}>
          Confidence:{" "}
          <span style={{ fontWeight: 700, color: "#94a3b8" }}>{data.confidence}</span>
        </div>
        <div style={{ fontSize: 9, color: "#475569", fontFamily: "monospace" }}>
          {data.model_version}
        </div>
      </div>

      {/* Top drivers */}
      {topDrivers.length > 0 && (
        <div style={{ marginBottom: 6 }}>
          <div style={{ ...sectionLabel, marginBottom: 4 }}>Top drivers</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {topDrivers.map((d, i) => {
              const icon = DIRECTION_ICON[d.direction] ?? "·";
              const iconColor = DIRECTION_COLOR[d.direction] ?? "#64748b";
              return (
                <div key={i} style={{ display: "flex", gap: 5, alignItems: "flex-start" }}>
                  <span style={{ color: iconColor, fontSize: 11, fontWeight: 700, flexShrink: 0, width: 10, textAlign: "center", lineHeight: "15px" }}>
                    {icon}
                  </span>
                  <span style={{ fontSize: 10, color: "#94a3b8", lineHeight: "15px" }}>
                    {d.driver}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Disclaimer */}
      <div style={{ fontSize: 9, color: "#334155", fontStyle: "italic", lineHeight: 1.4 }}>
        Deterministic baseline — not yet statistically calibrated
      </div>
    </>
  );
}
