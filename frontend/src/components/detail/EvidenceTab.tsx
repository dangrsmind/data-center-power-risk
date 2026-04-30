import type { EvidenceItem } from "../../api/types";

const SOURCE_LABELS: Record<string, string> = {
  official_filing:    "Official Filing",
  utility_statement:  "Utility Statement",
  regulatory_record:  "Regulatory Record",
  county_record:      "County Record",
  press:              "Press",
  developer_statement:"Developer Statement",
  other:              "Other",
};

const SOURCE_COLORS: Record<string, string> = {
  official_filing:    "#a78bfa",
  utility_statement:  "#34d399",
  regulatory_record:  "#818cf8",
  county_record:      "#60a5fa",
  press:              "#fbbf24",
  developer_statement:"#f87171",
  other:              "#94a3b8",
};

const STATUS_COLORS: Record<string, string> = {
  accepted: "#34d399",
  rejected: "#ef4444",
  pending: "#fbbf24",
};

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
  padding: "8px 10px",
  fontSize: 12,
  color: "var(--text)",
  borderBottom: "1px solid var(--border)",
  verticalAlign: "top",
};

interface Props {
  evidence: EvidenceItem[];
}

export function EvidenceTab({ evidence }: Props) {
  if (evidence.length === 0) {
    return (
      <div style={{ color: "var(--text-muted)", fontSize: 13, padding: "20px 0" }}>
        No evidence items have been linked to this project yet.
      </div>
    );
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={TH}>Date</th>
            <th style={TH}>Source Type</th>
            <th style={TH}>Title</th>
            <th style={TH}>Excerpt</th>
            <th style={TH}>Status</th>
            <th style={TH}>Link</th>
          </tr>
        </thead>
        <tbody>
          {evidence.map((item) => {
            const typeColor = SOURCE_COLORS[item.source_type] ?? "var(--text-muted)";
            const typeLabel = SOURCE_LABELS[item.source_type] ?? item.source_type;
            const statusColor = STATUS_COLORS[item.reviewer_status] ?? "var(--text-muted)";
            return (
              <tr key={item.evidence_id}>
                <td style={{ ...TD, fontFamily: '"JetBrains Mono", monospace', color: "var(--text-dim)", whiteSpace: "nowrap", fontSize: 11 }}>
                  {item.source_date ?? "—"}
                </td>
                <td style={TD}>
                  <span style={{
                    fontSize: 10,
                    padding: "2px 6px",
                    borderRadius: 3,
                    background: `${typeColor}22`,
                    border: `1px solid ${typeColor}55`,
                    color: typeColor,
                    whiteSpace: "nowrap",
                  }}>
                    {typeLabel}
                  </span>
                </td>
                <td style={{ ...TD, maxWidth: 220 }}>
                  {item.title ?? <span style={{ color: "var(--text-dim)" }}>—</span>}
                </td>
                <td style={{ ...TD, color: "var(--text-muted)", maxWidth: 320, lineHeight: 1.5 }}>
                  {item.excerpt ?? <span style={{ color: "var(--text-dim)" }}>—</span>}
                </td>
                <td style={TD}>
                  <span style={{ color: statusColor, fontSize: 11, fontWeight: 600 }}>
                    {item.reviewer_status}
                  </span>
                </td>
                <td style={TD}>
                  {item.source_url
                    ? (
                      <a
                        href={item.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: "var(--accent)", fontSize: 11, textDecoration: "none" }}
                      >
                        source ↗
                      </a>
                    )
                    : <span style={{ color: "var(--text-dim)" }}>—</span>
                  }
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
