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

## Dependencies
- fastapi, uvicorn[standard], sqlalchemy, alembic, pydantic, psycopg[binary] (PostgreSQL), gunicorn (production)
