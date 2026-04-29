import type { Score } from "../../api/types";
import { ScoreBar, PctDisplay } from "../shared/ScoreBar";

interface Props {
  score: Score;
}

export function ScorePanel({ score }: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Source note */}
      <div style={{ fontSize: 11, color: "var(--text-dim)", padding: "7px 10px", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 5 }}>
        ML scoring model — independent of the Evidence-Based Risk Signal shown on the Evidence Signal tab.
      </div>
      {/* Primary score cards */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(2, 1fr)",
        gap: 1,
        background: "var(--border)",
        borderRadius: 6,
        overflow: "hidden",
        border: "1px solid var(--border)",
      }}>
        {[
          { label: "Quarterly Hazard (E1)", value: score.current_hazard },
          { label: "Deadline Probability", value: score.deadline_probability },
        ].map(item => (
          <div key={item.label} style={{ background: "var(--bg)", padding: "16px 20px" }}>
            <PctDisplay value={item.value} label={item.label} />
          </div>
        ))}
      </div>

      {/* Stress & signal scores */}
      <div>
        <h4 style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)", marginBottom: 10 }}>
          Stress & Signal Scores
        </h4>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <ScoreBar value={score.project_stress_score} label="Project stress score" />
          <ScoreBar value={score.regional_stress_score} label="Regional stress score" />
          <ScoreBar value={score.anomaly_score} label="Anomaly score" />
          <ScoreBar value={score.evidence_quality_score} label="Evidence quality score" colorThresholds={false} />
        </div>
      </div>

      {/* Top drivers */}
      <div>
        <h4 style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)", marginBottom: 8 }}>
          Top Drivers
        </h4>
        <ol style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: 5 }}>
          {score.top_drivers.map((d, i) => (
            <li key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
              <span style={{
                fontSize: 10,
                fontWeight: 700,
                fontFamily: '"JetBrains Mono", monospace',
                color: "var(--text-dim)",
                background: "var(--bg-active)",
                padding: "1px 6px",
                borderRadius: 3,
                minWidth: 22,
                textAlign: "center",
                marginTop: 1,
                flexShrink: 0,
              }}>
                {i + 1}
              </span>
              <span style={{ fontSize: 13, color: "var(--text)" }}>{d}</span>
            </li>
          ))}
        </ol>
      </div>

      {/* Weak signal summary */}
      {score.weak_signal_summary && (
        <div>
          <h4 style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)", marginBottom: 6 }}>
            Weak Signal Summary (E2 / E3 / E4)
          </h4>
          <div style={{
            fontSize: 12,
            color: "var(--text-muted)",
            background: "var(--bg-active)",
            border: "1px solid var(--border)",
            borderRadius: 5,
            padding: "10px 12px",
            lineHeight: 1.6,
          }}>
            {score.weak_signal_summary}
          </div>
        </div>
      )}

      {/* Graph fragility summary */}
      {score.graph_fragility_summary && (
        <div>
          <h4 style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)", marginBottom: 8 }}>
            Graph Fragility
          </h4>
          <div style={{ display: "flex", gap: 24 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)", fontWeight: 600 }}>
                Most Likely Break Node
              </span>
              <span style={{
                fontFamily: '"JetBrains Mono", monospace',
                fontSize: 12,
                color: score.graph_fragility_summary.most_likely_break_node === "none_identified"
                  ? "var(--text-muted)"
                  : "#f97316",
              }}>
                {score.graph_fragility_summary.most_likely_break_node.replace(/_/g, " ")}
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)", fontWeight: 600 }}>
                Unresolved Critical Nodes
              </span>
              <span style={{
                fontFamily: '"JetBrains Mono", monospace',
                fontSize: 20,
                fontWeight: 700,
                color: score.graph_fragility_summary.unresolved_critical_nodes === 0
                  ? "#22c55e"
                  : score.graph_fragility_summary.unresolved_critical_nodes >= 4
                  ? "#ef4444"
                  : "#f97316",
              }}>
                {score.graph_fragility_summary.unresolved_critical_nodes}
              </span>
            </div>
          </div>
        </div>
      )}

      <div style={{ fontSize: 11, color: "var(--text-dim)", borderTop: "1px solid var(--border)", paddingTop: 10 }}>
        Score as of quarter: <span style={{ fontFamily: '"JetBrains Mono", monospace' }}>{score.as_of_quarter}</span>
        {score.phase_id && (
          <> · Phase: <span style={{ fontFamily: '"JetBrains Mono", monospace' }}>{score.phase_id}</span></>
        )}
      </div>
    </div>
  );
}
