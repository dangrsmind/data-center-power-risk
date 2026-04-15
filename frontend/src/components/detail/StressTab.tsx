import type { ProjectStressData } from "../../api/types";

const TH: React.CSSProperties = {
  padding: "6px 10px",
  fontSize: 10,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.07em",
  color: "var(--text-dim)",
  textAlign: "left",
  whiteSpace: "nowrap",
  borderBottom: "1px solid var(--border)",
};

const TD: React.CSSProperties = {
  padding: "7px 10px",
  fontSize: 12,
  color: "var(--text)",
  borderBottom: "1px solid var(--border)",
  verticalAlign: "top",
};

function scoreColor(v: number | null): string {
  if (v === null) return "var(--text-dim)";
  if (v > 0.6) return "#ef4444";
  if (v > 0.35) return "#f97316";
  return "var(--text)";
}

function ScoreCell({ value }: { value: number | null }) {
  if (value === null) return <span style={{ color: "var(--text-dim)" }}>—</span>;
  return (
    <span style={{ fontFamily: '"JetBrains Mono", monospace', color: scoreColor(value), fontWeight: 600 }}>
      {value.toFixed(2)}
    </span>
  );
}

interface Props {
  data: ProjectStressData;
}

export function StressTab({ data }: Props) {
  const { current_stress, signals } = data;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28, maxWidth: 900 }}>
      {/* Current stress summary card */}
      <div>
        <h3 style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)", marginBottom: 12 }}>
          Current Stress
        </h3>
        {!current_stress ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13 }}>No current stress record available.</div>
        ) : (
          <div style={{
            border: "1px solid var(--border)",
            borderRadius: 6,
            overflow: "hidden",
          }}>
            {/* Scores grid */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: 1,
              background: "var(--border)",
            }}>
              {[
                { label: "Project Stress", value: current_stress.project_stress_score },
                { label: "Regional Stress", value: current_stress.regional_stress_score },
                { label: "Anomaly", value: current_stress.anomaly_score },
                { label: "Evidence Quality", value: current_stress.evidence_quality_score },
              ].map(item => (
                <div key={item.label} style={{ background: "var(--bg)", padding: "12px 14px" }}>
                  <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", fontWeight: 600, marginBottom: 4 }}>
                    {item.label}
                  </div>
                  <div style={{ fontSize: 18, fontWeight: 700, fontFamily: '"JetBrains Mono", monospace', color: scoreColor(item.value) }}>
                    {item.value !== null ? item.value.toFixed(2) : "—"}
                  </div>
                </div>
              ))}
            </div>
            {/* Meta row */}
            <div style={{
              padding: "8px 14px",
              background: "var(--bg-active)",
              display: "flex",
              gap: 24,
              flexWrap: "wrap",
              fontSize: 11,
              color: "var(--text-muted)",
            }}>
              <span><span style={{ color: "var(--text-dim)" }}>Quarter</span> {current_stress.quarter}</span>
              <span><span style={{ color: "var(--text-dim)" }}>Region</span> {current_stress.region_name ?? "—"}</span>
              <span><span style={{ color: "var(--text-dim)" }}>Utility</span> {current_stress.utility_name ?? "—"}</span>
              <span><span style={{ color: "var(--text-dim)" }}>Model</span> {current_stress.model_version}</span>
            </div>
            {/* Decomposition */}
            {current_stress.decomposition && Object.keys(current_stress.decomposition).length > 0 && (
              <div style={{ padding: "10px 14px", borderTop: "1px solid var(--border)", display: "flex", gap: 20, flexWrap: "wrap" }}>
                <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.07em", color: "var(--text-dim)", fontWeight: 700, paddingTop: 2 }}>
                  Decomposition
                </div>
                {Object.entries(current_stress.decomposition).map(([k, v]) => (
                  <div key={k} style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    <span style={{ color: "var(--text-dim)", textTransform: "capitalize" }}>{k}:</span>{" "}
                    <span style={{ fontFamily: '"JetBrains Mono", monospace', color: "var(--text)" }}>{v.toFixed(3)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Signals table */}
      <div>
        <h3 style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)", marginBottom: 12 }}>
          Stress Signals ({signals.length})
        </h3>
        {signals.length === 0 ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13 }}>No stress signals recorded.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={TH}>Signal Name</th>
                  <th style={TH}>Type</th>
                  <th style={TH}>Quarter</th>
                  <th style={TH}>Value</th>
                  <th style={TH}>Weight</th>
                  <th style={TH}>Derived By</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((sig) => (
                  <tr key={sig.stress_observation_id}>
                    <td style={{ ...TD, fontFamily: '"JetBrains Mono", monospace', fontSize: 11 }}>
                      {sig.signal_name}
                    </td>
                    <td style={{ ...TD, color: "var(--text-muted)" }}>{sig.source_signal_type}</td>
                    <td style={{ ...TD, fontFamily: '"JetBrains Mono", monospace', color: "var(--text-dim)" }}>
                      {sig.quarter}
                    </td>
                    <td style={TD}>
                      <span style={{ fontFamily: '"JetBrains Mono", monospace' }}>
                        {sig.signal_value.toLocaleString()}
                      </span>
                    </td>
                    <td style={TD}><ScoreCell value={sig.signal_weight} /></td>
                    <td style={{ ...TD, color: "var(--text-muted)" }}>{sig.derived_by ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
