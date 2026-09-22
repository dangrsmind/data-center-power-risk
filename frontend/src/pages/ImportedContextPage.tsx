import { useEffect, useRef, useState } from 'react';
import { getImportedContext, getImportedContextDetail, getImportedContextSummary } from '../api/adapter';
import type { ImportedContextDetail, ImportedContextList, ImportedContextRow, ImportedContextSummary } from '../api/types';
import { safeSourceUrl } from '../config/candidatePresentation';
import '../styles/importedContext.css';

export function ContextSummaryCards({ summary }: { summary: ImportedContextSummary }) {
  const epoch = Object.entries(summary.counts_by_dataset_name).reduce((n, [name, count]) => n + (name.toLowerCase().includes('epoch') ? count : 0), 0);
  return <div className="context-cards">{[
    ['Imported audit rows', summary.total], ['Epoch rows', epoch],
    [`Imported in last ${summary.recent_window_days} days`, summary.recent_row_count],
    ['Rows with warnings', summary.rows_with_warnings], ['Rows with errors', summary.rows_with_errors],
    ['Linked to candidates', summary.linked_candidate_count],
  ].map(([label, value]) => <div key={label} className={label === "Rows with warnings" ? "warning" : label === "Rows with errors" ? "error" : ""}><small>{label}</small><strong>{value}</strong></div>)}</div>;
}

export function ImportedContextDashboard() {
  const [summary, setSummary] = useState<ImportedContextSummary | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => { let active = true; getImportedContextSummary().then(s => { if (active) setSummary(s); }).catch(() => { if (active) setError(true); }); return () => { active = false; }; }, []);
  return <section className="context-panel"><h2><a href="/imported-context">Imported Context →</a></h2>
    <p>Read-only audit inventory. Context rows are not Projects.</p>
    {summary ? <ContextSummaryCards summary={summary} /> : <p>{error ? 'Imported context summary unavailable.' : 'Loading imported context…'}</p>}
  </section>;
}

function Sources({ urls }: { urls: string[] | null }) {
  return <>{(urls || []).map((url, i) => typeof url === 'string' && safeSourceUrl(url) ? <a key={i} href={url} target="_blank" rel="noopener noreferrer">Source {i + 1} ↗ </a> : null)}</>;
}

export function ContextTable({ rows, onDetail }: { rows: ImportedContextRow[]; onDetail: (id: string) => void }) {
  return <div className="context-table-wrap"><table className="context-table"><thead><tr>
    {['Context row', 'Dataset / file', 'Type', 'Duplicate status', 'Warnings / errors', 'Sources / candidate', 'Imported'].map(h => <th key={h}>{h}</th>)}
  </tr></thead><tbody>{rows.map(row => <tr key={row.id}>
    <td><button onClick={() => onDetail(row.id)}>{row.display_name}</button><small>Imported audit row · Not a Project</small></td>
    <td>{row.dataset_name}<small>{row.source_file_basename} · row {row.row_number}</small></td>
    <td><span className="context-badge">{row.record_type}</span></td>
    <td><span className="context-badge neutral">{row.duplicate_status}</span></td>
    <td><span className={`context-badge ${row.warnings_json?.length ? "warning" : "neutral"}`}>{row.warnings_json?.length || 0} warnings</span> <span className={`context-badge ${row.errors_json?.length ? "error" : "neutral"}`}>{row.errors_json?.length || 0} errors</span></td>
    <td><Sources urls={row.source_urls_json} />{row.linked_project_candidate_id && <a className="context-linked" href="/project-candidates" title={row.linked_project_candidate_id}>Linked candidate</a>}</td>
    <td>{new Date(row.created_at).toLocaleString()}</td>
  </tr>)}</tbody></table></div>;
}

export function ImportedContextPage() {
  const [summary, setSummary] = useState<ImportedContextSummary | null>(null);
  const [summaryError, setSummaryError] = useState('');
  const [data, setData] = useState<ImportedContextList | null>(null);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<ImportedContextDetail | null>(null);
  const [detailError, setDetailError] = useState('');
  const detailPanel = useRef<HTMLElement>(null);
  useEffect(() => { if (selected) { detailPanel.current?.scrollIntoView({ block: 'start' }); detailPanel.current?.focus({ preventScroll: true }); } }, [selected]);
  useEffect(() => { let active = true; getImportedContextSummary().then(s => { if (active) setSummary(s); }).catch(() => { if (active) setSummaryError('Summary unavailable. You can still browse rows.'); }); return () => { active = false; }; }, []);
  useEffect(() => {
    let active = true; setLoading(true); setError('');
    const timer = setTimeout(() => getImportedContext({ ...filters, limit: '50', offset: String(offset) }).then(result => { if (active) setData(result); }).catch(e => { if (active) setError(String(e)); }).finally(() => { if (active) setLoading(false); }), 200);
    return () => { active = false; clearTimeout(timer); };
  }, [filters, offset]);
  useEffect(() => {
    let active = true; setDetail(null); setDetailError('');
    if (selected) getImportedContextDetail(selected).then(d => { if (active) setDetail(d); }).catch(e => { if (active) setDetailError(String(e)); });
    return () => { active = false; };
  }, [selected]);
  function filter(key: string, value: string) { setOffset(0); setFilters(old => { const next = { ...old }; if (value) next[key] = value; else delete next[key]; return next; }); }
  function select(key: string, label: string, options: string[]) { return <label>{label}<select value={filters[key] || ''} onChange={e => filter(key, e.target.value)}><option value="">All</option>{options.map(v => <option key={v}>{v}</option>)}</select></label>; }
  return <main className="context-page"><h1>Imported Context</h1><p>Read-only context and imported audit rows. These rows are not Projects; viewing them does not promote or verify anything.</p>
    {summary && <ContextSummaryCards summary={summary} />}{summaryError && <p role="status">{summaryError}</p>}
    <div className="context-filters">
      {select('dataset_name', 'Dataset', Object.keys(summary?.counts_by_dataset_name || {}))}
      {select('source_file', 'Source file', Object.keys(summary?.counts_by_source_file || {}))}
      {select('duplicate_status', 'Duplicate status', Object.keys(summary?.counts_by_duplicate_status || {}))}
      <label>Search<input value={filters.q || ''} onChange={e => filter('q', e.target.value)} placeholder="Search raw / normalized data and URLs" /></label>
      {(['has_warnings', 'has_errors', 'has_candidate'] as const).map(key => <label key={key}>{key === 'has_candidate' ? 'Linked candidate' : key === 'has_warnings' ? 'Warnings' : 'Errors'}<select value={filters[key] || ''} onChange={e => filter(key, e.target.value)}><option value="">All</option><option value="true">Present</option><option value="false">Absent</option></select></label>)}
      <button onClick={() => { setFilters({}); setOffset(0); }}>Clear filters</button>
    </div>
    <p>Newest first · {data?.total ?? '…'} matching rows</p>
    {loading ? <p role="status">Loading context rows…</p> : error ? <p role="alert">{error}</p> : data && <><ContextTable rows={data.items} onDetail={setSelected} />{!data.items.length && <p>No context rows match these filters.</p>}<div className="context-pagination"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button><span>{data.total ? offset + 1 : 0}–{Math.min(offset + 50, data.total)} of {data.total}</span><button disabled={offset + 50 >= data.total} onClick={() => setOffset(offset + 50)}>Next</button></div></>}
    {selected && <section ref={detailPanel} tabIndex={-1} className="context-panel" aria-label="Context row detail"><button onClick={() => setSelected(null)}>Close detail</button><h2>Context row detail</h2><p>Imported audit row · Not a Project</p>
      {detailError ? <p role="alert">{detailError}</p> : detail ? <><h3>{detail.display_name}</h3><Sources urls={detail.source_urls_json} />{detail.linked_candidate && <p className="context-linked">Linked candidate: {detail.linked_candidate.candidate_name} ({detail.linked_candidate.status})</p>}<h3>Metadata and parsed source data</h3><pre>{JSON.stringify(detail, null, 2)}</pre></> : <p>Loading detail…</p>}
    </section>}
  </main>;
}
