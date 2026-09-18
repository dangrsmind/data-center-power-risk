import type { ProjectCandidate } from "../api/types";

export function isBaselineCandidate(c: ProjectCandidate): boolean {
  return c.csv_provenance?.import_kind === "baseline_dataset_import" || c.lifecycle_state === "dataset_import_needs_review";
}
export function isReviewCandidate(c: ProjectCandidate): boolean {
  return c.status === "needs_review" && !c.promoted_project_id;
}
export function hasCandidateCoordinates(c: ProjectCandidate): boolean {
  return typeof c.latitude === "number" && Number.isFinite(c.latitude) && Math.abs(c.latitude) <= 90
    && typeof c.longitude === "number" && Number.isFinite(c.longitude) && Math.abs(c.longitude) <= 180;
}
export function safeSourceUrl(url: string | null): string | undefined {
  try { const parsed = new URL(url ?? ""); return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : undefined; }
  catch { return undefined; }
}
