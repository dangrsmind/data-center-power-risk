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

## Reset and seed demo data

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
