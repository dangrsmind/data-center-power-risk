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

The API is available at `http://127.0.0.1:8000`.

## 7. Start the Frontend

In a separate terminal:

```bash
cd frontend
npm run dev
```

Open `http://localhost:5000/map`.

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
