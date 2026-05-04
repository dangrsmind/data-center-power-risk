import { Link, useLocation } from "react-router-dom";

const NAV = [
  { path: "/",         label: "Projects", icon: "▤" },
  { path: "/map",      label: "Map",      icon: "◎" },
  { path: "/discover", label: "Discover", icon: "⊘" },
  { path: "/ingest",   label: "Ingest",   icon: "⊕" },
];

export function Layout({ children }: { children: React.ReactNode }) {
  const loc = useLocation();

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <aside style={{
        width: 200,
        background: "var(--bg-surface)",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
      }}>
        <div style={{
          padding: "14px 16px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          flexDirection: "column",
          gap: 2,
        }}>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-dim)" }}>
            Power Risk
          </span>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Analyst Console</span>
        </div>

        <nav style={{ flex: 1, padding: "8px 0" }}>
          {NAV.map((item) => {
            const active = item.path === "/" ? loc.pathname === "/" : loc.pathname.startsWith(item.path);
            return (
              <Link
                key={item.path}
                to={item.path}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "7px 16px",
                  fontSize: 13,
                  color: active ? "var(--text)" : "var(--text-muted)",
                  background: active ? "var(--bg-active)" : "transparent",
                  borderLeft: active ? "2px solid var(--accent)" : "2px solid transparent",
                  transition: "background 0.15s",
                }}
              >
                <span style={{ fontSize: 14 }}>{item.icon}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div style={{
          padding: "10px 16px",
          borderTop: "1px solid var(--border)",
          fontSize: 11,
          color: "var(--text-dim)",
        }}>
          <div>v1 — mock data</div>
          <div style={{ marginTop: 2 }}>as of 2026-Q1</div>
        </div>
      </aside>

      <main style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {children}
      </main>
    </div>
  );
}
