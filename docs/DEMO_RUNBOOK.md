# Demo Runbook

This runbook creates a reproducible local demo from a clean SQLite database. The demo data is loaded from the committed CSV at `data/demo/demo_projects_v0_1.csv`; it does not scrape live sources at demo time.

## Update The DB Schema

From the backend directory:

```bash
cd backend
source .venv/bin/activate
DATABASE_URL=sqlite:///local.db alembic upgrade head
```

## Load Demo Data

From the backend directory:

```bash
python scripts/load_demo_dataset.py --reset
```

The loader upserts by `canonical_name` plus `state`. Running it repeatedly is safe and will not create duplicate projects. The `--reset` flag removes only demo-owned project rows for this dataset before reloading them.

Expected summary fields:

- `rows_read`
- `projects_created`
- `projects_updated`
- `rows_skipped`
- `validation_errors`

## Run Demo Predictions

From the backend directory:

```bash
DATABASE_URL=sqlite:///local.db python scripts/run_demo_predictions.py
```

The runner scores demo-marked projects with `baseline_power_delay_v0_2` and stores one prediction row per project/model/version. Re-running it is safe; existing prediction rows are updated in place when the deterministic output changes.

Expected summary fields:

- `projects_scored`
- `predictions_created`
- `predictions_updated`
- `errors`

## Run Backend Healthcheck

From the backend directory:

```bash
DATABASE_URL=sqlite:///local.db python scripts/demo_healthcheck.py
```

The healthcheck validates the demo database, project API service path, stored/computed predictions, coordinate metadata, and evidence endpoint behavior. It exits non-zero only when the summary includes errors.

## Start The Backend

From the backend directory:

```bash
uvicorn app.main:app --reload
```

The API should be available at `http://127.0.0.1:8000`.

## Verify Projects

In another terminal:

```bash
curl http://127.0.0.1:8000/projects
```

Confirm the response includes the demo projects:

- `AVAIO Farmville`
- `CleanArc VA1`

Both records should include latitude, longitude, and coordinate metadata.

## Verify Predictions

Use any project ID from `/projects`:

```bash
curl http://127.0.0.1:8000/projects/<PROJECT_UUID>/prediction
```

Confirm the response uses `baseline_power_delay_v0_2`, includes `p_delay_6mo`, `p_delay_12mo`, `p_delay_18mo`, `risk_tier`, `confidence`, and human-readable `drivers`.

## Start The Frontend

From the frontend directory:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL printed by `npm run dev`.

## Verify The Map

Open `/map` in the frontend. The map should show markers for demo projects with valid coordinates. Click each marker and confirm the popup shows project and coordinate metadata.

## Rerun Safely

To reload the demo data after editing the curated CSV:

```bash
cd backend
source .venv/bin/activate
python scripts/load_demo_dataset.py --reset
```

To check idempotency without deleting demo rows first:

```bash
python scripts/load_demo_dataset.py
python scripts/run_demo_predictions.py
```

The loader command should report skipped rows or updates, not newly duplicated projects. The prediction command should update existing stored predictions instead of creating duplicates.
