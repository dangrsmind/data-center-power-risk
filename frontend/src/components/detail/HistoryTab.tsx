import type { ProjectHistoryItem } from "../../api/types";

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
  verticalAlign: "middle",
};

function PctCell({ value }: { value: number | null | undefined }) {
  if (value == null) return <span style={{ color: "var(--text-dim)" }}>—</span>;
  const pct = value * 100;
  const color = pct > 70 ? "#ef4444" : pct > 40 ? "#f97316" : "#34d399";
  return (
    <span style={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 600, color }}>
      {pct.toFixed(1)}%
    </span>
  );
}

function ScoreCell({ value }: { value: number | null | undefined }) {
  if (value == null) return <span style={{ color: "var(--text-dim)" }}>—</span>;
  const color = value > 0.6 ? "#ef4444" : value > 0.35 ? "#f97316" : "var(--text)";
  return (
    <span style={{ fontFamily: '"JetBrains Mono", monospace', color }}>
      {value.toFixed(2)}
    </span>
  );
}

function BoolCell({ value }: { value: boolean | null | undefined }) {
  if (value == null) return <span style={{ color: "var(--text-dim)" }}>—</span>;
  return (
    <span style={{ color: value ? "#ef4444" : "var(--text-dim)", fontWeight: value ? 700 : 400, fontSize: 11 }}>
      {value ? "yes" : "no"}
    </span>
  );
}

interface Props {
  history: ProjectHistoryItem[];
}

export function HistoryTab({ history }: Props) {
  if (history.length === 0) {
    return (
      <div style={{ color: "var(--text-muted)", fontSize: 13, padding: "20px 0" }}>
        No historical records available for this project.
      </div>
    );
  }

  const sorted = [...history].sort((a, b) =>
    b.quarter.localeCompare(a.quarter)
  );

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={TH}>Quarter</th>
            <th style={TH}>Phase</th>
            <th style={TH}>Q-Hazard</th>
            <th style={TH}>Deadline P</th>
            <th style={TH}>Proj. Stress</th>
            <th style={TH}>Reg. Stress</th>
            <th style={TH}>Anomaly</th>
            <th style={TH}>E1</th>
            <th style={TH}>E2</th>
            <th style={TH}>E3</th>
            <th style={TH}>E4</th>
            <th style={TH}>DQ Score</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((item) => (
            <tr key={item.project_phase_quarter_id}>
              <td style={{ ...TD, fontFamily: '"JetBrains Mono", monospace', color: "var(--text-dim)", whiteSpace: "nowrap" }}>
                {item.quarter}
              </td>
              <td style={{ ...TD, whiteSpace: "nowrap" }}>{item.phase_name}</td>
              <td style={TD}><PctCell value={item.current_hazard} /></td>
              <td style={TD}><PctCell value={item.deadline_probability} /></td>
              <td style={TD}><ScoreCell value={item.project_stress_score} /></td>
              <td style={TD}><ScoreCell value={item.regional_stress_score} /></td>
              <td style={TD}><ScoreCell value={item.anomaly_score} /></td>
              <td style={TD}><BoolCell value={item.E1_label} /></td>
              <td style={TD}><BoolCell value={item.E2_label} /></td>
              <td style={TD}>
                {item.E3_intensity != null
                  ? <span style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 11, color: "var(--text-muted)" }}>{item.E3_intensity.toFixed(2)}</span>
                  : <span style={{ color: "var(--text-dim)" }}>—</span>
                }
              </td>
              <td style={TD}><BoolCell value={item.E4_label} /></td>
              <td style={{ ...TD, color: "var(--text-muted)", fontFamily: '"JetBrains Mono", monospace', fontSize: 11 }}>
                {item.data_quality_score != null ? item.data_quality_score.toFixed(0) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
