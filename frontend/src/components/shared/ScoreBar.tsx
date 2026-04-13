interface ScoreBarProps {
  value: number;
  max?: number;
  label?: string;
  colorThresholds?: boolean;
}

function getColor(v: number): string {
  if (v >= 0.7) return "#ef4444";
  if (v >= 0.5) return "#f97316";
  if (v >= 0.3) return "#eab308";
  return "#22c55e";
}

export function ScoreBar({ value, max = 1, label, colorThresholds = true }: ScoreBarProps) {
  const pct = Math.min((value / max) * 100, 100);
  const color = colorThresholds ? getColor(value / max) : "var(--accent)";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: "var(--bg-active)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 3, transition: "width 0.3s ease" }} />
      </div>
      <span style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 12, color: color, minWidth: 42, textAlign: "right" }}>
        {(value * (max === 1 ? 100 : 1)).toFixed(max === 1 ? 0 : 1)}{max === 1 ? "%" : ""}
      </span>
      {label && <span style={{ fontSize: 11, color: "var(--text-muted)", minWidth: 140 }}>{label}</span>}
    </div>
  );
}

export function PctDisplay({ value, label }: { value: number; label: string }) {
  const color = getColor(value);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)", fontWeight: 600 }}>
        {label}
      </span>
      <span style={{ fontSize: 22, fontWeight: 600, fontFamily: '"JetBrains Mono", monospace', color }}>
        {(value * 100).toFixed(1)}%
      </span>
    </div>
  );
}
