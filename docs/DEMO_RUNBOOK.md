# Demo Runbook

This runbook creates a reproducible local demo from a clean SQLite database. The demo data is loaded from committed CSVs under `data/demo/`; it does not scrape live sources at demo time.

The project is a data center build-constraint risk system. Grid interconnection and transmission capacity remain important, but the demo should also be read as a workflow for surfacing onsite generation, air/emissions, water/cooling, community, legal, permitting, cost, and schedule credibility risks when those signals are supported by public sources.

## Prerequisites

- Python virtualenv created and activated under `backend/.venv`
- Node.js / npm available for the frontend

## 1. Update the DB Schema

```bash
cd backend
source .venv/bin/activate
DATABASE_URL=sqlite:///local.db alembic upgrade head
```

## 2. Load Demo Data

```bash
DATABASE_URL=sqlite:///local.db python scripts/load_demo_dataset.py --reset
```

The loader upserts by `canonical_name` + `state`. Running it repeatedly is safe. `--reset` removes only demo-owned rows before reloading them.

Expected summary fields:

- `rows_read`
- `projects_created`
- `projects_updated`
- `rows_skipped`
- `validation_errors`

## 3. Load Demo Evidence

```bash
DATABASE_URL=sqlite:///local.db python scripts/load_demo_evidence.py
```

Loads curated source-backed evidence from `data/demo/demo_evidence_v0_1.csv` and links it to demo projects for the Project Detail Evidence tab. Re-running is safe; existing evidence and claim links are updated in place.

Expected summary fields:

- `rows_read`
- `evidence_created`
- `evidence_updated`
- `rows_skipped`
- `validation_errors`

## 4. Run Demo Predictions

```bash
DATABASE_URL=sqlite:///local.db python scripts/run_demo_predictions.py
```

Scores demo-marked projects with `baseline_power_delay_v0_2` and stores one prediction row per project/model/version. Re-running is safe; existing rows are updated in place.

Expected summary fields:

- `projects_scored`
- `predictions_created`
- `predictions_updated`
- `errors`

To refresh one promoted or demo project without running the batch scorer:

```bash
DATABASE_URL=sqlite:///local.db python scripts/run_project_prediction.py --project-id <PROJECT_UUID>
```

This uses the same deterministic baseline and upserts only that project's prediction. The API equivalent is `POST /projects/<PROJECT_UUID>/prediction/run`.

## 5. Run Backend Healthcheck

```bash
DATABASE_URL=sqlite:///local.db python scripts/demo_healthcheck.py
```

Validates the demo database, project API service path, stored/computed predictions, coordinate metadata, and evidence endpoint behavior. Exits non-zero only when the summary includes errors.

Expected output (all zeros for errors and warnings):

```json
{
  "errors": [],
  "evidence_checked": 2,
  "predictions_checked": 8,
  "projects_checked": 8,
  "projects_with_coordinates": 8,
  "projects_with_evidence": 2,
  "warnings": []
}
```

## Optional: Run Generic Web-Search Discovery

Generic web-search discovery is disabled by default and never creates projects directly. Dry-run lists planned queries only:

```bash
python scripts/validate_source_registry.py
python scripts/run_public_discovery.py --dry-run --report
python scripts/run_public_discovery.py --dry-run --report --report-format json
python scripts/run_public_discovery.py --dry-run --report --exclude-generic
python scripts/run_public_discovery.py --dry-run --report --priority high --exclude-generic --max-planned-queries 30
python scripts/run_public_discovery.py --dry-run --report --category grid_transmission --scope location-scoped
python scripts/run_public_discovery.py --dry-run --report --report-output ../data/discovery_plan_snapshots/full-plan.txt
python scripts/run_live_discovery_smoke.py --list-recipes
python scripts/run_live_discovery_smoke.py --recipe grid-transmission-location-scoped --dry-run
python scripts/run_public_discovery.py --dry-run
```

The dry-run report is the first review step before any live or paid search. It shows total planned query count, estimated web-search requests, estimated search cost, counts by adapter/provider/source type/risk category/geography/scope, each query, source registry metadata, and warnings for high-count, duplicate, generic, or likely overbroad query templates. It is read-only: it does not call Brave, fetch URLs, use a database, write runtime files, create Projects, create ProjectCandidates, or promote anything.

Use report filters to review a narrower safe plan before any paid provider call: `--category`, `--source-type`, `--priority`, `--scope`, `--geography`, `--adapter`, `--source-id`, `--exclude-generic`, and `--max-planned-queries`. The report shows original, filtered, and retained query counts; caps are applied after filters; and zero-match filter combinations return an explicit warning rather than an unfiltered plan.

Estimated cost is a preflight planning estimate, not billing truth. The default assumes Brave Search API Search at `0.005` USD/request, configurable with `WEB_SEARCH_COST_USD_PER_REQUEST=...` or `--search-cost-usd-per-request ...`; CLI values override the environment. Verify Brave dashboard pricing, credits, and usage before running live discovery.

Save local discovery plan snapshots with `--report-output` when comparing scoped plans. These files belong under the ignored runtime directory `data/discovery_plan_snapshots/`, with descriptive names such as `full-plan.txt`, `exclude-generic.txt`, `high-exclude-generic-30.json`, or `grid-transmission-location-scoped.json`. Snapshots are pre-live planning artifacts only; they are not evidence, discovered sources, claims, Projects, or ProjectCandidates.

Recommended snapshot workflow:

```bash
cd backend
source .venv/bin/activate

python scripts/validate_source_registry.py

python scripts/run_public_discovery.py --dry-run --report \
  --report-output ../data/discovery_plan_snapshots/full-plan.txt

python scripts/run_public_discovery.py --dry-run --report \
  --exclude-generic \
  --report-output ../data/discovery_plan_snapshots/exclude-generic.txt

python scripts/run_public_discovery.py --dry-run --report \
  --priority high \
  --exclude-generic \
  --max-planned-queries 30 \
  --report-format json \
  --report-output ../data/discovery_plan_snapshots/high-exclude-generic-30.json

python scripts/run_public_discovery.py --dry-run --report \
  --category grid_transmission \
  --scope location-scoped \
  --report-format json \
  --report-output ../data/discovery_plan_snapshots/grid-transmission-location-scoped.json
```

Compare snapshots manually with `diff`, `jq`, or your editor, then keep live Brave disabled unless the session has explicit approval for a paid provider call.

The first recommended live-smoke recipe is `grid_transmission` plus `location-scoped`. It retains about 10 planned queries in the current registry, estimates 8 live generic web-search requests, costs about 0.04 USD at the default assumption, avoids broad generic templates, and focuses on official or regulatory targets. Save and review this snapshot first:

```bash
python scripts/run_public_discovery.py --dry-run --report \
  --category grid_transmission \
  --scope location-scoped \
  --max-planned-queries 30 \
  --report-format json \
  --report-output ../data/discovery_plan_snapshots/final-grid-transmission-location-scoped.json
```

Only after explicit cost approval, the matching live command is:

```bash
WEB_SEARCH_PROVIDER=brave WEB_SEARCH_API_KEY="$BRAVE_SEARCH_API_KEY" WEB_SEARCH_MAX_RESULTS=5 \
python scripts/run_public_discovery.py \
  --category grid_transmission \
  --scope location-scoped \
  --max-planned-queries 30 \
  --confirm-live-search
```

Other focused official-source recipes use the same cap and confirmation:

- Texas PUCT: `--source-id texas_puct_large_load_data_center_search --max-planned-queries 30 --confirm-live-search`
- ERCOT: `--source-id ercot_large_load_data_center_search --max-planned-queries 30 --confirm-live-search`
- Virginia SCC: `--source-id virginia_scc_data_center_large_load_dockets --max-planned-queries 30 --confirm-live-search`
- Pacific Northwest utility: `--source-id pacific_northwest_utility_data_center_search --max-planned-queries 30 --confirm-live-search`

The wrapper helper lists recipes and can dry-run a recipe plan without making provider calls:

```bash
python scripts/run_live_discovery_smoke.py --list-recipes
python scripts/run_live_discovery_smoke.py --recipe grid-transmission-location-scoped --dry-run
```

After explicit approval for possible provider cost and with `WEB_SEARCH_PROVIDER=brave` plus `WEB_SEARCH_API_KEY` set in the local shell, the matching guarded wrapper command is:

```bash
python scripts/run_live_discovery_smoke.py --recipe grid-transmission-location-scoped --confirm-live-search
```

Inspect live smoke output before ingest. Every discovered source row should preserve `source_registry_id`, `adapter_id`, `source_type`, `geography`, `discovery_method`, `source_query`, `publisher`, `source_title`, and a plain HTTP/HTTPS `source_url`; snippets or notes should be present when available. Adapter results should filter obvious irrelevant records before output. SCC public-comment form URLs are valid but weak evidence; DocketSearch case-detail, SCC news/hearing notice, and transmission-project pages are preferred when already present in SearchStax metadata. Public-comment URLs may be retained as fallback/provenance, but they should not be treated as strong project evidence. Live discovery output is not final Project evidence, and ingest remains a separate deliberate step.

For the discovered-source review console, use the computed review queue as triage guidance only. `priority_desc`, `priority_bucket`, and `min_priority_score` help put official filings, planning records, project-like snippets, weak URL fallbacks, and likely noisy pages into a faster review order, but the score is a transparent heuristic derived from existing fields and is not persisted. Analyst `review_status` remains authoritative. Bulk triage can mark selected visible rows `useful`, `maybe`, `noisy`, `weak`, `rejected`, or `unreviewed`, and can replace or append notes, but it still writes only source-review metadata. Weak URL-quality warnings remain separate from analyst status: a public-comment or fallback URL can be useful context, and a primary-looking URL can still be noisy. Claim extraction, candidate generation, verification, admission, and promotion remain outside this queue workflow; a later extraction pass should default to reviewed `useful` or `maybe` sources and can prefer high-signal reviewed sources.

The dry-run JSON includes `planned_search_query_count` and `planned_generic_web_search_query_count`; report JSON also includes `estimated_web_search_requests`, `estimated_search_cost_usd`, `search_cost_usd_per_request`, and `pricing_note`. Use `estimated_web_search_requests` as the approximate Brave Search API request count before running live discovery. The targeted official-source and build-constraint expansions now plan 113 generic-provider queries per full run.

For a fixture-backed local check:

```bash
WEB_SEARCH_PROVIDER=mock python scripts/run_public_discovery.py \
  --priority high \
  --source-type utility_large_load_filings \
  --max-planned-queries 30 \
  --confirm-live-search
```

For live Brave Search API discovery, keep the key in your shell environment and do not commit it. Do not run this command unless the session has explicit approval for possible provider cost:

```bash
WEB_SEARCH_PROVIDER=brave WEB_SEARCH_API_KEY="$BRAVE_SEARCH_API_KEY" WEB_SEARCH_MAX_RESULTS=5 \
python scripts/run_public_discovery.py \
  --priority high \
  --exclude-generic \
  --max-planned-queries 30 \
  --confirm-live-search
```

Any non-dry-run discovery command is blocked unless it passes `--confirm-live-search`, at least one limiting filter, and `--max-planned-queries`. Caps above 30 require `--allow-large-live-run`. The preflight prints provider, original/filtered/retained query counts, estimated web-search requests, estimated search cost, active filters, cap metadata, counts by source type/risk category/scope, and a reminder to save a snapshot first. Confirmed live runs write redacted metadata, including estimated cost fields, under ignored `data/discovery_runs/live_run_metadata/`.

Any discovered records are written under ignored `data/discovery_runs/` runtime output and still need discovered-source ingestion, claim extraction, verification, and review before any project can be promoted. Do not run live Brave unless explicitly approved for the session; dry-run and mock runs are the default safe checks. Recommended workflow before paid search: validate the registry, save and inspect a scoped discovery plan snapshot, review high-count and overbroad warnings, run public discovery dry-run, and only then consider a confirmed capped live search with explicit cost approval.

Discovery and triage may surface build-constraint context such as grid interconnection, transmission capacity, substations, load requests, onsite or behind-the-meter generation, diesel or backup generators, gas turbine generation, fuel cells, nuclear or SMR proposals, fuel supply, air permitting, emissions/NOx compliance, water/cooling, wastewater, drought, community opposition, public hearings, zoning/land use, moratoria, litigation, utility regulatory approval, tax incentives, cost/financing, schedule delay/pause/cancellation, or political/institutional resistance. These signals are review cues, not final project facts.

ProjectCandidates may also show an energy strategy badge such as `unknown`, `grid_plus_backup`, `grid_plus_onsite`, `diesel_generation`, `dedicated_gas_generation`, `fuel_cell`, `nuclear_or_smr`, or `hybrid_power`. This is a review signal only. Unknown is acceptable; substations, transmission, utility service, or interconnection text alone should not be read as onsite generation. Backup generators are not primary power. Nuclear or SMR proposals should be treated as uncertain because regulatory, cost, schedule, and public-acceptance risks remain unresolved unless a source says otherwise.

ProjectCandidates may also show siting-friction signals for categories such as public hearing, community opposition, zoning or land use, litigation, moratorium, permit delay, air/emissions, water/cooling, cost/financing, or political opposition. These are review signals only. Public hearings do not automatically mean opposition; cost signals do not automatically prove delay; water/cooling and air/emissions risks need source support; and litigation, moratorium, or political opposition should require explicit source language. These signals do not bypass verification or guarded promotion.

Live discovery outputs may include duplicate `source_url` values across query patterns or repeat runs. Ingestion is expected to be duplicate-safe and idempotent by `source_url`: duplicate input URLs and already-ingested URLs are skipped unless safe metadata updates are requested with `--allow-existing`.

Guarded live-output ingest flow:

```bash
python scripts/run_live_discovery_smoke.py --recipe grid-transmission-location-scoped --dry-run

# Only after explicit approval for possible provider cost:
python scripts/run_live_discovery_smoke.py --recipe grid-transmission-location-scoped --confirm-live-search

# Inspect the reviewed output file before ingest:
python scripts/ingest_public_discovered_sources.py \
  --input ../data/discovery_runs/20260828T193254Z/discovered_sources.json \
  --dry-run

# Confirmed ingest is a separate decision:
python scripts/ingest_public_discovered_sources.py \
  --input ../data/discovery_runs/20260828T193254Z/discovered_sources.json \
  --confirm
```

The dry-run ingest report writes nothing and distinguishes structural blockers, duplicate input URLs, already-ingested URLs, would-create/would-update counts, and review-only weak SCC public-comment fallback warnings. Do not ingest old pre-hardening runs. Claim extraction, candidate generation, verification, auto-admit, and promotion remain separate steps.

After confirmed ingest, inspect stored discovered-source rows through the read-only `/discovered-sources` analyst page or `GET /discovered-sources` plus `GET /discovered-sources/summary`. Filter by discovery run, registry, adapter, source type, geography, status, publisher, URL quality, weak URL quality, or search text before starting claim extraction or candidate generation. SCC public-comment form and fallback-reference warnings are review cues only; they do not create Projects, ProjectCandidates, claims, verification decisions, or promotions.

## Optional: Import Manual CSV Datasets

Manual CSV imports are disabled-by-default review inputs for external datasets. Use them as a two-step workflow:

1. Audit-only import stores imported row provenance and dedupe status.
2. Opt-in candidate creation creates or links only reviewable ProjectCandidates.

Dry-run writes nothing and reports mapping, warnings, duplicate status counts, and unmapped columns:

```bash
cd backend
DATABASE_URL=sqlite:///local.db python scripts/import_csv_dataset.py --dataset epoch_frontier --input ../data/imports/manual_csv/epoch/data_centers.csv
DATABASE_URL=sqlite:///local.db python scripts/import_csv_dataset.py --dataset fractracker_open_us --input ../data/imports/manual_csv/fractracker/fractracker_db_output_v2.csv
```

To dry-run candidate creation without writing anything:

```bash
DATABASE_URL=sqlite:///local.db python scripts/import_csv_dataset.py --dataset epoch_frontier --input ../data/imports/manual_csv/epoch/data_centers.csv --create-candidates
DATABASE_URL=sqlite:///local.db python scripts/import_csv_dataset.py --dataset fractracker_open_us --input ../data/imports/manual_csv/fractracker/fractracker_db_output_v2.csv --create-candidates
```

To persist only imported row audit records:

```bash
DATABASE_URL=sqlite:///local.db python scripts/import_csv_dataset.py --dataset epoch_frontier --input ../data/imports/manual_csv/epoch/data_centers.csv --confirm
```

To additionally create review-only ProjectCandidates, pass `--create-candidates` with `--confirm`. Candidate creation requires a name, at least one location signal, and source/dataset provenance. Rows that fail those checks remain imported audit rows but do not become candidates. Matching rows link to existing ProjectCandidates when the dedupe signal is exact or likely; uncertain matches are preserved as warnings for analyst review. This never creates Projects, never promotes candidates, and never marks candidates `auto_admit_eligible`:

```bash
DATABASE_URL=sqlite:///local.db python scripts/import_csv_dataset.py --dataset epoch_frontier --input ../data/imports/manual_csv/epoch/data_centers.csv --confirm --create-candidates --source-url https://epoch.ai/data/frontier-data-centers --citation "Epoch AI Frontier Data Centers"
```

After creating CSV-backed candidates, run triage to rank the review queue:

```bash
DATABASE_URL=sqlite:///local.db python scripts/triage_project_candidates.py --confirm
```

Triage uses dataset provenance, source URLs, location, load, developer/operator, citation, license notes, and conservative build-constraint signals as review-priority cues only. It does not verify, promote, or admit candidates. It also does not overwrite analyst review decisions.

If CSV-imported candidate metadata includes explicit power/generator wording, triage can classify the energy strategy from the persisted candidate metadata without needing raw CSV files in the repo. Treat the classification as analyst-reviewable context, not as confirmation that a campus is viable or publicly verified.

If CSV-imported metadata includes explicit siting-friction wording, triage can surface bounded siting categories and warnings from persisted candidate metadata. Treat them as analyst-reviewable context, not as final verification or delay proof.

Dashboards should use the read-only constraint summary endpoint instead of aggregating the full candidate list client-side:

```bash
curl http://127.0.0.1:8000/project-candidates/constraint-summary
```

The endpoint returns candidate review counts by status, verification, triage tier, review decision, CSV/web provenance, energy strategy, energy risk tags, siting-friction categories, and siting-friction warnings, plus a bounded top review-priority candidate list. These counts are review signals only; they do not verify projects, imply promotion, or change guarded admission rules.

If the candidate table is empty, or candidate metadata is incomplete or malformed, the endpoint should still return HTTP 200 with zero counts, empty count objects, and an empty top-candidate list. The constraint dashboard treats that response as an empty review queue. A stale local `backend/local.db` may still report an Alembic revision such as `20260616_0016` that is not present in the repository; verify migrations against a fresh temp SQLite DB instead of rewriting migrations to match stale local runtime state.

Important causal pathways to watch during review:

- Grid constraints can push a campus toward onsite generation or hybrid grid-plus-onsite systems.
- Onsite generation can create air permit, emissions, fuel supply, cost, and community opposition risk.
- Community opposition can lead to litigation, zoning delay, or political/institutional resistance.
- Nuclear or SMR proposals can reduce grid dependence while increasing regulatory, schedule, cost, and public-acceptance uncertainty.

In the Project Candidates UI, expand a candidate row to set, update, or clear an analyst review decision. Notes and reviewer are optional; blank values are stored as empty metadata. Decisions such as `needs_source`, `needs_location`, `likely_duplicate`, `ready_for_verification`, and rejected/keep-under-review labels are workflow metadata only. They never create Projects, never promote, never delete candidates, and never merge duplicates. `ready_for_verification` still requires the normal verifier; it is not an override. Rejected labels leave the candidate record in place for auditability, and `likely_duplicate` marks review intent without merging records.

The API equivalent is:

```bash
curl -X PATCH http://127.0.0.1:8000/project-candidates/<CANDIDATE_UUID>/review-decision \
  -H 'Content-Type: application/json' \
  -d '{"review_decision":"needs_source","review_notes":"Need official utility interconnection or permit source.","reviewed_by":"analyst"}'
```

To clear a decision, send `null` or an empty string for `review_decision`; whitespace-only notes or reviewer values are normalized to empty metadata:

```bash
curl -X PATCH http://127.0.0.1:8000/project-candidates/<CANDIDATE_UUID>/review-decision \
  -H 'Content-Type: application/json' \
  -d '{"review_decision":null,"review_notes":null,"reviewed_by":null}'
```

Raw CSVs under `data/imports/manual_csv/`, local databases, and runtime outputs should remain uncommitted. The public-source rule still applies: imported rows can become review candidates only when a source URL or source document is preserved.

## Optional: Live/Mock Discovery Smoke Workflow

The smoke wrapper runs the manual discovery pipeline in controlled opt-in steps. It never promotes candidates, never passes `--confirm` to auto-admit, and reports provider state without printing API keys.

Mock, no API key:

```bash
WEB_SEARCH_PROVIDER=mock DATABASE_URL=sqlite:///local.db python scripts/run_live_discovery_smoke.py
WEB_SEARCH_PROVIDER=mock DATABASE_URL=sqlite:///local.db python scripts/run_live_discovery_smoke.py --ingest --extract-claims --generate-candidates --verify-candidates --auto-admit-dry-run --healthcheck
```

Live Brave, with local shell env only:

```bash
export WEB_SEARCH_PROVIDER=brave
export WEB_SEARCH_API_KEY='...'
export WEB_SEARCH_MAX_RESULTS=3
DATABASE_URL=sqlite:///local.db python scripts/run_live_discovery_smoke.py
DATABASE_URL=sqlite:///local.db python scripts/run_live_discovery_smoke.py --ingest --extract-claims --generate-candidates --verify-candidates --auto-admit-dry-run --healthcheck
```

Brave API usage may create incremental API cost, so keep `WEB_SEARCH_MAX_RESULTS` small for smoke tests. The preflight estimate counts planned web-search requests; max results controls how many records each request asks the provider to return. Do not commit API keys or `.env` files. Results become discovered sources first; project candidates are not final Projects. Auto-admit remains dry-run in this smoke script, and the public discoverability rule still applies: no public source means no project record.

For live smoke runs, keep `WEB_SEARCH_MAX_RESULTS=3` unless deliberately broadening the run. The query count controls the number of Brave API searches; max results controls how many records each query asks the provider to return.

## 6. Start the Backend

```bash
DATABASE_URL=sqlite:///local.db uvicorn app.main:app --reload
```

The backend API is available at `http://localhost:8000`.

## 7. Start the Frontend

In a separate terminal:

```bash
cd frontend
VITE_API_BASE_URL=http://localhost:8000 npm run dev -- --host 0.0.0.0 --port 8001
```

Open `http://localhost:8001/discovered-sources`.

Use the discovered sources page as the analyst triage gate before extraction or candidate generation. Review statuses are `unreviewed`, `useful`, `maybe`, `noisy`, `weak`, and `rejected`; notes and reviewer fields are triage metadata only. Weak URL-quality badges, including SCC public-comment form warnings, are separate provenance warnings and do not mean analyst rejection. Saving triage does not create Projects, Evidence, ProjectCandidates, claims, verification results, auto-admit decisions, or promotions. Later downstream extraction should normally be scoped to `useful` and `maybe` sources unless deliberately overridden.

### Map basemap setup

Open `http://localhost:8001/map`. CARTO basemaps require a key; the console reads the optional `VITE_CARTO_BASEMAP_API_KEY`. When absent or blank, it uses no-key OpenStreetMap standard tiles instead of calling CARTO, and displays a small “Fallback basemap active” notice. Project markers, popups, layers, and map controls remain available. Both providers retain their required attribution. The fallback requires internet access for tiles and is intended for interactive local demos, not bulk downloads or offline use.

To use CARTO, set this in the ignored `frontend/.env.local` file and restart Vite (or rebuild for production):

```dotenv
VITE_CARTO_BASEMAP_API_KEY=your-carto-basemap-key
```

Do not commit API keys or local env files. Vite exposes this browser-side key in the client and tile requests; use a key intended for public basemap access, not a private service credential. Remove the key to return to the fallback. A configured but invalid key is still sent to CARTO; this fallback handles missing/blank configuration, not provider outages or invalid credentials.

### Dark build-constraint intelligence console

The map uses a graphite, map-first Leaflet console with filtered summary metrics, compact controls, a project register, and a selected-project inspector. Search, state, model-risk, evidence-signal, and modeled-load filters apply to both the register and map. Clicking a list item selects and focuses its marker when coordinates are visible; clicking a marker selects it and opens a concise popup. Fit view frames the currently mapped records. Records without valid coordinates remain in the register. Approximate coordinates can be hidden, and location confidence is labeled separately from project risk.

Color semantics are explicit: red-orange means high evidence signal or high model risk in the selected mode; amber means moderate signal or elevated/medium/moderate model risk; slate means low, unknown, or unavailable signal/risk. Green marks explicitly verified coordinate status, not inferred analyst approval. Cyan marks navigation and coordinate tools. Magenta (permitting/legal/community) and cyan (water/infrastructure) category tokens are reserved; no category is assigned without structured supporting data. Marker area follows modeled MW, not confidence, review priority, or committed power. The selected marker gets a white ring and glow. Signal strength, model risk, and analyst review status are distinct.

The no-key OpenStreetMap fallback is darkened with a CSS filter on the tile pane only; markers, controls, and attribution keep their colors. The footer identifies the active fallback without an error. Optional CARTO key setup remains as above. State boundaries are opt-in and fetch only when enabled. Loading, empty, and API-error states preserve map controls, and failed project loads offer Retry. All new styling is scoped to the map route.

The map reads existing project, phase, score, signal, and prediction data. It no longer calls the enrichment GET endpoint, which writes an enrichment snapshot; available utility names come from existing project/phase records. The existing coordinate editor remains an explicit save action—do not submit it during read-only smoke tests.

Local smoke: start the backend and frontend using sections 6–7 (set `VITE_USE_MOCK=false` for real local data). Open `/map`, `/discovered-sources`, and `/constraint-dashboard`. Confirm fallback attribution, dark tiles, markers, popup/drawer selection, list-to-map focus, Fit view, filters, approximate-location toggle, and empty states. Confirm the review and constraint pages still load. Block non-tile external requests during restricted smoke; leave state boundaries disabled. Do not submit review or coordinate changes, run downstream pipelines, or commit secrets, env files, local databases, screenshots, or build output.

Follow-up: `map-vector-layers-v0` can evaluate MapLibre/deck.gl for vector styling, dense-point clustering, and evidence-backed constraint overlays. This branch keeps Leaflet and adds no dependencies.

## 8. Verify Projects

```bash
curl http://127.0.0.1:8000/projects
```

Confirm the response includes demo projects (e.g. `AVAIO Farmville`, `CleanArc VA1`). Both records should include `latitude`, `longitude`, and `coordinate_source`. Confirm `coordinate_source` values are **not** `manual_capture` or `starter_dataset` (legacy values) — they should be `manual_review` or `imported_dataset`.

## 9. Verify Predictions

```bash
curl http://127.0.0.1:8000/projects/<PROJECT_UUID>/prediction
```

Confirm the response uses `baseline_power_delay_v0_2` and includes `p_delay_6mo`, `p_delay_12mo`, `p_delay_18mo`, `risk_tier`, `confidence`, and human-readable `drivers`.

## 10. Verify Evidence

```bash
curl http://127.0.0.1:8000/projects/<PROJECT_UUID>/evidence
```

Confirm the response is HTTP 200 and includes an `evidence` list. Demo evidence rows should include a source URL or excerpt and accepted field names.

## 11. Verify the Map

Open `/map` in the frontend. Markers should be visible immediately (no toggle required). Click any marker without toggling any filter first. Confirm:

- Popup opens on the first click
- Prediction section appears with delay probabilities and drivers
- "View project details →" link works
- Evidence tab on the detail page loads without a backend 500
- "Edit coordinates" opens the coordinate editor

## 12. Constraint Dashboard

Open `/constraint-dashboard` in the frontend. The dashboard reads from the read-only constraint summary API (`GET /project-candidates/constraint-summary`) and shows:

- Summary stat cards: total candidates, high-priority review count, ready for verification, needs source, likely duplicate, dataset-only rejected
- CSV-backed vs web-discovered provenance pills
- Breakdown tables: by status, verification status, triage tier, review decision
- Energy strategy counts and top energy risk tags
- Siting friction category counts and top siting friction warnings
- Top review-priority candidates list with triage tier, recommended action, review decision, verification status, energy strategy, and siting friction

The dashboard supports filter controls for status, triage tier, review decision, energy strategy, and siting friction category — these are passed directly as query parameters to the summary endpoint.

**Important:** The dashboard is read-only. It uses only the constraint summary API and does not verify, promote, or admit candidates. Summary counts are review signals; they do not change guarded admission rules or imply that any candidate has been verified.

```bash
curl http://127.0.0.1:8000/project-candidates/constraint-summary
```

## Rerun Safely

To reload the demo data after editing the curated CSV:

```bash
cd backend
source .venv/bin/activate
DATABASE_URL=sqlite:///local.db python scripts/load_demo_dataset.py --reset
DATABASE_URL=sqlite:///local.db python scripts/load_demo_evidence.py
DATABASE_URL=sqlite:///local.db python scripts/run_demo_predictions.py
DATABASE_URL=sqlite:///local.db python scripts/demo_healthcheck.py
```

To check idempotency without deleting demo rows first, omit `--reset`. The loader should report skipped rows or updates, not newly duplicated projects.

### Review pagination and PATCH semantics

The source-review page shows `Showing X–Y of total`, Previous/Next controls, and page sizes of 25, 50, or 100. Filters and sort are preserved between pages; changing search, filters, sort, or page size returns to page 1. Selection is visible-page scoped: select-all selects only visible rows, and changing pages clears selection. After triage removes the last row on a page from the current filter, the UI returns to the last available page.

`GET /discovered-sources` applies filters and deterministic sorting before pagination, accepts `limit` (1–200) and nonnegative `offset`, and returns `total`, `next_offset`, `previous_offset`, `has_next`, and `has_previous`. Unavailable offsets are null.

Single and bulk PATCH preserve omitted fields. Explicit null or blank clears `review_notes` and `reviewed_by`; notes replace only when supplied. Append requires explicitly supplied, nonblank notes; null/blank append is a no-op. Omitted status is preserved; explicit `unreviewed` (or null) returns to unreviewed. The UI sends only changed row fields; bulk controls explicitly choose status, notes, and reviewer, with blank notes/reviewer clearing only when their Apply checkbox is selected (notes must use Replace).

`reviewed_count` counts surfaced statuses other than `unreviewed`; `unreviewed_count` includes null and explicit unreviewed statuses. Counts never depend on `reviewed_at`. That field is the last effective review metadata update timestamp, stays unchanged on no-ops, and can remain populated after returning to unreviewed. Bulk `updated_count` reports matched rows processed, including unchanged rows; missing IDs are reported separately.

Bulk triage changes source-review metadata only. It preserves provenance and creates no Projects, Evidence, ProjectCandidates, or claims. No search, URL fetch/validation, ingest, extraction, candidate generation, verification, auto-admission, or promotion occurs during review triage.

### Vector-style layer foundation (Leaflet)

The existing map console now has a structured layer model in `src/config/mapPresentation.ts` and five Map layers controls. Project markers are the master visibility switch. Model-risk halos (off by default) use high/elevated/medium/moderate model tiers already loaded. High-signal rings use only explicit high evidence-signal tiers. Green inner rings identify verified coordinates; dashed slate rings identify unverified, approximate, missing-precision, or low/unknown coordinate-confidence records. Confidence below 0.5 is a presentation threshold, not a verification decision. Verified and incomplete rings may coexist, for example for a verified approximate coordinate.

Counts show eligible **filtered, mappable** records before layer toggles and can overlap. Approximate-location visibility affects counts. Overlay toggles only change styling; the project master toggle hides markers and overlays together, while retaining list records, selection/details, and overlay preferences. Fit view uses visible markers. No layer fabricates constraint categories or runs predictions. Existing signal/risk color modes and selected-marker highlighting remain independent from overlays.

Concentric CSS rings follow Leaflet's marker transforms, add no geographic coverage claims, and do not intercept clicks. The high-signal ring has a subtle pulse disabled by reduced-motion preferences. All layers use already-loaded frontend data; toggles add no API calls, source fetching, or database writes. No new dependencies were added. Run `npm run test:map` for pure classification/count/filter assertions and `npm run build` for the production build.

For local smoke, open Map layers on `/map`; toggle project markers off/on, confirm counts remain eligibility counts, and toggle rings independently. Verify list selection, popups, Fit view, dark fallback tiles/attribution, `/discovered-sources`, and `/constraint-dashboard`. Do not submit coordinate/review changes. Never commit keys, env files, runtime data, or local databases.

**Engine evaluation:** The current Leaflet stack is sufficient for the next 1–2 demos with the current small project set. This is screen-space overlay styling, not vector basemap tiles or a spatial constraint analysis. MapLibre would enable a unified WebGL vector basemap and data-layer styling; deck.gl would add GPU-oriented rendering for large point sets and analytical overlays. Neither supplies missing evidence, verified geography, or a tile license. A migration introduces renderer lifecycle/React integration, selection/popup and attribution parity, WebGL/device testing, bundle/dependency cost, and provider/style/glyph/sprite configuration (including credential and offline considerations). Dense-marker performance still needs measurement; no clustering is claimed here. Recommend `maplibre-layer-parity-v0` as a later isolated spike with a licensed/key-optional style, measured dataset sizes, and parity tests before considering deck.gl. No engine migration is needed for this branch.

## Baseline open-database imports

Baseline imports seed analyst review; dataset rows are not final truth. The existing
CSV audit system supports `epoch_ai_data_centers` and `fractracker_us_data_centers`.
Keep local inputs in ignored `data/imports/manual_csv/epoch/` and
`data/imports/manual_csv/fractracker/`. No download or scraping occurs.

From `backend`, preview against an existing migrated database:

```sh
DATABASE_URL=sqlite:///local.db .venv/bin/python scripts/import_baseline_open_databases.py \
  --dataset epoch_ai_data_centers \
  --input ../data/imports/manual_csv/epoch/data_centers.csv --dry-run --limit 20
DATABASE_URL=sqlite:///local.db .venv/bin/python scripts/import_baseline_open_databases.py \
  --dataset fractracker_us_data_centers \
  --input ../data/imports/manual_csv/fractracker/fractracker_db_output_v2.csv --dry-run --limit 20
```

One of `--dry-run` or `--confirm` is mandatory. Dry-run writes nothing, including
schema or reports; SQLite is opened read-only. Use this dedicated entrypoint for
baseline datasets. Replace `--dry-run` with `--confirm` to write audit records only.
To request eligible review candidates, preview with `--dry-run --create-candidates`,
then use `--confirm --create-candidates` after inspecting the report. Remove the
limit only after review. No Projects, Evidence, claims, verification, auto-admission,
or promotions are created by baseline import.

Optional flags: `--import-run-id` (new UUID), `--dataset-version`, `--source-url`
(dataset landing page), `--citation`, `--license-note`, and `--report-output` (new
JSON file, confirmed runs only). Metadata flags override row values and profile
defaults. Never commit CSVs, env files, secrets, databases, or generated reports.

Epoch timeline/chiller/cooling-tower files retain original fields but are audit-only.
Epoch citation and CC BY 4.0 attribution defaults come from its supplied README;
confirm terms for the export version. FracTracker's license remains explicitly
unknown unless supplied; no redistribution license is inferred. Source columns,
citation, license notes, original row, filename/line and run UUID are preserved.
Missing country/location/date/capacity values are not invented.

Reports include read/valid/invalid rows, projected/actual audit and candidate counts,
exact skips, possible duplicates, missing identity/coordinates/public URLs, errors
and warnings. Import-record counts refer to rows; each confirmation also creates a
run record. Invalid rows remain auditable but cannot create candidates. Facility
candidates need name and location plus existing CSV provenance eligibility. Missing
coordinates or public URLs produce warnings. Dataset provenance is not project
evidence; URL checks are syntactic and do not fetch or verify anything.

Identical audited rows are skipped. Changed dataset IDs, shared URLs, normalized name
plus state/country, and matching names with nearby coordinates flag review and suppress
candidate creation; no automatic merges occur. Choose candidate creation on the first
import: repeating an audit-only import does not backfill candidates; use the explicit backfill workflow below. Ambiguous rows
remain audit-only for analyst resolution. Candidate review displays dataset, baseline
import type, run UUID, citation/license, URLs and missing-source warnings. Candidates
remain needs_review, unverified, not promoted and ineligible for auto-admission.

## Backfill baseline review candidates

First audit-import the local dataset using the workflow above. Then preview candidates
from those persisted audit rows; no CSV reload or external fetch is involved. From
`backend`, the recommended first demo uses FracTracker coordinates and a small limit:

```sh
DATABASE_URL=sqlite:///local.db .venv/bin/python scripts/backfill_baseline_candidates.py \
  --dataset fractracker_us_data_centers --dry-run --only-mappable --limit 25
DATABASE_URL=sqlite:///local.db .venv/bin/python scripts/backfill_baseline_candidates.py \
  --dataset epoch_ai_data_centers --dry-run --limit 25
```

Review the JSON, then preview an explicit audit-row allowlist with a positive creation
cap using the safe workflow below. Confirmation requires both safeguards. Exactly one mode is required;
no mode fails safely. Dry-run opens SQLite read-only and writes nothing. Confirmation
creates only ProjectCandidates and imported_candidate_links in one transaction. It
does not update audit rows, runs, existing candidates, or discovered-source status.
No Projects, Evidence, claims, verification, auto-admission or promotions are created.
Candidates remain `needs_review`, unverified, and not eligible for auto-admission.

`--import-run-id UUID` filters an existing run. `--limit` counts examined rows including
skips, in stable audit order; rerunning the same limited batch reports already-linked
rows instead of silently advancing. Use an explicit `--offset` or select another run
to examine the next window. `--only-mappable` requires finite, in-range latitude and longitude. Epoch
rows without coordinates remain suitable for review lists without that flag. Candidate
coordinates are stored in metadata; this workflow does not add candidates to the final
Project map layer or imply that a candidate has been promoted.

Rows need a name, a location, and either an external dataset ID, name plus state/country,
or name plus coordinates. Invalid and supporting audit rows are skipped. Existing links
are the primary rerun guard, with deterministic candidate keys and existing dedupe checks
as additional protection. Exact duplicates are always skipped. Possible/likely matches
are skipped unless `--include-possible-duplicates` explicitly requests review candidates;
the warning survives creation. No existing candidate is merged or modified.

Missing primary public URLs now block backfill under `rows_skipped_weak_source_quality`
(the legacy `rows_skipped_missing_public_source_url` counter remains zero). Public-source
requirements for final projects remain unchanged. Original row, dataset, audit/run IDs, source URLs,
citation and license metadata are retained. Epoch attribution and unknown FracTracker
license terms remain as recorded during import. Analysts must review both provenance
and project-specific evidence before later admission.

JSON reports include checked/eligible/skipped counts, projected and actual candidate
counts, link count, at most 100 created candidate IDs, warnings/errors and explicit zero
Project/Evidence counts. Skip reasons are mutually exclusive, in validation order.
`--report-output` is confirmed-only and refuses to overwrite a file; keep reports out of
Git. Existing dedupe searches consider the latest 1,000 candidates/projects. Run backfill
serially; concurrent jobs are not an entity-resolution mechanism. A duplicate key error
rolls back the transaction. No confirmed local backfill is needed to test this feature.

### Stable backfill windows and repeat checks

Backfill now retains already-linked audit rows in the batch's duplicate comparison
context. Linking a candidate must not erase coordinate, country, external-ID, or
secondary-source signals from its original audit row. Linked rows still count as
already linked; related ambiguous rows remain gated. No Projects or Evidence are
created, and verification/admission/promotion rules are unchanged.

For a fixed dataset and run filter, `--offset` (default 0) and `--limit` select audit
rows in stable order **before** eligibility checks. They count linked and skipped
rows too. With unchanged audit data and flags, repeating a confirmed window should
report zero would-create candidates. Skips may be classified as exact duplicates
when stronger evidence becomes available, but linking alone must not make them eligible.

From `backend`, preview the first window:

```sh
DATABASE_URL=sqlite:///local.db .venv/bin/python scripts/backfill_baseline_candidates.py \
  --dataset fractracker_us_data_centers --dry-run --only-mappable --offset 0 --limit 25
```

After reviewing that report, select reviewed audit UUIDs and preview them with
`--audit-row-id` and `--max-create-candidates` as described below. Both safeguards
are required for confirmation. Repeat the same allowlist dry-run to check idempotency. Confirmations during hardening tests use temporary databases
only; do not run this confirmation against local.db during hardening development.

To intentionally preview the next window:

```sh
DATABASE_URL=sqlite:///local.db .venv/bin/python scripts/backfill_baseline_candidates.py \
  --dataset fractracker_us_data_centers --dry-run --only-mappable --offset 25 --limit 25
```

Use a fixed `--import-run-id` when concurrent imports could alter the dataset ordering.
Offset is an audit-row offset, not an eligible-candidate count or an automatic cursor.
`--include-possible-duplicates` is an explicit override that can create ambiguous
review candidates; it never bypasses exact duplicate protection. Changing this flag
changes eligibility intentionally. Missing-coordinate rows remain excluded with
`--only-mappable`. Dry-runs remain write-free.

### Reconcile paginated backfill previews before confirmation

Do not run `--confirm` until the dry-run row details and counts have been reviewed.
Offset alone is insufficient: duplicate context must also be independent of page size.
The preview order is ascending `(created_at, run_id, source_file, row_number, id)`
within the selected dataset/run. The audit ID breaks every remaining tie. This keeps
existing import windows stable; no audit records are reordered or rewritten.

The service now replays preceding audit rows as read-only duplicate context before
reporting the requested offset/limit. Eligible preceding rows are treated as planned
review inputs, even when unlinked, so splitting a window cannot erase their duplicate
signals. Prefix rows contribute no output counts, row details, candidates or links.
Consequently later pages may be gated by earlier, not-yet-confirmed rows. This is
intentional conservative behavior; inspect the matched audit ID rather than bypassing
it. Larger offsets require more read-only comparisons.

From `backend`:

```sh
DATABASE_URL=sqlite:///local.db .venv/bin/python scripts/backfill_baseline_candidates.py \
  --dataset fractracker_us_data_centers --dry-run --only-mappable \
  --offset 25 --limit 25 --include-row-details
```

`--include-row-details` is dry-run-only: combining it with `--confirm` fails before
opening the database. Each selected row includes its audit ID, available facility,
operator, location, first public source URL, classification, reason, and matching
candidate/project/audit IDs where known. Missing fields are null. No raw row or full
metadata blob is included. Matching audit IDs may refer to earlier context rows;
`existing_candidate_duplicate` also covers exact matches to planned audit rows, so
use the match IDs to distinguish the cases. Missing primary public sources now block
backfill through the source-quality gate described below.

To reconcile, run the same command with `--limit 5` at offsets 25, 30, 35, 40 and 45.
Sum checked/eligible/skipped/would-create/created counts; they must equal the limit-25
report. Concatenate row_details in offset order; they must equal its row_details,
including classifications and match IDs. Repeat against the same unchanged database,
dataset/run filter and flags. Offset itself is not an additive counter. Concurrent
imports or reviews change the comparison snapshot, so rerun all previews after them.
Dry-run creates zero candidates, links, Projects or Evidence and invokes no external
fetch, verification, admission or promotion. Runtime reports stay outside Git.

### Source-quality and candidate-type gates

Review `--dry-run --include-row-details` before any confirmed backfill. A usable name,
location and lack of duplicates are no longer sufficient. Baseline backfill now also
requires `source_quality_allows_candidate_creation`,
`candidate_type_allows_candidate_creation` and
`source_row_alignment_allows_candidate_creation`. This applies to the existing confirm path
as well as its preview; `--include-possible-duplicates` cannot bypass these gates.

Classification is offline, using the primary public URL's hostname/path and explicit
name, stage and notes fields. No fetching, content verification or invented facts are
involved. A small explicit domain list recognizes operator and news sources; unknown
hosts remain blocked. These are review hints, not proof of credibility or admission.

Source categories:

- `official_project_or_operator`, `credible_news_article`, `government_or_regulatory`:
  may pass source quality if the URL is not a landing page/index.
- `social_media_or_group`: blocked; social/group/forum pages cannot establish a candidate.
- `broad_report_or_index`: blocked; broad reports and indexes are supporting context.
- `advocacy_or_watchdog_report`: blocked as a direct candidate creation source.
- `unknown`: blocked, including missing URLs and unrecognized domains.

Candidate types:

- `project_specific_build_or_expansion`: requires an explicit build, expansion,
  construction or proposal signal in the primary URL or selected row fields.
- `operating_facility_or_colocation_page`: blocked without an explicit build/expansion signal.
- `programmatic_solicitation_or_policy`: blocked; a program covering multiple sites
  does not establish a particular project, even if the dataset labels it Proposed.
- `broad_market_or_report_reference` and `ambiguous`: blocked.

The existing first public URL remains the primary source. Secondary links are retained
in the audit but never silently promoted to replace a weak primary. Analysts should
review such alternatives separately. Evidence-text blobs containing other URLs are
not mined for build signals. This deliberately favors false negatives over weak
candidate creation; there is no CLI source-quality override.

Row details show both categories, both booleans and `quality_gate_reason`, even when an
earlier identity/link/duplicate check supplies the final classification. Rows otherwise
eligible are counted as `rows_skipped_weak_source_quality` or
`rows_skipped_ambiguous_candidate_type` when blocked. Counters remain mutually exclusive.
Blocked rows remain visible and retain duplicate context, so tightening source gates
cannot silently make neighboring ambiguous rows eligible. Pagination reconciliation
and read-only behavior remain unchanged.

For the reviewed offset-25 FracTracker window, the two Facebook-primary rows are blocked;
Expedient PHX1 is an operating facility reference; the Tract primary URL is a broad report;
Davis-Monthan's primary article describes a multi-base solicitation. The Guadalupe Quarry
proposal article can remain eligible subject to duplicate and analyst checks. Additional
links on some blocked rows may be useful for later review. This change does not modify
the separate CSV audit importer, final-project verifier, admission or promotion rules.

### Entity, lifecycle and intelligence-purpose taxonomy (preview only)

The baseline preview can describe useful intelligence even when a row cannot create a
build candidate. `--include-row-details` now adds `entity_type`, `lifecycle_stage`,
`candidate_purpose` and a sorted, deduplicated `constraint_domains` list. No migration,
model/API change or durable taxonomy field is added in this version. The existing
source-quality, source-row alignment, identity, duplicate and mappability gates control creation.
A `build_review` purpose is a review role, not permission to create or promote a record.
Entity and purpose are independent: an existing facility can carry a build-review role
when its primary source describes a proposal or expansion. This does not verify an event.

Entity types: `data_center_project`, `data_center_facility`, `data_center_campus`,
`power_generation_asset`, `grid_interconnection_asset`, `cooling_water_asset`,
`equipment_supply_chain_signal`, `policy_permitting_case`, `supporting_context`, `unknown`.

Lifecycle stages: `existing_operational`, `under_construction`, `proposed`,
`planned_expansion`, `speculative_or_unverified`, `cancelled`, `retired`, `unknown`.
Explicit row stage takes precedence; absent stages can use explicit name/primary-URL
language. Approved/permitted alone does not imply construction. Context reports, policy
signals and supply reports retain unknown asset lifecycle rather than inheriting a
facility stage from the dataset. These are unverified text classifications.

Purposes: `build_review`, `facility_baseline`, `infrastructure_context`,
`supply_chain_signal`, `permitting_or_policy_signal`, `supporting_context`, `unknown`.
Social sources remain supporting context. Broad reports are supporting context or, with
explicit equipment/supply language, supply-chain signals. Programmatic solicitations
are policy/permitting signals. Official operating facility pages can be facility baselines
without becoming build-review candidates. Names explicitly identifying standalone assets
can be infrastructure context; a data center mentioning generators remains a data center.

Constraint domains: `grid_capacity`, `onsite_power`, `gas_turbine_supply`,
`transformer_supply`, `backup_generation`, `fuel_supply`, `air_emissions`, `water_cooling`,
`land_use_zoning`, `community_opposition`, `legal_regulatory`, `cost_financing`, `schedule_delay`.
These tags mean a topic is mentioned, not that a dependency, shortage, capacity problem
or adverse risk has been verified. They may include negative or hypothetical mentions.
Water/cooling includes dry/air cooling as a cooling topic, without asserting water use.
No capacity, location, date or technology is invented from a city, operator brand or
hostname. General turbines are not automatically labeled gas turbines.

Taxonomy uses explicit normalized fields, whitelisted original equipment/power/cooling/
context fields, and stored URL paths. Secondary URL paths can contribute topical tags;
only the primary URL contributes entity/lifecycle hints. They never replace the primary
source or relax source-quality gates. Raw blobs, secrets, URL queries and unrelated raw
columns are not included in the output. No sources are fetched.

Every dry-run includes `taxonomy_summary` with `entity_type_counts`,
`lifecycle_stage_counts`, `candidate_purpose_counts`, and `constraint_domain_counts`.
Counts cover exactly the selected audit window, including skipped and linked rows, not
its preceding duplicate context. The first three totals equal rows_checked; domain
counts can exceed it because a row may mention multiple domains. Zero categories are
omitted. Summing smaller windows reconciles with a larger window on the same snapshot.
Existing top-level counters retain their meanings. Confirm output/persistence is unchanged.

Use the existing safe preview command:

```sh
DATABASE_URL=sqlite:///local.db .venv/bin/python scripts/backfill_baseline_candidates.py \
  --dataset fractracker_us_data_centers --dry-run --only-mappable \
  --offset 25 --limit 25 --include-row-details
```

PHX1 should read as an operational facility baseline. Facebook-primary rows and Tract's
broad report remain supporting context; Davis-Monthan is a policy/permitting signal.
Guadalupe Quarry remains the only build-review would-create row in the reviewed window.
Review this output before any later workflow; taxonomy itself creates no graph nodes,
Projects, Evidence, candidates, verification, admission or promotions.

### Primary-source row alignment

Backfill also requires affirmative offline alignment between the audit row and its
primary source. Row details expose `source_row_alignment`,
`source_row_alignment_allows_candidate_creation` and `source_row_alignment_reasons`.
Categories are `aligned`, `weakly_aligned`, `geography_mismatch`,
`facility_or_operator_mismatch`, `broad_transaction_or_platform_article`,
`cancelled_or_rejected_project`, `insufficient_source_row_alignment` and `unknown`.
Only the first two allow creation, subject to all existing gates and duplicate checks.
`rows_skipped_source_row_alignment` counts rows reaching and failing this gate;
rows blocked earlier still show their alignment details.

This reads stored primary URL paths and explicitly bound primary titles/subject metadata.
Generic article titles need a matching source URL or a single-source audit row. Secondary
sources never rescue the primary source. Full US state names and contextual abbreviations
are recognized; city hints use the existing audit corpus, independently of page limits.
This is a bounded heuristic, not geocoding or content verification. Unrecognized geography
and token overlap still require analyst review. A matching state plus a build signal may
be weakly aligned, allowing a nearby-metro description such as Guadalupe Quarry.

Explicit conflicting geography blocks unless the row city or state also appears in the
source. Broad transactions block unless a build/expansion or identifiable site conversion
is supported at the row location; Buena Vista's Californian biomass-site conversion is
such an exception. Cancellation/withdrawal signals block and set preview lifecycle to
`cancelled`, purpose `supporting_context`; rejection/lack of approval sets lifecycle to
`unknown`, purpose `permitting_or_policy_signal`. These overrides avoid treating rejected
plans as active builds without inventing a final cancellation.

Blocked rows remain visible and retain duplicate context across pagination. Alignment
cannot relax source-quality gates and has no CLI bypass. Validate with dry-run row details
only; this change requires no confirmed local backfill, network requests or DB mutation.

### Safe allowlist confirmation workflow

A. Run a dry-run sweep with `--include-row-details`.
B. Manually inspect the `would_create_candidate` rows, source quality, taxonomy,
alignment and duplicate reasons.
C. Preview exactly the reviewed row using its audit UUID and a positive cap:

```sh
DATABASE_URL=sqlite:///local.db .venv/bin/python scripts/backfill_baseline_candidates.py \
  --dataset fractracker_us_data_centers --dry-run --only-mappable \
  --audit-row-id 75847487-397c-48df-8929-069ee44261af \
  --max-create-candidates 1 --include-row-details
```

D. Only after reviewing that allowlist preview, a separately authorized confirmed run
may replace `--dry-run` with `--confirm` and **remove `--include-row-details`** (preview
only). Keep the same dataset, allowlist, cap and other selection flags. No confirmed
local backfill is part of this implementation's validation.

Repeat `--audit-row-id UUID` to select multiple reviewed audit rows; repeated identical
UUIDs count once. Both a nonempty allowlist and `--max-create-candidates N` are mandatory
for confirmation, in both CLI and service. N must be a positive integer. All existing
gates still apply; allowlisting never forces a blocked row to create a candidate.

The allowlist intersects the existing dataset/run/offset/limit window. Unknown UUIDs
or IDs outside that scope fail explicitly, preventing a silently incomplete selection.
Other audit rows remain duplicate-comparison context, but are excluded from reported
row counts, details, taxonomy counts and planned writes. Window offsets still refer to
the original audit order, not to the allowlist.

The full eligible selection is planned before writes. Exceeding the cap fails with
`created_candidates=0`; it never silently truncates. Dry-run reports the full count even
when over cap. New summary fields are `audit_row_id_filter_count` (unique IDs),
`max_create_candidates` (null when absent), `would_create_candidates_within_cap` (true
when no cap or within cap), and `confirm_safety_ready` (both safeguards present and
within cap). Readiness is a guardrail result, not analyst approval or verification.
Confirmation creates only review candidates and audit links in the existing transaction;
Projects, Evidence, verification, admission and promotion remain outside this workflow.

## Baseline candidate map demo

The four reviewed pilot imports are **ProjectCandidates, not final Projects**:
HostDime (Maitland, FL), Global AI (Windsor, CO), Buena Vista Biomass Power site
(Ione, CA), and Guadalupe Quarry Redevelopment (Brisbane, CA). They remain
`needs_review` / `dataset_import_needs_review`, confidence 0.45, unverified and
not promoted. Displaying them performs no backfill, verification, auto-admit or promotion.

Start the existing migrated local database in read-only mode for this demo:

```sh
cd backend
source .venv/bin/activate
DATABASE_URL="sqlite:///file:$(pwd)/local.db?mode=ro&uri=true" \
  uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
cd frontend
VITE_USE_MOCK=false VITE_API_BASE_URL=http://127.0.0.1:8000 \
  VITE_CARTO_BASEMAP_API_KEY= npm run dev -- --host 127.0.0.1 --port 8001
```

- Open `/project-candidates`. Newest-created sorting is the default; choose
  **Baseline imports** and **Needs review** to find the pilots without exact search.
  Existing dataset, status, geography and other filters remain available, along with
  **Triage priority** sorting. Rows show dataset-import and not-promoted labels,
  city/state and a primary-source link. No need to open source links for the demo.
- Open `/map`. **Needs review candidates** is enabled by default under **Map layers**.
  Amber diamonds represent unpromoted review candidates; project circles remain separate.
  Use **Fit view**, or search a short name such as Global AI. Candidate popups show
  name, city/state, lifecycle, status, confidence, primary URL and a candidate-review link.
  Candidate markers use only existing stored coordinates; locations are not verified.
  Search/geography apply to candidates; model-load/risk/signal filters apply to Projects.
- Open `/constraint-dashboard` for the additional ProjectCandidate review inventory:
  needs-review, dataset-import-needs-review and not-promoted counts. These describe the
  latest up to 500 candidates and are independent of dashboard filters. The candidate
  list and map also load at most 500 records; these are not exhaustive national totals.

The API adds nullable validated latitude/longitude display fields, accepting only finite,
in-range stored coordinate pairs (top-level metadata, then normalized row). No database
columns or records are added. Raw metadata remains redacted. Optional `sort=newest`
applies before the API limit; the existing default API triage order is unchanged.

Without a CARTO key, the existing OpenStreetMap fallback and notice remain. Normal
basemap rendering requests external tiles. For no-network smoke, block external browser
requests: candidate/project overlays and controls still work, but tiles are blank.
State boundaries and external source links should remain unopened in that smoke.
The implementation smoke used ports 8126/8127 to avoid existing local servers, a
read-only SQLite connection, `BACKEND_CORS_ORIGINS=http://127.0.0.1:8127`,
and blocked all external and non-GET/HEAD requests. It found all four pilots and
19 mapped review candidates, with no mutation requests or database checksum change.

### Coordinate preservation during explicit promotion

Future candidate promotions preserve a validated coordinate pair on newly created
Projects. The resolver first uses the same candidate metadata fields as the candidate
API (top-level latitude/longitude, then normalized row). If unavailable or invalid,
it checks imported audit rows linked to that candidate by `imported_candidate_links`
with `linked_record_type=project_candidate`, in stable creation-time/ID order, taking
the first valid pair. Coordinates are never combined across sources or geocoded.
Booleans, nonnumeric values, nonfinite values and out-of-range pairs are ignored;
missing coordinates do not block an otherwise valid promotion.

Copied coordinates are `unverified`, precision `source_row`, with source
`baseline_imported_dataset_row` (or `candidate_metadata` for a non-dataset candidate),
the candidate primary URL, candidate confidence when valid (otherwise 0.45), source
notes and the current update timestamp. No coordinate verification timestamp is set.
Existing Projects and already-promoted records are not silently repaired or overwritten.
The usual explicit promotion guards and associated Evidence behavior are unchanged.

Current demo: HostDime and Buena Vista were previously promoted and manually repaired.
They appear as Project circles. Global AI and Guadalupe Quarry remain amber review
candidate diamonds. Promoted status or a promoted Project ID excludes a record from
the review-candidate layer. This code change performs no local promotion or repair;
regression promotions run only against disposable test databases.
