# Demo Runbook

This runbook creates a reproducible local demo from a clean SQLite database. The demo data is loaded from committed CSVs under `data/demo/`; it does not scrape live sources at demo time.

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
python scripts/run_public_discovery.py --dry-run
```

The dry-run JSON includes `planned_search_query_count` and `planned_generic_web_search_query_count`. Use `planned_generic_web_search_query_count` as the approximate Brave Search API query count before running live discovery. The targeted official-source expansion adds 28 generic-provider queries per full run.

For a fixture-backed local check:

```bash
WEB_SEARCH_PROVIDER=mock python scripts/run_public_discovery.py
```

For live Brave Search API discovery, keep the key in your shell environment and do not commit it:

```bash
WEB_SEARCH_PROVIDER=brave WEB_SEARCH_API_KEY="$BRAVE_SEARCH_API_KEY" WEB_SEARCH_MAX_RESULTS=5 python scripts/run_public_discovery.py
```

Any discovered records are written under ignored `data/discovery_runs/` runtime output and still need discovered-source ingestion, claim extraction, verification, and review before any project can be promoted.

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

Triage uses dataset provenance, source URLs, location, load, developer/operator, citation, and license notes as review-priority signals only. It does not verify, promote, or admit candidates.

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

Analysts can also attach public-source references to a ProjectCandidate during review. These attachments are candidate-review metadata: they store URLs, titles, excerpts, notes, source type, and reviewer context for later analyst work. They do not create final `Evidence` rows, do not create Projects, do not bypass verification, and do not change the guarded promotion flow.

```bash
curl -X POST http://127.0.0.1:8000/project-candidates/<CANDIDATE_UUID>/source-attachments \
  -H 'Content-Type: application/json' \
  -d '{"source_url":"https://example.gov/permit-page","source_title":"County permit agenda","source_type":"permit","source_excerpt":"Agenda item references data center substation request.","analyst_notes":"Potential official source for candidate.","attached_by":"analyst"}'
```

To review saved attachments:

```bash
curl http://127.0.0.1:8000/project-candidates/<CANDIDATE_UUID>/source-attachments
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

Brave API usage may create incremental API cost, so keep `WEB_SEARCH_MAX_RESULTS` small for smoke tests. Do not commit API keys or `.env` files. Results become discovered sources first; project candidates are not final Projects. Auto-admit remains dry-run in this smoke script, and the public discoverability rule still applies: no public source means no project record.

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
