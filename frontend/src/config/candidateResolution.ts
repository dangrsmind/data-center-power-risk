export const REVIEWABLE_CLASSES = ["promotable_now", "resolvable_missing_coordinates", "resolvable_missing_identity"];
export const RESOLUTION_CLASSES = [...REVIEWABLE_CLASSES, "unresolved_placeholder", "context_only_or_supporting", "low_confidence", "already_promoted", "exception_review"];
export const resolutionLabel = (value: string) => value.replace(/_/g, " ");
export const matchesResolution = (value: string | undefined, filter: string) =>
  filter === "all" || (filter === "reviewable" ? REVIEWABLE_CLASSES.includes(value ?? "") : value === filter);
