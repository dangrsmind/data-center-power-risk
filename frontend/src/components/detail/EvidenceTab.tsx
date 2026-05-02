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
  pending:  "#fbbf24",
};

const STATUS_LABELS: Record<string, string> = {
  accepted: "Accepted",
  rejected: "Rejected",
  pending:  "Pending",
};

const FIELD_LABELS: Record<string, string> = {
  canonical_name:          "Project Name",
  developer:               "Developer",
  operator:                "Operator",
  state:                   "State",
  county:                  "County",
  region_id:               "Region / RTO",
  utility_id:              "Utility",
  announcement_date:       "Announced",
  latest_update_date:      "Last Update",
  phase_name:              "Phase Name",
  target_energization_date:"Target Date",
  modeled_primary_load_mw: "Modeled Load",
  optional_expansion_mw:   "Optional Expansion",
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
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Helper note */}
      <div style={{
        background: "var(--bg-active)",
        border: "1px solid var(--border)",
        borderRadius: 6,
        padding: "10px 14px",
        fontSize: 12,
        color: "var(--text-muted)",
        lineHeight: 1.6,
      }}>
        <strong style={{ color: "var(--text)", fontWeight: 600 }}>Source Status vs. Claim Acceptance</strong>
        {" — "}
        Evidence review status is separate from claim acceptance. A source may remain{" "}
        <span style={{ color: STATUS_COLORS.pending, fontWeight: 600 }}>pending</span> analyst sign-off
        while claims extracted from it have already been accepted into the project record.
      </div>

      {/* Table */}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={TH}>Date</th>
              <th style={TH}>Source Type</th>
              <th style={TH}>Title</th>
              <th style={TH}>Excerpt</th>
              <th style={TH}>Source Status</th>
              <th style={TH}>Accepted Fields</th>
              <th style={TH}>Link</th>
            </tr>
          </thead>
          <tbody>
            {evidence.map((item) => {
              const typeColor  = SOURCE_COLORS[item.source_type] ?? "var(--text-muted)";
              const typeLabel  = SOURCE_LABELS[item.source_type] ?? item.source_type;
              const statusColor = STATUS_COLORS[item.reviewer_status] ?? "var(--text-muted)";
              const statusLabel = STATUS_LABELS[item.reviewer_status] ?? item.reviewer_status;
              const isPending  = item.reviewer_status === "pending";
              const acceptedFields = item.field_names ?? [];

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

                  {/* Source Status — shows reviewer_status + "not yet reviewed" note when pending */}
                  <td style={TD}>
                    <span style={{ color: statusColor, fontSize: 11, fontWeight: 600 }}>
                      {statusLabel}
                    </span>
                    {isPending && (
                      <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 3, lineHeight: 1.4 }}>
                        Source not yet reviewed
                      </div>
                    )}
                  </td>

                  {/* Accepted Fields — provenance-written fields from accepted claims */}
                  <td style={TD}>
                    {acceptedFields.length === 0 ? (
                      <span style={{ fontSize: 11, color: "var(--text-dim)" }}>none</span>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                        <span style={{ fontSize: 11, color: "#34d399", fontWeight: 600, marginBottom: 2 }}>
                          {acceptedFields.length} accepted claim{acceptedFields.length !== 1 ? "s" : ""}
                        </span>
                        {acceptedFields.map(f => (
                          <span key={f} style={{
                            fontSize: 10,
                            padding: "1px 5px",
                            borderRadius: 3,
                            background: "#34d39922",
                            border: "1px solid #34d39944",
                            color: "#34d399",
                            whiteSpace: "nowrap",
                            width: "fit-content",
                          }}>
                            {FIELD_LABELS[f] ?? f}
                          </span>
                        ))}
                      </div>
                    )}
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
    </div>
  );
}
