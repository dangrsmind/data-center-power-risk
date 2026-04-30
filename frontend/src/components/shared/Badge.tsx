import type { LifecycleState, RiskTier, PhaseStatus } from "../../api/types";

interface BadgeProps {
  children: React.ReactNode;
  variant?: "risk" | "lifecycle" | "status" | "neutral";
  value?: string;
}

const riskColors: Record<RiskTier, { color: string; bg: string }> = {
  high: { color: "var(--risk-high)", bg: "var(--risk-high-bg)" },
  elevated: { color: "var(--risk-elevated)", bg: "var(--risk-elevated-bg)" },
  medium: { color: "var(--risk-elevated)", bg: "var(--risk-elevated-bg)" },
  moderate: { color: "var(--risk-moderate)", bg: "var(--risk-moderate-bg)" },
  low: { color: "var(--risk-low)", bg: "var(--risk-low-bg)" },
  unknown: { color: "var(--risk-unknown)", bg: "var(--risk-unknown-bg)" },
};

const lifecycleColors: Record<LifecycleState, { color: string; bg: string }> = {
  // Real backend states — progressive readiness (blue → green)
  candidate_unverified:    { color: "#64748b", bg: "#161e2e" },
  named_verified:          { color: "#94a3b8", bg: "#192130" },
  location_verified:       { color: "#7dd3fc", bg: "#0c2340" },
  load_partially_resolved: { color: "#818cf8", bg: "#16184a" },
  phase_resolved:          { color: "#a78bfa", bg: "#1a1040" },
  power_path_partial:      { color: "#fb923c", bg: "#2c1400" },
  monitoring_ready:        { color: "#60a5fa", bg: "#0d1f3c" },
  production_ready:        { color: "#22c55e", bg: "#0d2416" },
  // Legacy / mock states
  under_review:       { color: "#a78bfa", bg: "#1a1040" },
  active_construction:{ color: "#34d399", bg: "#0a2416" },
  operational:        { color: "#22c55e", bg: "#0d2416" },
  canceled:           { color: "#ef4444", bg: "#2d1010" },
  delayed:            { color: "#f97316", bg: "#2a1500" },
  downsized:          { color: "#eab308", bg: "#271e00" },
};

const statusColors: Record<PhaseStatus, { color: string; bg: string }> = {
  planning: { color: "#60a5fa", bg: "#0d1f3c" },
  permitting: { color: "#a78bfa", bg: "#1a1040" },
  construction: { color: "#34d399", bg: "#0a2416" },
  energized: { color: "#22c55e", bg: "#0d2416" },
  delayed: { color: "#f97316", bg: "#2a1500" },
  canceled: { color: "#ef4444", bg: "#2d1010" },
};

function label(s: string) {
  return s.replace(/_/g, " ");
}

export function RiskBadge({ tier }: { tier: RiskTier }) {
  const c = riskColors[tier] ?? riskColors.unknown;
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 7px",
      borderRadius: 3,
      fontSize: 11,
      fontWeight: 600,
      letterSpacing: "0.04em",
      textTransform: "uppercase",
      color: c.color,
      background: c.bg,
      border: `1px solid ${c.color}33`,
    }}>
      {tier}
    </span>
  );
}

export function LifecycleBadge({ state }: { state: LifecycleState }) {
  const c = lifecycleColors[state] ?? { color: "#7b8db0", bg: "#1a1f2e" };
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 7px",
      borderRadius: 3,
      fontSize: 11,
      color: c.color,
      background: c.bg,
      border: `1px solid ${c.color}33`,
      whiteSpace: "nowrap",
    }}>
      {label(state)}
    </span>
  );
}

export function StatusBadge({ status }: { status: PhaseStatus }) {
  const c = statusColors[status] ?? { color: "#7b8db0", bg: "#1a1f2e" };
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 7px",
      borderRadius: 3,
      fontSize: 11,
      color: c.color,
      background: c.bg,
      border: `1px solid ${c.color}33`,
    }}>
      {label(status)}
    </span>
  );
}

export function Tag({ children }: BadgeProps) {
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 6px",
      borderRadius: 3,
      fontSize: 11,
      color: "var(--text-muted)",
      background: "var(--bg-active)",
      border: "1px solid var(--border)",
    }}>
      {children}
    </span>
  );
}
