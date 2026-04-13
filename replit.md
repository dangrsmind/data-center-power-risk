# Power Risk Backend

## Overview
A FastAPI-based early-warning forecasting system for large U.S. data-center projects. It estimates the probability of project delays, downsizings, or cancellations due to constraints in power access, interconnection, or electrical infrastructure.

## Architecture
- **Framework:** FastAPI with Uvicorn
- **Database:** SQLite (local dev via `local.db`), PostgreSQL (production via `DATABASE_URL` env var)
- **ORM:** SQLAlchemy 2.0+ with Alembic migrations
- **Validation:** Pydantic 2.x
- **Package Manager:** pip / setuptools

## Project Structure
```
backend/
  app/
    api/routes/     - FastAPI route definitions
    api/deps.py     - Dependency injection (DB session)
    core/config.py  - Configuration and paths
    core/db.py      - Database engine and session setup
    core/enums.py   - Shared enumerations
    models/         - SQLAlchemy ORM models
    repositories/   - Data access layer
    services/       - Business logic layer
    schemas/        - Pydantic request/response models
    main.py         - FastAPI app entrypoint
  migrations/       - Alembic migration scripts
  scripts/          - Utility scripts (seed_demo_data.py)
  pyproject.toml    - Project dependencies
```

## Running Locally
The app runs via the "Start application" workflow:
```
cd backend && DATABASE_URL='' uvicorn app.main:app --host 0.0.0.0 --port 5000 --reload
```

When `DATABASE_URL` is not set, the app defaults to SQLite at `backend/local.db`.

## API Endpoints
- `GET /health` - Health check
- Routes defined in `app/api/routes/`

## Database
- **Local dev:** SQLite (`backend/local.db`) - auto-created on startup
- **Production:** Set `DATABASE_URL` env var to PostgreSQL connection string
- Tables auto-created via `Base.metadata.create_all()` on startup

## Backend Dependencies
- fastapi, uvicorn[standard], sqlalchemy, alembic, pydantic, psycopg[binary] (PostgreSQL), gunicorn (production)

---

## Frontend — Analyst Console

React + Vite + TypeScript internal tool for analysts. Lives in `/frontend/`.

### Frontend Stack
- **Framework:** React 18 + Vite 5
- **Language:** TypeScript
- **Routing:** React Router v6
- **Styling:** Plain CSS variables (no UI library)
- **Port:** 5000 (the active workflow)

### Frontend Structure
```
frontend/
  src/
    api/
      types.ts        # TypeScript interfaces matching backend schema
      mock.ts         # Mock data fixtures (7 projects, full detail)
      adapter.ts      # API adapter — swap VITE_USE_MOCK=false to use real backend
    components/
      layout/Layout.tsx
      shared/Badge.tsx, KeyValue.tsx, ScoreBar.tsx
      projects/ProjectListTable.tsx
      detail/ProjectDetailPanel.tsx, PhaseList.tsx, ScorePanel.tsx
    pages/
      ProjectsPage.tsx
      ProjectDetailPage.tsx
```

### Views
- `/` — Project list table (sortable, filterable by MW bucket / lifecycle / risk / RTO)
- `/projects/:id` — Project detail with 4 tabs: Overview, Phases, Score, Evidence Timeline

### Score Panel Fields
- current_hazard, deadline_probability
- project_stress_score, regional_stress_score, anomaly_score, evidence_quality_score
- top_drivers, weak_signal_summary, graph_fragility_summary

### Switching to Real Backend
In `frontend/src/api/adapter.ts`, set `VITE_USE_MOCK=false` in `.env` and point `VITE_API_BASE_URL` to the backend URL.
