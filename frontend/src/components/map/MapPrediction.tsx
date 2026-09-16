import { useEffect, useState } from "react";
import { getProjectPrediction } from "../../api/adapter";
import type { ProjectPredictionData } from "../../api/types";
import { humanize, tierColor } from "../../config/mapPresentation";

/** Existing prediction read, with map-scoped semantics and no run action. */
export function MapPrediction({ projectId }: { projectId: string }) {
  const [data, setData] = useState<ProjectPredictionData | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let cancelled = false;
    getProjectPrediction(projectId).then(value => { if (!cancelled) setData(value); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [projectId]);
  if (!data) return <p className="map-caveat">{failed ? "Prediction unavailable." : "Loading existing prediction…"}</p>;
  return <div className="map-prediction-content">
    <p style={{ color: tierColor(data.risk_tier) }}>{humanize(data.risk_tier)} model risk</p>
    <dl className="map-probabilities">{[["6 mo", data.p_delay_6mo], ["12 mo", data.p_delay_12mo], ["18 mo", data.p_delay_18mo]].map(([label, value]) => <div key={label}><dt>{label} delay</dt><dd>{typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "Unknown"}</dd></div>)}</dl>
    <p className="map-caveat">Model confidence: {humanize(data.confidence)}</p>
    {!!data.drivers.length && <ul>{data.drivers.slice(0, 3).map((driver, index) => <li key={index}>{driver.driver}</li>)}</ul>}
    <p className="map-caveat">{data.method_note || "Deterministic baseline; not statistically calibrated."}</p>
  </div>;
}
