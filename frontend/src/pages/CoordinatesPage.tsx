import { useEffect, useState } from "react";
import type { MissingCoordinateProject, ProjectDetail } from "../api/types";
import { getMissingCoordinateProjects, getProject } from "../api/adapter";
import { ProjectCoordinateEditor } from "../components/coordinates/ProjectCoordinateEditor";

export function CoordinatesPage() {
  const [rows, setRows] = useState<MissingCoordinateProject[]>([]);
  const [editing, setEditing] = useState<ProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setRows(await getMissingCoordinateProjects());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function openEditor(projectId: string) {
    setError(null);
    try {
      setEditing(await getProject(projectId));
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)", background: "var(--bg-surface)" }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text)" }}>Coordinate Review</div>
        <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
          {loading ? "Loading..." : `${rows.length} project${rows.length !== 1 ? "s" : ""} missing or needing review`}
        </div>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 20 }}>
        {error && (
          <div style={{ color: "#fca5a5", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.35)", borderRadius: 5, padding: "8px 10px", marginBottom: 12, fontSize: 12 }}>
            {error}
          </div>
        )}
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em", fontSize: 10 }}>
              {["Project name", "Developer", "Utility", "City", "County", "State", "Status", "Precision", ""].map(h => (
                <th key={h} style={{ textAlign: "left", padding: "8px 10px", borderBottom: "1px solid var(--border)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.id} style={{ borderBottom: "1px solid var(--border)" }}>
                <td style={cellStyle}>{row.name}</td>
                <td style={cellStyle}>{row.developer ?? "-"}</td>
                <td style={cellStyle}>{row.utility ?? "-"}</td>
                <td style={cellStyle}>{row.city ?? "-"}</td>
                <td style={cellStyle}>{row.county ?? "-"}</td>
                <td style={cellStyle}>{row.state ?? "-"}</td>
                <td style={cellStyle}>{(row.coordinate_status ?? "missing").replace(/_/g, " ")}</td>
                <td style={cellStyle}>{(row.coordinate_precision ?? "unknown").replace(/_/g, " ")}</td>
                <td style={{ ...cellStyle, textAlign: "right" }}>
                  <button onClick={() => openEditor(row.id)} style={buttonStyle}>
                    {row.latitude != null && row.longitude != null ? "Edit" : "Add"}
                  </button>
                </td>
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={9} style={{ padding: 18, color: "var(--text-muted)", textAlign: "center" }}>
                  No projects need coordinate review.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {editing && (
        <div style={{ position: "fixed", inset: 0, zIndex: 2000, background: "rgba(0,0,0,0.45)", display: "flex", justifyContent: "center", alignItems: "flex-start", paddingTop: 48 }}>
          <div style={{ width: 480, maxWidth: "calc(100vw - 32px)", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 6, padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 12 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>{editing.project_name}</div>
                <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>Coordinate editor</div>
              </div>
              <button onClick={() => setEditing(null)} style={{ background: "transparent", border: 0, color: "var(--text-muted)", cursor: "pointer", fontSize: 18, lineHeight: 1 }}>
                x
              </button>
            </div>
            <ProjectCoordinateEditor
              project={editing}
              onCancel={() => setEditing(null)}
              onSaved={async () => {
                setEditing(null);
                await refresh();
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

const cellStyle: React.CSSProperties = {
  padding: "9px 10px",
  color: "var(--text-muted)",
  verticalAlign: "top",
};

const buttonStyle: React.CSSProperties = {
  padding: "5px 10px",
  borderRadius: 4,
  border: "1px solid var(--border)",
  background: "transparent",
  color: "var(--accent)",
  cursor: "pointer",
  fontSize: 12,
};
