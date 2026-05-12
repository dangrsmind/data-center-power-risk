# Demo Checklist

Use this checklist before every demo or before merging `demo-real-data-v0`.

## Setup

- [ ] Pull latest `demo-real-data-v0`
- [ ] Confirm clean git status (`git status --short` shows no staged runtime files)

## Backend

- [ ] `cd backend && source .venv/bin/activate`
- [ ] `DATABASE_URL=sqlite:///local.db alembic upgrade head` — migration applies cleanly
- [ ] `DATABASE_URL=sqlite:///local.db python scripts/load_demo_dataset.py --reset` — reports projects created/updated, zero validation errors
- [ ] `DATABASE_URL=sqlite:///local.db python scripts/run_demo_predictions.py` — reports predictions created/updated, zero errors
- [ ] `DATABASE_URL=sqlite:///local.db python scripts/demo_healthcheck.py` — exits zero, `"errors": []`, `"warnings": []`
- [ ] `DATABASE_URL=sqlite:///local.db uvicorn app.main:app --reload` — starts on port 8000

## Frontend

- [ ] `cd frontend && npm run dev` — starts on port 5000
- [ ] Open `http://localhost:5000/map`

## Map QA

- [ ] Markers are visible immediately — no toggle required
- [ ] Click a marker **without** toggling any filter first — popup opens on the first click
- [ ] Popup shows prediction section (delay probabilities and drivers)
- [ ] "View project details →" navigates to the project detail page

## Project Detail QA

- [ ] Overview tab renders without errors
- [ ] Evidence tab loads without a backend 500
- [ ] Edit coordinates opens the coordinate editor
- [ ] Submitting an invalid coordinate (e.g. latitude > 90) is rejected with an error message

## Data Hygiene

- [ ] `curl http://127.0.0.1:8000/projects` — no `coordinate_source` values of `manual_capture` or `starter_dataset` (legacy values)
- [ ] `git status --short` — none of the following are staged:
  - `local.db`
  - `node_modules/`
  - `frontend/dist/`
  - `*.csv` runtime files
  - `*.json` runtime files
  - geocoding cache files
  - `backend/data/exports/`
  - `attached_assets/`
  - `__pycache__/`

## Deterministic Baseline Disclaimer

- [ ] The UI shows **"Deterministic baseline — not yet statistically calibrated"** where prediction scores are displayed (not removed or hidden)
