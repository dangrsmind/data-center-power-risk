import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import type { ProjectDetail, TimelineEvent } from "../api/types";
import { getProject, getTimeline } from "../api/adapter";
import { ProjectDetailPanel } from "../components/detail/ProjectDetailPanel";
import { PhaseList } from "../components/detail/PhaseList";
import { ScorePanel } from "../components/detail/ScorePanel";

const SOURCE_LABELS: Record<string, string> = {
  county_record: "County Record",
  utility_statement: "Utility Statement",
  regulatory_filing: "Regulatory Filing",
  press: "Press",
  developer_statement: "Developer Statement",
  rto_filing: "RTO Filing",
};

const SOURCE_COLORS: Record<string, string> = {
  county_record: "#60a5fa",
  utility_statement: "#34d399",
  regulatory_filing: "#a78bfa",
  press: "#fbbf24",
  developer_statement: "#f87171",
  rto_filing: "#38bdf8",
};

type TabId = "overview" | "phases" | "score" | "timeline";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "phases", label: "Phases" },
  { id: "score", label: "Score" },
  { id: "timeline", label: "Evidence Timeline" },
];

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>("overview");

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setProject(null);
    setTimeline([]);
    Promise.all([getProject(id), getTimeline(id)])
      .then(([proj, tl]) => {
        setProject(proj);
        setTimeline(tl);
      })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Breadcrumb + tabs header */}
      <div style={{
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-surface)",
        flexShrink: 0,
      }}>
        <div style={{ padding: "10px 20px 0", display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
            <Link to="/" style={{ color: "var(--accent)", textDecoration: "none" }}>
              Projects
            </Link>
            {" / "}
            <span>{project?.project_name ?? id}</span>
          </div>

          <div style={{ display: "flex", gap: 0 }}>
            {TABS.map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                style={{
                  padding: "6px 14px",
                  fontSize: 12,
                  fontWeight: tab === t.id ? 600 : 400,
                  color: tab === t.id ? "var(--text)" : "var(--text-muted)",
                  background: "transparent",
                  border: "none",
                  borderBottom: tab === t.id ? "2px solid var(--accent)" : "2px solid transparent",
                  marginBottom: -1,
                  cursor: "pointer",
                  transition: "color 0.15s",
                }}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: "auto", padding: "20px" }}>
        {loading && (
          <div style={{ color: "var(--text-muted)", padding: 20 }}>Loading project…</div>
        )}
        {error && (
          <div style={{
            padding: "10px 14px",
            background: "var(--risk-high-bg)",
            border: "1px solid var(--risk-high)",
            borderRadius: 5,
            color: "var(--risk-high)",
            fontSize: 12,
          }}>
            {error}
          </div>
        )}
        {project && !loading && (
          <>
            {tab === "overview" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 24, maxWidth: 900 }}>
                <ProjectDetailPanel project={project} />
                <SectionCard title="Score Summary">
                  <QuickScoreRow project={project} />
                </SectionCard>
                <SectionCard title="Phase Overview">
                  <PhaseList phases={project.phases} />
                </SectionCard>
              </div>
            )}

            {tab === "phases" && (
              <div style={{ maxWidth: 900 }}>
                <PhaseList phases={project.phases} />
              </div>
            )}

            {tab === "score" && (
              <div style={{ maxWidth: 680 }}>
                <ScorePanel score={project.score} />
              </div>
            )}

            {tab === "timeline" && (
              <div style={{ maxWidth: 760 }}>
                <h3 style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)", marginBottom: 14 }}>
                  Evidence Timeline
                </h3>
                {timeline.length === 0 ? (
                  <div style={{ color: "var(--text-muted)", fontSize: 13 }}>No timeline events available for this project.</div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                    {timeline.map((ev, i) => (
                      <div key={i} style={{ display: "flex", gap: 16, paddingBottom: 20, position: "relative" }}>
                        {/* Line */}
                        {i < timeline.length - 1 && (
                          <div style={{
                            position: "absolute",
                            left: 57,
                            top: 22,
                            bottom: 0,
                            width: 1,
                            background: "var(--border)",
                          }} />
                        )}
                        {/* Date */}
                        <div style={{ width: 100, flexShrink: 0, fontSize: 11, color: "var(--text-dim)", fontFamily: '"JetBrains Mono", monospace', paddingTop: 3 }}>
                          {ev.date}
                        </div>
                        {/* Dot */}
                        <div style={{
                          width: 10,
                          height: 10,
                          borderRadius: "50%",
                          background: SOURCE_COLORS[ev.source_type] ?? "#7b8db0",
                          flexShrink: 0,
                          marginTop: 5,
                          zIndex: 1,
                        }} />
                        {/* Content */}
                        <div style={{ flex: 1 }}>
                          <div style={{ marginBottom: 4 }}>
                            <span style={{
                              fontSize: 10,
                              padding: "1px 6px",
                              borderRadius: 3,
                              background: "var(--bg-active)",
                              border: "1px solid var(--border)",
                              color: SOURCE_COLORS[ev.source_type] ?? "var(--text-muted)",
                            }}>
                              {SOURCE_LABELS[ev.source_type] ?? ev.source_type}
                            </span>
                          </div>
                          <div style={{ fontSize: 13, color: "var(--text)", lineHeight: 1.5 }}>{ev.summary}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <h3 style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)" }}>
        {title}
      </h3>
      {children}
    </div>
  );
}

function QuickScoreRow({ project }: { project: ProjectDetail }) {
  const s = project.score;
  const items = [
    { label: "Q-Hazard", value: `${(s.current_hazard * 100).toFixed(1)}%`, highlight: s.current_hazard > 0.07 },
    { label: "Deadline P", value: `${(s.deadline_probability * 100).toFixed(1)}%`, highlight: s.deadline_probability > 0.2 },
    { label: "Project Stress", value: s.project_stress_score.toFixed(2), highlight: s.project_stress_score > 0.6 },
    { label: "Regional Stress", value: s.regional_stress_score.toFixed(2), highlight: s.regional_stress_score > 0.5 },
    { label: "Anomaly", value: s.anomaly_score.toFixed(2), highlight: s.anomaly_score > 0.4 },
    { label: "Evidence Quality", value: s.evidence_quality_score.toFixed(2), highlight: false },
  ];
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "repeat(6, 1fr)",
      gap: 1,
      background: "var(--border)",
      border: "1px solid var(--border)",
      borderRadius: 6,
      overflow: "hidden",
    }}>
      {items.map(item => (
        <div key={item.label} style={{ background: "var(--bg)", padding: "12px 14px" }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", fontWeight: 600, marginBottom: 4 }}>
            {item.label}
          </div>
          <div style={{
            fontFamily: '"JetBrains Mono", monospace',
            fontSize: 16,
            fontWeight: 700,
            color: item.highlight ? "#ef4444" : "var(--text)",
          }}>
            {item.value}
          </div>
        </div>
      ))}
    </div>
  );
}
