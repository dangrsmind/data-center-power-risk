import type { ProjectDetail } from "../../api/types";
import { RiskBadge, LifecycleBadge } from "../shared/Badge";
import { KeyValue, KeyValueGrid } from "../shared/KeyValue";

interface Props {
  project: ProjectDetail;
}

export function ProjectDetailPanel({ project: p }: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 600, marginBottom: 6 }}>{p.project_name}</h1>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <LifecycleBadge state={p.lifecycle_state} />
            <RiskBadge tier={p.risk_tier} />
            <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
              {p.project_id}
            </span>
          </div>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>Last updated</div>
          <div style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 12, color: "var(--text-muted)" }}>
            {p.latest_update_date}
          </div>
        </div>
      </div>

      {/* Metadata grid */}
      <div style={{ background: "var(--bg-active)", border: "1px solid var(--border)", borderRadius: 6, padding: "14px 16px" }}>
        <KeyValueGrid cols={4}>
          <KeyValue label="State" value={p.state} />
          <KeyValue label="RTO / Region" value={p.region_or_rto} />
          <KeyValue label="Utility" value={p.utility ?? "—"} />
          <KeyValue label="Announced" value={p.announce_date ?? "—"} />
          <KeyValue
            label="Modeled Primary Load"
            value={<span style={{ fontFamily: '"JetBrains Mono", monospace' }}>{p.modeled_primary_load_mw} MW</span>}
          />
          <KeyValue
            label="Headline Load"
            value={p.headline_load_mw != null
              ? <span style={{ fontFamily: '"JetBrains Mono", monospace' }}>{p.headline_load_mw} MW</span>
              : "—"
            }
          />
          <KeyValue
            label="Optional Expansion"
            value={p.optional_expansion_mw != null
              ? <span style={{ fontFamily: '"JetBrains Mono", monospace' }}>+{p.optional_expansion_mw} MW</span>
              : "—"
            }
          />
          <KeyValue
            label="Data Quality Score"
            value={
              <span style={{
                fontFamily: '"JetBrains Mono", monospace',
                color: p.data_quality_score >= 80 ? "#22c55e" : p.data_quality_score >= 60 ? "#eab308" : "#ef4444",
              }}>
                {p.data_quality_score} / 100
              </span>
            }
          />
        </KeyValueGrid>
      </div>
    </div>
  );
}
