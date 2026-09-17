import type { ProjectListItem } from "../api/types";

// CSS variables resolve inside the map console, including Leaflet's marker pane.
export const tierColor = (tier: string | null) => {
  if (tier === "high") return "var(--map-hot)";
  if (["elevated", "medium", "moderate"].includes(tier ?? "")) return "var(--map-amber)";
  return "var(--map-slate)";
};
export const humanize = (value?: string | null) => value ? value.replace(/_/g, " ") : "Unknown";
export const formatLoad = (value: number) => Number.isFinite(value) && value > 0 ? value.toLocaleString("en-US", { maximumFractionDigits: 0 }) : "Unknown";
export const markerRadius = (mw: number) => Number.isFinite(mw) && mw > 0 ? Math.max(7, Math.min(24, Math.sqrt(mw / 60) * 4.2)) : 7;
export function isMappable(project: ProjectListItem, showApproximate = true) {
  const { latitude: lat, longitude: lng } = project;
  if (lat == null || lng == null || !Number.isFinite(Number(lat)) || !Number.isFinite(Number(lng))) return false;
  if (Math.abs(Number(lat)) > 90 || Math.abs(Number(lng)) > 180 || project.coordinate_status === "missing") return false;
  return showApproximate || !["state_centroid", "approximate"].includes(project.coordinate_precision ?? "");
}

export type MapLayerId = "projects" | "risk" | "high_signal" | "verified" | "incomplete";
export interface MapLayerRecord {
  project: ProjectListItem;
  signal: { risk_signal_tier: string } | null;
}
export const MAP_LAYERS: ReadonlyArray<{
  id: MapLayerId; label: string; description: string; enabledDefault: boolean; color: string;
}> = [
  { id: "projects", label: "Project markers", description: "Known project records with visible coordinates. Hiding markers also hides their overlays.", enabledDefault: true, color: "var(--map-slate)" },
  { id: "risk", label: "Model-risk halos", description: "High risk: red-orange. Elevated, medium or moderate: amber. Uses the existing model tier, not a new prediction.", enabledDefault: false, color: "var(--map-amber)" },
  { id: "high_signal", label: "High-signal rings", description: "Red-orange outer ring for an explicit high evidence-signal tier. Not proof of a verified constraint.", enabledDefault: true, color: "var(--map-hot)" },
  { id: "verified", label: "Verified coordinates", description: "Green inner ring only for explicit verified coordinate status. Not project or analyst approval.", enabledDefault: true, color: "var(--map-green)" },
  { id: "incomplete", label: "Incomplete locations", description: "Dashed slate ring for unverified, approximate, missing-precision, or low/unknown coordinate confidence. Confidence below 0.5 is a display threshold only.", enabledDefault: true, color: "var(--map-slate)" },
];
export const defaultMapLayers = (): Record<MapLayerId, boolean> => Object.fromEntries(MAP_LAYERS.map(layer => [layer.id, layer.enabledDefault])) as Record<MapLayerId, boolean>;

export function classifyMapRecord(item: MapLayerRecord): Record<MapLayerId, boolean> {
  const p = item.project;
  const confidence = p.coordinate_confidence;
  return {
    projects: true,
    risk: ["high", "elevated", "medium", "moderate"].includes(p.risk_tier),
    high_signal: item.signal?.risk_signal_tier === "high",
    verified: p.coordinate_status === "verified",
    incomplete: p.coordinate_status !== "verified"
      || !["exact_site", "parcel", "campus"].includes(p.coordinate_precision ?? "")
      || confidence == null || !Number.isFinite(confidence) || confidence < 0.5 || confidence > 1,
  };
}
/** Counts are eligibility counts before layer toggles; overlaps are intentional. */
export function mapLayerCounts(items: MapLayerRecord[], showApproximate: boolean): Record<MapLayerId, number> {
  const counts: Record<MapLayerId, number> = { projects: 0, risk: 0, high_signal: 0, verified: 0, incomplete: 0 };
  for (const item of items) {
    if (!isMappable(item.project, showApproximate)) continue;
    const classification = classifyMapRecord(item);
    for (const layer of MAP_LAYERS) if (classification[layer.id]) counts[layer.id]++;
  }
  return counts;
}
export function visibleMapRecords<T extends MapLayerRecord>(items: T[], showApproximate: boolean, layers: Record<MapLayerId, boolean>): T[] {
  return layers.projects ? items.filter(item => isMappable(item.project, showApproximate)) : [];
}
