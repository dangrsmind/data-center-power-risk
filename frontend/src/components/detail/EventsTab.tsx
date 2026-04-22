import type { ProjectEvent } from "../../api/types";

const FAMILY_COLORS: Record<string, string> = {
  E1: "#ef4444",
  E2: "#f97316",
  E3: "#eab308",
  E4: "#a78bfa",
};

function FamilyBadge({ family }: { family: string }) {
  const color = FAMILY_COLORS[family] ?? "var(--text-muted)";
  return (
    <span style={{
      fontFamily: '"JetBrains Mono", monospace',
      fontSize: 11,
      fontWeight: 700,
      padding: "2px 7px",
      borderRadius: 3,
      background: `${color}22`,
      border: `1px solid ${color}66`,
      color,
    }}>
      {family}
    </span>
  );
}

function SeverityCell({ value }: { value: string | null }) {
  if (!value) return <span style={{ color: "var(--text-dim)" }}>—</span>;
  const color = value === "high" ? "#ef4444" : value === "medium" ? "#f97316" : "var(--text-muted)";
  return <span style={{ color, fontWeight: 600, fontSize: 12 }}>{value}</span>;
}

function ConfidenceCell({ value }: { value: string | null }) {
  if (!value) return <span style={{ color: "var(--text-dim)" }}>—</span>;
  const color = value === "high" ? "#34d399" : value === "medium" ? "#fbbf24" : "var(--text-muted)";
  return <span style={{ color, fontSize: 12 }}>{value}</span>;
}

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

interface Props {
  events: ProjectEvent[];
}

export function EventsTab({ events }: Props) {
  if (events.length === 0) {
    return (
      <div style={{ color: "var(--text-muted)", fontSize: 13, padding: "20px 0" }}>
        No events recorded for this project.
      </div>
    );
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr>
            <th style={TH}>Family</th>
            <th style={TH}>Date</th>
            <th style={TH}>Scope</th>
            <th style={TH}>Phase</th>
            <th style={TH}>Reason Class</th>
            <th style={TH}>Severity</th>
            <th style={TH}>Confidence</th>
            <th style={TH}>Adj.</th>
            <th style={TH}>WL Weight</th>
          </tr>
        </thead>
        <tbody>
          {events.map((ev) => (
            <tr key={ev.event_id} style={{ background: "transparent" }}>
              <td style={TD}><FamilyBadge family={ev.event_family} /></td>
              <td style={{ ...TD, fontFamily: '"JetBrains Mono", monospace', color: "var(--text-dim)" }}>
                {ev.event_date}
              </td>
              <td style={{ ...TD, color: "var(--text-muted)" }}>{ev.event_scope}</td>
              <td style={TD}>{ev.phase_name ?? <span style={{ color: "var(--text-dim)" }}>—</span>}</td>
              <td style={{ ...TD, color: "var(--text-muted)" }}>
                {ev.reason_class
                  ? ev.reason_class.replace(/_/g, " ")
                  : <span style={{ color: "var(--text-dim)" }}>—</span>}
              </td>
              <td style={TD}><SeverityCell value={ev.severity} /></td>
              <td style={TD}><ConfidenceCell value={ev.confidence} /></td>
              <td style={{ ...TD, color: ev.adjudicated ? "#34d399" : "var(--text-dim)" }}>
                {ev.adjudicated ? "yes" : "no"}
              </td>
              <td style={{ ...TD, fontFamily: '"JetBrains Mono", monospace', color: "var(--text-dim)" }}>
                {ev.weak_label_weight != null ? ev.weak_label_weight.toFixed(2) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {events.some(e => e.notes) && (
        <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 8 }}>
          {events.filter(e => e.notes).map(e => (
            <div key={e.event_id} style={{
              fontSize: 11,
              color: "var(--text-muted)",
              padding: "6px 10px",
              background: "var(--bg-active)",
              border: "1px solid var(--border)",
              borderRadius: 4,
            }}>
              <span style={{ color: "var(--text-dim)", marginRight: 6 }}>
                <FamilyBadge family={e.event_family} />
              </span>
              {" "}{e.notes}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
