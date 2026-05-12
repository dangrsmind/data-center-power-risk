import { useEffect, useMemo, useState } from "react";
import type {
  CoordinatePrecision,
  CoordinateSource,
  CoordinateStatus,
  ProjectDetail,
  ProjectListItem,
} from "../../api/types";
import { clearProjectCoordinates, patchProjectCoordinates } from "../../api/adapter";

type CoordinateProject = Pick<
  ProjectDetail | ProjectListItem,
  | "project_id"
  | "project_name"
  | "latitude"
  | "longitude"
  | "coordinate_status"
  | "coordinate_precision"
  | "coordinate_source"
  | "coordinate_source_url"
  | "coordinate_notes"
  | "coordinate_confidence"
>;

const STATUS_OPTIONS: CoordinateStatus[] = ["missing", "unverified", "verified", "needs_review"];
const PRECISION_OPTIONS: CoordinatePrecision[] = [
  "exact_site",
  "parcel",
  "campus",
  "city_centroid",
  "county_centroid",
  "state_centroid",
  "approximate",
  "unknown",
];
const SOURCE_OPTIONS: CoordinateSource[] = [
  "manual_review",
  "project_announcement",
  "utility_filing",
  "county_record",
  "company_website",
  "inferred_from_city",
  "imported_dataset",
  "other",
];

const VALID_SOURCES = new Set<string>(SOURCE_OPTIONS);

function sanitizeSource(raw: string | null | undefined): CoordinateSource {
  if (raw && VALID_SOURCES.has(raw)) return raw as CoordinateSource;
  if (raw && (raw.includes("dataset") || raw.includes("import"))) return "imported_dataset";
  if (raw) return "other";
  return "manual_review";
}

function label(value: string): string {
  return value.replace(/_/g, " ");
}

function formatCoord(value: number): string {
  return String(Number(value.toFixed(7)));
}

export function ProjectCoordinateEditor({
  project,
  pickedCoordinates,
  onSaved,
  onCancel,
  onStartPick,
  onClear,
}: {
  project: CoordinateProject;
  pickedCoordinates?: { latitude: number; longitude: number } | null;
  onSaved: (updated: ProjectDetail) => void;
  onCancel: () => void;
  onStartPick?: () => void;
  onClear?: (updated: ProjectDetail) => void;
}) {
  const hasCoordinates = project.latitude != null && project.longitude != null;
  const [latitude, setLatitude] = useState(project.latitude != null ? String(project.latitude) : "");
  const [longitude, setLongitude] = useState(project.longitude != null ? String(project.longitude) : "");
  const [status, setStatus] = useState<CoordinateStatus>(project.coordinate_status ?? "verified");
  const [precision, setPrecision] = useState<CoordinatePrecision>(project.coordinate_precision ?? "exact_site");
  const [source, setSource] = useState<CoordinateSource>(sanitizeSource(project.coordinate_source));
  const [sourceUrl, setSourceUrl] = useState(project.coordinate_source_url ?? "");
  const [confidence, setConfidence] = useState(
    project.coordinate_confidence != null ? String(project.coordinate_confidence) : "0.8",
  );
  const [notes, setNotes] = useState(project.coordinate_notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!pickedCoordinates) return;
    setLatitude(formatCoord(pickedCoordinates.latitude));
    setLongitude(formatCoord(pickedCoordinates.longitude));
  }, [pickedCoordinates]);

  const suspicious = useMemo(() => {
    const lat = Number(latitude);
    const lon = Number(longitude);
    if (latitude.trim() && longitude.trim() && lat === 0 && lon === 0) {
      return "0,0 is almost certainly not a project coordinate.";
    }
    if (precision === "exact_site" && !sourceUrl.trim() && !notes.trim()) {
      return "Exact-site coordinates should include a source URL or note.";
    }
    return null;
  }, [latitude, longitude, precision, sourceUrl, notes]);

  function validate(): string | null {
    const lat = Number(latitude);
    const lon = Number(longitude);
    if (!latitude.trim() || Number.isNaN(lat) || lat < -90 || lat > 90) {
      return "Latitude must be numeric and between -90 and 90.";
    }
    if (!longitude.trim() || Number.isNaN(lon) || lon < -180 || lon > 180) {
      return "Longitude must be numeric and between -180 and 180.";
    }
    if (!status) return "Coordinate status is required.";
    if (!precision) return "Coordinate precision is required.";
    if (confidence.trim()) {
      const parsed = Number(confidence);
      if (Number.isNaN(parsed) || parsed < 0 || parsed > 1) {
        return "Coordinate confidence must be blank or between 0 and 1.";
      }
    }
    return null;
  }

  function applyPrecisionDefaults(nextPrecision: CoordinatePrecision) {
    setPrecision(nextPrecision);
    if (nextPrecision === "exact_site") {
      setStatus("verified");
      setSource("manual_review");
      setConfidence("0.8");
    } else if (nextPrecision === "city_centroid") {
      setStatus("unverified");
      setSource("inferred_from_city");
      setConfidence("0.4");
    } else if (nextPrecision === "county_centroid") {
      setStatus("unverified");
      setSource("inferred_from_city");
      setConfidence("0.3");
    }
  }

  async function save() {
    const validation = validate();
    if (validation) {
      setError(validation);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await patchProjectCoordinates(project.project_id, {
        latitude: Number(latitude),
        longitude: Number(longitude),
        coordinate_status: status,
        coordinate_precision: precision,
        coordinate_source: source,
        coordinate_source_url: sourceUrl.trim() || null,
        coordinate_notes: notes.trim() || null,
        coordinate_confidence: confidence.trim() ? Number(confidence) : null,
        changed_by: "manual",
      });
      onSaved(updated);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function clear() {
    setSaving(true);
    setError(null);
    try {
      const updated = await clearProjectCoordinates(project.project_id);
      onClear?.(updated);
      onSaved(updated);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  const input: React.CSSProperties = {
    width: "100%",
    boxSizing: "border-box",
    background: "var(--bg)",
    border: "1px solid var(--border)",
    borderRadius: 4,
    color: "var(--text)",
    fontSize: 12,
    padding: "7px 9px",
  };
  const fieldLabel: React.CSSProperties = {
    display: "block",
    marginBottom: 4,
    color: "var(--text-dim)",
    fontSize: 10,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <label>
          <span style={fieldLabel}>Latitude</span>
          <input type="number" step="any" value={latitude} onChange={e => setLatitude(e.target.value)} style={input} />
        </label>
        <label>
          <span style={fieldLabel}>Longitude</span>
          <input type="number" step="any" value={longitude} onChange={e => setLongitude(e.target.value)} style={input} />
        </label>
      </div>

      {onStartPick && (
        <button
          type="button"
          onClick={onStartPick}
          style={{
            alignSelf: "flex-start",
            padding: "6px 10px",
            borderRadius: 4,
            border: "1px solid var(--border)",
            background: "transparent",
            color: "var(--accent)",
            fontSize: 12,
            cursor: "pointer",
          }}
        >
          Pick coordinates from map
        </button>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <label>
          <span style={fieldLabel}>Status</span>
          <select value={status} onChange={e => setStatus(e.target.value as CoordinateStatus)} style={input}>
            {STATUS_OPTIONS.map(option => <option key={option} value={option}>{label(option)}</option>)}
          </select>
        </label>
        <label>
          <span style={fieldLabel}>Precision</span>
          <select value={precision} onChange={e => applyPrecisionDefaults(e.target.value as CoordinatePrecision)} style={input}>
            {PRECISION_OPTIONS.map(option => <option key={option} value={option}>{label(option)}</option>)}
          </select>
        </label>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <label>
          <span style={fieldLabel}>Source</span>
          <select value={source} onChange={e => setSource(e.target.value as CoordinateSource)} style={input}>
            {SOURCE_OPTIONS.map(option => <option key={option} value={option}>{label(option)}</option>)}
          </select>
        </label>
        <label>
          <span style={fieldLabel}>Confidence</span>
          <input type="number" min="0" max="1" step="0.05" value={confidence} onChange={e => setConfidence(e.target.value)} style={input} />
        </label>
      </div>

      <label>
        <span style={fieldLabel}>Source URL</span>
        <input value={sourceUrl} onChange={e => setSourceUrl(e.target.value)} style={input} />
      </label>

      <label>
        <span style={fieldLabel}>Notes</span>
        <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={3} style={{ ...input, resize: "vertical" }} />
      </label>

      {suspicious && (
        <div style={{ fontSize: 11, color: "#fbbf24", background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.25)", borderRadius: 4, padding: "6px 8px" }}>
          {suspicious}
        </div>
      )}
      {error && (
        <div style={{ fontSize: 11, color: "#fca5a5", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.35)", borderRadius: 4, padding: "6px 8px" }}>
          {error}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, justifyContent: "space-between", flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={save} disabled={saving} style={primaryButtonStyle(saving)}>
            {saving ? "Saving..." : "Save"}
          </button>
          <button onClick={onCancel} disabled={saving} style={secondaryButtonStyle}>
            Cancel
          </button>
        </div>
        {hasCoordinates && (
          <button onClick={clear} disabled={saving} style={{ ...secondaryButtonStyle, color: "#fca5a5" }}>
            Clear Coordinates
          </button>
        )}
      </div>
    </div>
  );
}

function primaryButtonStyle(disabled: boolean): React.CSSProperties {
  return {
    padding: "7px 14px",
    borderRadius: 4,
    border: "1px solid rgba(34,197,94,0.45)",
    background: disabled ? "rgba(34,197,94,0.12)" : "rgba(34,197,94,0.2)",
    color: "#86efac",
    fontSize: 12,
    fontWeight: 700,
    cursor: disabled ? "default" : "pointer",
  };
}

const secondaryButtonStyle: React.CSSProperties = {
  padding: "7px 12px",
  borderRadius: 4,
  border: "1px solid var(--border)",
  background: "transparent",
  color: "var(--text-muted)",
  fontSize: 12,
  cursor: "pointer",
};
