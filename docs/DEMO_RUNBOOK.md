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
