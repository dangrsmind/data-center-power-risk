interface KeyValueProps {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}

export function KeyValue({ label, value, mono }: KeyValueProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)", fontWeight: 600 }}>
        {label}
      </span>
      <span style={{ color: "var(--text)", fontFamily: mono ? '"JetBrains Mono", monospace' : "inherit", fontSize: mono ? 12 : 13 }}>
        {value ?? <span style={{ color: "var(--text-dim)" }}>—</span>}
      </span>
    </div>
  );
}

interface KeyValueGridProps {
  children: React.ReactNode;
  cols?: number;
}

export function KeyValueGrid({ children, cols = 3 }: KeyValueGridProps) {
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: `repeat(${cols}, 1fr)`,
      gap: "16px 24px",
    }}>
      {children}
    </div>
  );
}
