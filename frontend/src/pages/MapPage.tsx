import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { MapContainer, TileLayer, Marker, Popup, GeoJSON, CircleMarker, useMap, useMapEvents } from "react-leaflet";
import { Link } from "react-router-dom";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "../styles/map-console.css";
import { getBasemapConfig } from "../config/basemap";
import { MAP_LAYERS, classifyMapRecord, defaultMapLayers, mapLayerCounts, visibleMapRecords, type MapLayerId, formatLoad, humanize, isMappable, markerRadius, tierColor } from "../config/mapPresentation";
import type { ProjectDetail, ProjectListItem, ProjectRiskSignalData } from "../api/types";
import { getProjects, getProjectRiskSignal, getProject } from "../api/adapter";
import { ProjectCoordinateEditor } from "../components/coordinates/ProjectCoordinateEditor";
import { MapPrediction } from "../components/map/MapPrediction";

type ColorMode = "evidence" | "model";
interface MapProject {
  project: ProjectListItem;
  signal: ProjectRiskSignalData | null;
  utility: string | null;
  enriched: boolean;
}
const basemap = getBasemapConfig(import.meta.env.VITE_CARTO_BASEMAP_API_KEY);
const STATES_URL = "https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json";
const tone = (item: MapProject, mode: ColorMode) => tierColor(mode === "evidence" ? item.signal?.risk_signal_tier ?? null : item.project.risk_tier);
const tier = (item: MapProject, mode: ColorMode) => mode === "evidence" ? item.signal?.risk_signal_tier ?? (item.enriched ? "unavailable" : "loading") : item.project.risk_tier;

function projectIcon(item: MapProject, mode: ColorMode, selected: boolean, layers: Record<MapLayerId, boolean>) {
  const radius = markerRadius(item.project.modeled_primary_load_mw);
  const flags = classifyMapRecord(item);
  const overlays = MAP_LAYERS.filter(layer => layer.id !== "projects" && layers[layer.id] && flags[layer.id])
    .map(layer => `<span aria-hidden="true" class="map-vector-overlay map-overlay-${layer.id}" style="--overlay-risk:${tierColor(item.project.risk_tier)}"></span>`).join("");
  return L.divIcon({
    className: `project-marker-icon ${selected ? "is-selected" : ""}`,
    // Color is a fixed CSS token; no API strings are inserted into HTML.
    html: `<span class="map-project-dot" style="--marker-color:${tone(item, mode)};width:${radius * 2}px;height:${radius * 2}px">${overlays}</span>`,
    iconSize: [radius * 2, radius * 2], iconAnchor: [radius, radius], popupAnchor: [0, -radius - 4],
  });
}
function Field({ label, children, color }: { label: string; children: React.ReactNode; color?: string }) {
  return <div className="map-field"><dt>{label}</dt><dd style={{ color }}>{children}</dd></div>;
}
function MapBehavior({ selected, focusToken, points, fitToken, onReady, pickMode, onPick }: {
  selected: ProjectListItem | null; focusToken: number; points: ProjectListItem[]; fitToken: number;
  onReady: () => void; pickMode: boolean; onPick: (lat: number, lng: number) => void;
}) {
  const map = useMap();
  useMapEvents({ click: e => { if (pickMode) onPick(e.latlng.lat, e.latlng.lng); } });
  useEffect(() => { map.whenReady(onReady); }, [map]);
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map]);
  useEffect(() => {
    if (selected && isMappable(selected)) map.setView([Number(selected.latitude), Number(selected.longitude)], Math.max(map.getZoom(), 7), { animate: false });
  }, [map, focusToken]);
  useEffect(() => {
    if (!fitToken) return;
    if (points.length) map.fitBounds(L.latLngBounds(points.map(p => [Number(p.latitude), Number(p.longitude)])), { padding: [55, 55], maxZoom: 9, animate: false });
    else map.setView([38.5, -96.5], 4);
  }, [map, fitToken]);
  return null;
}

export function MapPage() {
  const [items, setItems] = useState<MapProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [mapReady, setMapReady] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focusToken, setFocusToken] = useState(0);
  const [fitToken, setFitToken] = useState(0);
  const [colorMode, setColorMode] = useState<ColorMode>("evidence");
  const [query, setQuery] = useState("");
  const [state, setState] = useState("all");
  const [risk, setRisk] = useState("all");
  const [signal, setSignal] = useState("all");
  const [minLoad, setMinLoad] = useState("");
  const [maxLoad, setMaxLoad] = useState("");
  const [showApproximate, setShowApproximate] = useState(true);
  const [layers, setLayers] = useState(defaultMapLayers);
  const [showStates, setShowStates] = useState(false);
  const [boundaries, setBoundaries] = useState<GeoJSON.GeoJsonObject | null>(null);
  const [geoError, setGeoError] = useState(false);
  const [editing, setEditing] = useState<ProjectListItem | null>(null);
  const [pickMode, setPickMode] = useState(false);
  const [picked, setPicked] = useState<{ latitude: number; longitude: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(null); setItems([]); setSelectedId(null);
    getProjects().then(async projects => {
      if (cancelled) return;
      setItems(projects.map(project => ({ project, signal: null, utility: null, enriched: false })));
      setLoading(false);
      await Promise.allSettled(projects.map(async project => {
        const [signalResult, enrichment] = await Promise.allSettled([getProjectRiskSignal(project.project_id), getProject(project.project_id)]);
        if (cancelled) return;
        setItems(current => current.map(item => item.project.project_id !== project.project_id ? item : {
          ...item, enriched: true,
          signal: signalResult.status === "fulfilled" ? signalResult.value : null,
          utility: enrichment.status === "fulfilled" ? (enrichment.value.utility ?? enrichment.value.phases.find(phase => phase.utility)?.utility ?? null) : null,
        }));
      }));
    }).catch(() => { if (!cancelled) { setError("Project data could not be loaded. Check the local API and try again."); setLoading(false); } });
    return () => { cancelled = true; };
  }, [reload]);

  // Optional layer: no remote boundary request until the analyst enables it.
  useEffect(() => {
    if (!showStates || boundaries) return;
    const controller = new AbortController();
    setGeoError(false);
    fetch(STATES_URL, { signal: controller.signal }).then(response => {
      if (!response.ok) throw new Error("Boundary layer unavailable");
      return response.json();
    }).then(setBoundaries).catch(() => { if (!controller.signal.aborted) setGeoError(true); });
    return () => controller.abort();
  }, [showStates, boundaries]);

  const states = useMemo(() => [...new Set(items.map(item => item.project.state).filter(Boolean))].sort(), [items]);
  const filtered = useMemo(() => items.filter(item => {
    const p = item.project;
    const text = `${p.project_name} ${p.developer ?? ""} ${p.county ?? ""} ${p.state}`.toLowerCase();
    return text.includes(query.trim().toLowerCase()) && (state === "all" || p.state === state)
      && (risk === "all" || p.risk_tier === risk) && (signal === "all" || item.signal?.risk_signal_tier === signal)
      && (minLoad === "" || (Number.isFinite(p.modeled_primary_load_mw) && p.modeled_primary_load_mw >= Number(minLoad)))
      && (maxLoad === "" || (Number.isFinite(p.modeled_primary_load_mw) && p.modeled_primary_load_mw <= Number(maxLoad)));
  }), [items, query, state, risk, signal, minLoad, maxLoad]);
  const onMap = visibleMapRecords(filtered, showApproximate, layers);
  const layerCounts = mapLayerCounts(filtered, showApproximate);
  const selected = filtered.find(item => item.project.project_id === selectedId) ?? null;
  // Filtering away a selection clears it rather than silently restoring it later.
  useEffect(() => { if (selectedId && !selected) setSelectedId(null); }, [selectedId, selected]);
  const totalLoad = filtered.reduce((sum, item) => sum + (Number.isFinite(item.project.modeled_primary_load_mw) ? Math.max(0, item.project.modeled_primary_load_mw) : 0), 0);
  const highRisk = filtered.filter(item => item.project.risk_tier === "high").length;
  const loadedSignals = filtered.filter(item => item.signal !== null).length;
  const activeFilters = !!query || state !== "all" || risk !== "all" || signal !== "all" || !!minLoad || !!maxLoad;
  function clearFilters() { setQuery(""); setState("all"); setRisk("all"); setSignal("all"); setMinLoad(""); setMaxLoad(""); }
  function selectItem(item: MapProject, pan = false) { setSelectedId(item.project.project_id); if (pan && layers.projects && isMappable(item.project, showApproximate)) setFocusToken(value => value + 1); }
  function closeEditor() { setEditing(null); setPickMode(false); setPicked(null); }
  function applyUpdatedProject(updated: ProjectDetail) {
    setItems(current => current.map(item => item.project.project_id === updated.project_id ? { ...item, project: { ...item.project, ...updated } } : item));
    closeEditor();
  }

  return <section className="map-console" aria-label="Build constraint intelligence">
    <header className="map-intelligence-header">
      <div><p className="map-eyebrow">POWER RISK / SPATIAL INTELLIGENCE</p><h1>Build-constraint intelligence<span className="map-heading-dot">.</span></h1><p className="map-subtitle">Locate exposure. Inspect the evidence. Resolve the unknowns.</p></div>
      <div className="map-header-links"><span className="map-readonly">PROJECT INTELLIGENCE</span><Link to="/constraint-dashboard">Constraint dashboard ↗</Link></div>
    </header>
    <div className="map-stat-strip" aria-label="Filtered project statistics">
      <div><span>Mapped / filtered</span><strong>{loading ? "—" : `${onMap.length} / ${filtered.length}`}</strong><small>Projects in this view</small></div>
      <div><span>Modeled load</span><strong>{loading ? "—" : totalLoad > 0 ? formatLoad(totalLoad) : "—"} <em>MW</em></strong><small>Reported modeled load · filtered projects</small></div>
      <div className="map-stat-hot"><span>High model risk</span><strong>{loading ? "—" : highRisk.toString().padStart(2, "0")}</strong><small>Model tier · not verified constraints</small></div>
      <div><span>Signal coverage</span><strong>{loading ? "—" : `${loadedSignals} / ${filtered.length}`}</strong><small>Projects with signal data available</small></div>
    </div>
    <div className={`map-workspace ${selected ? "has-selection" : ""}`}>
      <aside className="map-browser" aria-label="Project filters and list">
        <div className="map-panel-heading"><h2>Explore projects</h2><span>{filtered.length.toString().padStart(2, "0")}</span></div>
        <div className="map-filter-panel">
          <label className="map-search"><span>Search projects</span><input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Project, developer, location…" /></label>
          <div className="map-filter-grid">
            <label>Geography<select value={state} onChange={e => setState(e.target.value)}><option value="all">All states</option>{states.map(s => <option key={s}>{s}</option>)}</select></label>
            <label>Model risk<select value={risk} onChange={e => setRisk(e.target.value)}><option value="all">All tiers</option>{["high", "elevated", "medium", "moderate", "low", "unknown"].map(t => <option key={t} value={t}>{humanize(t)}</option>)}</select></label>
            <label>Evidence signal<select value={signal} onChange={e => setSignal(e.target.value)}><option value="all">All signals</option>{["high", "moderate", "low"].map(t => <option key={t} value={t}>{humanize(t)}</option>)}</select></label>
            <div className="map-load-range"><span>Modeled MW</span><div><input aria-label="Minimum modeled load" type="number" min="0" value={minLoad} onChange={e => setMinLoad(e.target.value)} placeholder="Min"/><input aria-label="Maximum modeled load" type="number" min="0" value={maxLoad} onChange={e => setMaxLoad(e.target.value)} placeholder="Max"/></div></div>
          </div>
          {activeFilters && <button className="map-text-button" onClick={clearFilters}>Reset filters</button>}
        </div>
        <div className="map-list-heading"><span>PROJECT REGISTER</span><span>{onMap.length} mapped</span></div>
        <div className="map-project-list">
          {loading && <div className="map-list-state" role="status">Loading project register…</div>}
          {!loading && !error && !filtered.length && <div className="map-list-state">No projects match these filters.<button className="map-text-button" onClick={clearFilters}>Reset filters</button></div>}
          {filtered.map(item => <button key={item.project.project_id} className={`map-project-row ${selectedId === item.project.project_id ? "selected" : ""}`} aria-pressed={selectedId === item.project.project_id} onClick={() => selectItem(item, true)} style={{ "--row-signal": tone(item, colorMode) } as CSSProperties}>
            <span className="map-row-top"><span className="map-tier-label">{humanize(tier(item, colorMode))} {colorMode === "model" ? "risk" : "signal"}</span><span>{formatLoad(item.project.modeled_primary_load_mw)} MW</span></span>
            <strong>{item.project.project_name}</strong><span className="map-row-location">{[item.project.county, item.project.state].filter(Boolean).join(", ") || "Location unknown"}</span>
            <span className="map-row-bottom"><span>{humanize(item.project.lifecycle_state)}</span><span>{!layers.projects ? "Markers hidden" : isMappable(item.project, showApproximate) ? "Locate ↗" : isMappable(item.project) ? "Approx. hidden" : "Unmapped"}</span></span>
          </button>)}
        </div>
        <div className="map-register-foot">{filtered.length - onMap.length} not mapped in this view · coordinates or project markers may be hidden.</div>
      </aside>
      <div className="map-stage">
        <div className="map-canvas-toolbar">
          <div className="map-segmented" role="group" aria-label="Marker color mode"><button aria-pressed={colorMode === "evidence"} onClick={() => setColorMode("evidence")}>Evidence signal</button><button aria-pressed={colorMode === "model"} onClick={() => setColorMode("model")}>Model risk</button></div>
          <button className="map-fit-button" onClick={() => setFitToken(value => value + 1)}>Fit view</button>
        </div>
        <MapContainer center={[38.5, -96.5]} zoom={4} className={`map-canvas ${basemap.fallback ? "map-fallback" : ""}`} zoomControl>
          <TileLayer url={basemap.url} attribution={basemap.attribution} maxZoom={basemap.maxZoom} />
          {showStates && boundaries && <GeoJSON data={boundaries} style={{ color: "#7d90a5", weight: 1, fillOpacity: 0, opacity: 0.6 }} />}
          <MapBehavior selected={selected && layers.projects && isMappable(selected.project, showApproximate) ? selected.project : null} focusToken={focusToken} points={onMap.map(item => item.project)} fitToken={fitToken} onReady={() => setMapReady(true)} pickMode={pickMode} onPick={(latitude, longitude) => setPicked({ latitude, longitude })} />
          {picked && <CircleMarker center={[picked.latitude, picked.longitude]} radius={8} pathOptions={{ color: "var(--map-cyan)" }} />}
          {mapReady && onMap.map(item => <Marker key={item.project.project_id} position={[Number(item.project.latitude), Number(item.project.longitude)]} icon={projectIcon(item, colorMode, item.project.project_id === selectedId, layers)} title={item.project.project_name} alt={item.project.project_name} zIndexOffset={selectedId === item.project.project_id ? 1000 : 0} eventHandlers={{ click: () => selectItem(item), keydown: event => { if (event.originalEvent.key === "Enter") selectItem(item); } }}>
            <Popup className="map-console-popup" minWidth={220} maxWidth={280}><div className="map-popup-content"><span className="map-eyebrow">{humanize(tier(item, colorMode))} {colorMode === "model" ? "model risk" : "evidence signal"}</span><strong>{item.project.project_name}</strong><p>{[item.project.county, item.project.state].filter(Boolean).join(", ")} · {formatLoad(item.project.modeled_primary_load_mw)} MW modeled</p><Link to={`/projects/${item.project.project_id}`}>Open project details ↗</Link></div></Popup>
          </Marker>)}
        </MapContainer>
        {(loading || error || !onMap.length) && <div className={`map-state-card ${error ? "has-error" : ""}`} role={error ? "alert" : "status"}>
          <span className="map-eyebrow">{error ? "DATA CONNECTION" : loading ? "LOADING INTELLIGENCE" : "NO MAPPABLE RECORDS"}</span>
          <h2>{error ? "Map available. Project data unavailable." : loading ? "Building your spatial view…" : "No projects to plot in this view."}</h2>
          <p>{error ?? (loading ? "Loading projects and their existing evidence signals." : "Enable project markers, adjust filters, or include approximate coordinates. Hidden records remain in the project register.")}</p>
          {error ? <button onClick={() => setReload(value => value + 1)}>Retry project data</button> : !loading && activeFilters ? <button onClick={clearFilters}>Reset filters</button> : null}
        </div>}
        <details className="map-layer-control"><summary>Map layers</summary>
          <p className="map-layer-count-note">Eligible in this view · counts can overlap</p>
          {MAP_LAYERS.map(layer => <label className="map-overlay-toggle" key={layer.id} title={layer.description}>
            <input type="checkbox" aria-label={layer.label} checked={layers[layer.id]} disabled={layer.id !== "projects" && !layers.projects} onChange={event => setLayers(current => ({ ...current, [layer.id]: event.target.checked }))}/>
            <span><span className="map-layer-name"><i style={{ background: layer.color }}/>{layer.label}<b aria-label={`${layerCounts[layer.id]} eligible records`}>{layerCounts[layer.id]}</b></span><small>{layer.description}</small></span>
          </label>)}
          <label><input type="checkbox" checked={showApproximate} onChange={e => setShowApproximate(e.target.checked)}/>Include approximate locations</label><label><input type="checkbox" checked={showStates} onChange={e => setShowStates(e.target.checked)}/>State boundaries</label>{showStates && <p>{geoError ? "Boundary layer unavailable. Project markers remain usable." : !boundaries ? "Loading boundaries…" : "State boundaries visible"}</p>}</details>
        <div className="map-legend" aria-label="Map legend"><span>{colorMode === "evidence" ? "SIGNAL" : "RISK"}</span><i style={{ background: "var(--map-hot)" }}/>High<i style={{ background: "var(--map-amber)" }}/>{colorMode === "evidence" ? "Moderate" : "Elevated / medium"}<i style={{ background: "var(--map-slate)" }}/>Low / unknown <span className="map-legend-size">Size = modeled MW</span></div>
      </div>
      {selected && <aside className="map-inspector" aria-label="Selected project details">
        <div className="map-panel-heading"><h2>Project intelligence</h2><button onClick={() => setSelectedId(null)} aria-label="Close project details">×</button></div>
        <div className="map-inspector-body">
          <span className="map-tier-badge" style={{ color: tone(selected, colorMode) }}>{humanize(tier(selected, colorMode))} {colorMode === "evidence" ? "evidence signal" : "model risk"}</span>
          <h2>{selected.project.project_name}</h2><p className="map-inspector-location">{[selected.project.county, selected.project.state].filter(Boolean).join(", ") || "Location unknown"}</p>
          <p className="map-lifecycle">{humanize(selected.project.lifecycle_state)}</p>
          <dl className="map-detail-grid"><Field label="Modeled load">{formatLoad(selected.project.modeled_primary_load_mw)} MW</Field><Field label="Evidence records">{selected.signal?.evidence_summary.evidence_count ?? (selected.enriched ? "Unavailable" : "Loading…")}</Field><Field label="Model risk" color={tierColor(selected.project.risk_tier)}>{humanize(selected.project.risk_tier)}</Field><Field label="Utility">{selected.utility ?? "Unknown"}</Field></dl>
          <section className="map-detail-section"><h3>Evidence-backed signal</h3><p>{selected.signal ? humanize(selected.signal.risk_signal) : selected.enriched ? "Signal data unavailable. No constraint inferred." : "Loading signal data…"}</p>{!!selected.signal?.drivers.length && <ul>{selected.signal.drivers.map((driver, index) => <li key={index}>{humanize(driver)}</li>)}</ul>}<p className="map-caveat">Signal strength and model risk are separate from analyst review status.</p></section>
          <section className="map-detail-section"><h3>Location confidence</h3><dl className="map-detail-grid"><Field label="Coordinate status" color={selected.project.coordinate_status === "verified" ? "var(--map-green)" : undefined}>{humanize(selected.project.coordinate_status ?? "unverified")}</Field><Field label="Precision">{humanize(selected.project.coordinate_precision)}</Field><Field label="Coordinate confidence">{selected.project.coordinate_confidence != null ? selected.project.coordinate_confidence.toFixed(2) : "Unknown"}</Field><Field label="Source">{humanize(selected.project.coordinate_source)}</Field></dl>{["city_centroid", "county_centroid", "state_centroid", "approximate"].includes(selected.project.coordinate_precision ?? "") && <p className="map-location-warning">Approximate location; not an exact site boundary.</p>}</section>
          <details className="map-prediction"><summary>Model prediction</summary><MapPrediction key={selected.project.project_id} projectId={selected.project.project_id}/></details>
          <Link className="map-primary-link" to={`/projects/${selected.project.project_id}`}>Open project details ↗</Link>
          <button className="map-text-button" onClick={() => { setEditing(selected.project); setPicked(null); setPickMode(false); }}>Edit coordinates</button>
        </div>
      </aside>}
    </div>
    <footer className="map-console-footer"><span role="status">{basemap.fallback ? "Fallback basemap active · OpenStreetMap" : "CARTO dark basemap"}</span><span>{basemap.fallback ? "Optional CARTO key available in local setup" : "Provider attribution on map"}</span><span>Existing project data · no downstream actions</span></footer>
    {editing && <div className="map-coordinate-editor" role="dialog" aria-label="Edit project coordinates"><div className="map-panel-heading"><h2>{editing.project_name}</h2><button aria-label="Close coordinate editor" onClick={closeEditor}>×</button></div>{pickMode && <p className="map-location-warning">Click the map to fill coordinates. Changes are not saved until you submit.</p>}<ProjectCoordinateEditor project={editing} pickedCoordinates={picked} onStartPick={() => setPickMode(true)} onCancel={closeEditor} onSaved={applyUpdatedProject}/></div>}
  </section>;
}
