import type { Phase } from "../../api/types";
import { StatusBadge } from "../shared/Badge";

interface Props {
  phases: Phase[];
}

export function PhaseList({ phases }: Props) {
  return (
    <div>
      <h3 style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)", marginBottom: 10 }}>
        Phases ({phases.length})
      </h3>
      <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 90px 90px 130px 110px 110px",
          padding: "5px 10px",
          fontSize: 10,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          color: "var(--text-dim)",
          borderBottom: "1px solid var(--border)",
        }}>
          <span>Phase</span>
          <span>Load (MW)</span>
          <span>Expansion</span>
          <span>Target Date</span>
          <span>Status</span>
          <span>Flags</span>
        </div>
        {phases.map((ph) => (
          <div
            key={ph.phase_id}
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 90px 90px 130px 110px 110px",
              padding: "9px 10px",
              background: "var(--bg)",
              borderBottom: "1px solid var(--border-light)",
              alignItems: "center",
            }}
          >
            <div>
              <div style={{ fontWeight: 500, fontSize: 13 }}>{ph.phase_name}</div>
              {ph.utility && (
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>{ph.utility}</div>
              )}
            </div>
            <span style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 12 }}>
              {ph.modeled_primary_load_mw} MW
            </span>
            <span style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 12, color: "var(--text-muted)" }}>
              {ph.optional_expansion_mw != null ? `+${ph.optional_expansion_mw} MW` : "—"}
            </span>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
              {ph.target_energization_date ?? "—"}
            </span>
            <span>
              <StatusBadge status={ph.status} />
            </span>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {ph.new_transmission_required && (
                <span style={{ fontSize: 10, padding: "1px 5px", background: "#2a1500", color: "#f97316", borderRadius: 2, border: "1px solid #f9731633" }}>
                  TX req
                </span>
              )}
              {!ph.interconnection_status_known && (
                <span style={{ fontSize: 10, padding: "1px 5px", background: "#1a1040", color: "#a78bfa", borderRadius: 2, border: "1px solid #a78bfa33" }}>
                  IX unkn
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
