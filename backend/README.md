# Data Center Power Risk Backend

Minimal backend slice for the forecasting platform:

- SQLAlchemy data model
- SQLite fallback for local development
- FastAPI read-only endpoints
- Deterministic mock scoring service
- Deterministic demo seed data

## Local setup

### 1. Create a virtual environment

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

SQLite-only local setup:

```bash
pip install -e .
```

If you want PostgreSQL support too:

```bash
pip install -e '.[postgres]'
```

### 3. Choose a database

Default behavior uses SQLite automatically:

```bash
unset DATABASE_URL
```

This creates a local file database at `backend/local.db`.

To use PostgreSQL instead:

```bash
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/power_risk'
```

### 4. Start the server

```bash
uvicorn app.main:app --reload
```

The app creates tables on startup.

## Clean dataset management

Use these commands when building or restoring a real training/testing dataset.

Clean schema-only reset:

```bash
cd backend
source .venv/bin/activate
unset DATABASE_URL
python scripts/reset_db.py --schema-only --confirm REAL_RESET
```

This drops and recreates the application schema, does not create demo projects, and prints `projects`, `evidence`, and `claims` counts. For PostgreSQL, export `DATABASE_URL` before running the same command.

Backup/export the current dataset:

```bash
python scripts/export_dataset.py
```

Exports JSONL files for `projects`, `phases`, `evidence`, `claims`, `field_provenance`, and `events` under `data/exports/YYYYMMDD/`.

Restore/import into an empty local database:

```bash
unset DATABASE_URL
python scripts/reset_db.py --schema-only --confirm REAL_RESET
python scripts/import_dataset.py data/exports/YYYYMMDD
```

The import command refuses to load if any target dataset table already has rows, so demo data and real data are not silently mixed.

Build starter dataset v0.1:

```bash
unset DATABASE_URL
python scripts/reset_db.py --schema-only --confirm REAL_RESET
python scripts/ingest_starter_dataset.py --dry-run
python scripts/ingest_starter_dataset.py
python scripts/export_dataset.py
```

The starter ingest reads `../data/starter_sources/projects_v0_1.csv`. Add only real source-backed rows to that CSV; do not use `example.com`, placeholder evidence, or demo text. The script creates or updates projects, creates one evidence record per row, generates claims through the existing automation packet, and auto-accepts only `developer_named`, `location_state`, and `location_county`. Project-name, modeled-load, utility, region, date, phase, and power-path claims remain in the review queue.

### Source/config data vs runtime data

Tracked starter source/config files live under `../data/starter_sources/`:

- `discovery_seeds.yml`
- `projects_v0_1.csv`

Mutable discovery review state lives under `runtime_data/starter_sources/` and is intentionally ignored by Git:

- `discovered_sources_v0_1.csv`
- `discovery_decisions_v0_1.json`
- `manual_source_captures_v0_1.json`

This keeps source-controlled seed/config data separate from generated review output and local analyst approvals. To check the local repo state:

```bash
python scripts/doctor_repo_state.py
```

To preserve local runtime state manually before cleaning the worktree or switching machines, copy `runtime_data/starter_sources/` somewhere durable and restore it to the same path later. These files are local operating state, not part of the committed source dataset.

To export the database-backed dataset for sharing or backup:

```bash
python scripts/export_dataset.py
```

Exports are written under `data/exports/YYYYMMDD/` in the backend directory unless `--output-dir` is provided.

Useful starter ingest options:

```bash
python scripts/ingest_starter_dataset.py --dry-run
python scripts/ingest_starter_dataset.py --limit 10
python scripts/ingest_starter_dataset.py --project-name "Exact Project Name"
python scripts/ingest_starter_dataset.py --allow-existing
```

By default the script refuses to run if the configured database already contains rows. Use `--allow-existing` only when intentionally adding more real starter evidence to an existing real dataset.

Discover starter dataset source drafts:

```bash
python scripts/discover_starter_dataset.py --dry-run
python scripts/discover_starter_dataset.py --limit 20
python scripts/discover_starter_dataset.py --seed-file ../data/starter_sources/discovery_seeds.yml
python scripts/discover_starter_dataset.py --write-projects-csv
```

Discovery reads `../data/starter_sources/discovery_seeds.yml` and writes reviewable drafts to `runtime_data/starter_sources/discovered_sources_v0_1.csv`. It fetches only explicit URL seeds, rate-limits requests, checks `robots.txt`, records fetch failures as rows with review reasons, and does not touch the database. Search query seeds are preserved as `query:` rows for analyst follow-up rather than broad web scraping.

PDF URL seeds are supported without OCR. The script downloads PDFs up to 25 MB with a 30 second timeout, extracts embedded text with `pypdf` when available, skips encrypted PDFs, and writes `extraction_method`, `extraction_status`, `extraction_error`, and `extracted_character_count` for analyst inspection. Failed PDF extraction still preserves the source URL row for manual review.

Use `--write-projects-csv` only after reviewing the discovered rows. It generates the tracked `../data/starter_sources/projects_v0_1.csv` from high-confidence URL rows and still leaves ingestion/claim review to `ingest_starter_dataset.py`.

Ingest reviewed discovered source drafts:

```bash
python scripts/ingest_discovered_sources.py --dry-run
python scripts/ingest_discovered_sources.py --limit 10
python scripts/ingest_discovered_sources.py --allow-existing
```

This reads `runtime_data/starter_sources/discovered_sources_v0_1.csv`, creates candidate projects and evidence records, generates suggested claims, and auto-accepts only `developer_named`, `location_state`, and `location_county`. Project names, load, utility, region, dates, phase, and power-path claims remain queued for UI/manual review. Rows missing project name or state are skipped unless `--allow-partial` is used.

## Baseline prediction model card

Endpoint:

```bash
curl http://127.0.0.1:8000/projects/<PROJECT_UUID>/prediction
```

Model version: `baseline_power_delay_v0`

Prediction target: `power_delivery_delay`

Assumptions:

- This is a deterministic rule baseline, not a trained ML model.
- It uses accepted claims only for project facts such as load, utility, region, target energization date, and power-path evidence.
- Missing data lowers confidence. Missing utility, region, target date, load, or power-path support does not automatically make a project high risk.
- Enrichment context can appear as a driver, but it is not treated as accepted evidence.
- The existing Evidence Signal remains separate and is used as one input driver; it is not replaced.

Inputs:

- accepted `modeled_load_mw`
- accepted `utility_named`
- accepted `region_or_rto_named`
- accepted `target_energization_date`
- accepted power-path claims
- accepted regional large-load stress claims
- latest enrichment snapshot, if available
- reviewed evidence count and accepted claim count
- missing critical fields

Weights:

- baseline prior: `+0.12`
- accepted load over `300 MW`: `+0.16`
- accepted load over `800 MW`: `+0.28`
- target date under 24 months with no accepted power-path evidence: `+0.18`
- accepted new substation or transmission requirement: `+0.12`
- accepted regional large-load stress evidence: `+0.10`
- Evidence Signal moderate tier: `+0.06`
- Evidence Signal high tier: `+0.12`
- accepted power-path support: `-0.08`
- accepted substation/interconnection detail: `-0.04`
- missing critical input: `0.00` risk weight, confidence penalty only

Limitations:

- No learned coefficients, vector embeddings, OCR, or ML parsing are used.
- Probabilities are calibrated rule outputs for triage, not statistically fitted event probabilities.
- The baseline cannot infer unaccepted project facts from raw evidence text.
- It does not model utility queue position, interconnection study status, local permitting, or construction sequencing unless those facts are represented as accepted claims.

What would change the conclusion:

- accepted load moving above or below `300 MW` or `800 MW`
- accepted target energization date moving inside or outside a 24-month window
- accepted utility, region, or power-path evidence being added
- accepted evidence that new substation/transmission work is required
- accepted regional large-load stress evidence being added or rejected
- additional reviewed evidence increasing confidence

## Reset and seed demo data

Warning: `scripts/seed_demo_data.py` creates fake/demo data. Do not use it for real training/testing datasets.

The seed script replaces placeholder records with deterministic, clearly fake demo data.
It also rebuilds explicit evidence links and stored demo `phase_quarter_scores` used by the analyst endpoints.

SQLite reset + seed:

```bash
cd backend
source .venv/bin/activate
unset DATABASE_URL
python scripts/seed_demo_data.py --reset
```

This is the exact command to fully rebuild the local demo database.

PostgreSQL reset + seed:

```bash
cd backend
source .venv/bin/activate
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5432/power_risk'
python scripts/seed_demo_data.py --reset
```

If you only want to seed into existing tables without dropping them first:

```bash
python scripts/seed_demo_data.py
```

## Test endpoints

Healthcheck:

```bash
curl http://127.0.0.1:8000/health
```

List projects:

```bash
curl http://127.0.0.1:8000/projects
```

Each project row keeps the existing summary fields and now also includes:

- `current_hazard`
- `deadline_probability`
- `risk_tier`
- `as_of_quarter`

Project detail:

```bash
curl http://127.0.0.1:8000/projects/<PROJECT_UUID>
```

Project phases:

```bash
curl http://127.0.0.1:8000/projects/<PROJECT_UUID>/phases
```

Project mock score:

```bash
curl http://127.0.0.1:8000/projects/<PROJECT_UUID>/score
```

## Generate modeling training table

Build the strict as-of feature table for future modeling:

```bash
cd backend
source .venv/bin/activate
python scripts/generate_training_table.py --csv build/project_phase_quarter_features.csv
```

This creates/replaces the SQLite table `project_phase_quarter_features` and optionally writes a CSV. Each row is keyed by project, phase, and quarter, with E1 targets plus a JSON `features_as_of_prior_quarter` payload. Claim-derived features only count records accepted before the row quarter cutoff.

Audit the generated table before modeling:

```bash
python scripts/audit_training_table.py
python scripts/audit_training_table.py --json
```

OpenAPI docs:

```bash
open http://127.0.0.1:8000/docs
```

## Mock scoring notes

The current `/projects/{id}/score` endpoint is deterministic and has no randomness.

It combines:

- latest project stress score
- latest regional stress score
- anomaly score
- latest E2/E3/E4 weak-label signals
- selected structural snapshot flags
- evidence quality and observability offsets

If no snapshot or stress rows exist yet, the service uses stable fallback defaults so the endpoint still returns a consistent response shape.

For `GET /projects`, the dashboard fields use the latest available project score in this order:

- latest stored `phase_quarter_scores` row joined to the project quarter
- otherwise the same deterministic mock score computation used by `/projects/{id}/score`

`risk_tier` is currently deterministic and based on `deadline_probability`:

- `low` for values below `0.33`
- `medium` for values from `0.33` up to `0.66`
- `high` for values at or above `0.66`

`as_of_quarter` is returned as a `YYYY-QN` label such as `2026-Q2`.

## Demo dataset summary

The seed script creates:

- 6 fake but realistic-looking sample projects
- realistic modeled primary loads such as `300`, `500`, `900`, and `1200`
- multi-phase projects so `phase_count` is meaningful
- one E2 demo example
- one E3 demo example
- one E4 demo example
- explicit evidence links through `claims` and `field_provenance`
- stored demo `phase_quarter_scores` so history endpoints return non-null score values

These records are intended only for local development and API testing.
