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
