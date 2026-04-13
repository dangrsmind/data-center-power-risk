import { useEffect, useState } from "react";
import type { ProjectListItem } from "../api/types";
import { getProjects } from "../api/adapter";
import { ProjectListTable } from "../components/projects/ProjectListTable";

export function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProjects()
      .then(setProjects)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Page header */}
      <div style={{
        display: "flex",
        alignItems: "center",
        padding: "12px 20px",
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-surface)",
        flexShrink: 0,
      }}>
        <div>
          <h2 style={{ fontSize: 15, fontWeight: 600 }}>Project Portfolio</h2>
          <p style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
            All monitored data-center projects · Click row to open detail
          </p>
        </div>
      </div>

      {error && (
        <div style={{
          margin: 16,
          padding: "10px 14px",
          background: "var(--risk-high-bg)",
          border: "1px solid var(--risk-high)",
          borderRadius: 5,
          color: "var(--risk-high)",
          fontSize: 12,
        }}>
          Error loading projects: {error}
        </div>
      )}

      <div style={{ flex: 1, overflow: "hidden" }}>
        <ProjectListTable projects={projects} loading={loading} />
      </div>
    </div>
  );
}
