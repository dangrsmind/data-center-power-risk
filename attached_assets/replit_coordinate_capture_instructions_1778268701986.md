# Replit Instructions — Coordinate Capture and Correction Workflow

## Project

Data Center Power Risk

## Purpose of This Task

Implement and verify a coordinate capture/editing workflow so data center projects can be placed accurately on the Leaflet map.

This should support:

1. Manual latitude/longitude entry.
2. Editing and correcting existing coordinates.
3. Pick-from-map coordinate capture.
4. Coordinate precision labels.
5. Coordinate source/evidence fields.
6. Coordinate history.
7. Missing-coordinate review.
8. Safe git workflow in Replit.

Do not commit runtime artifacts.

---

# Current Stack

Backend:

```text
FastAPI
SQLite local.db
SQLAlchemy ORM
Alembic migrations
```

Frontend:

```text
React + Vite
Leaflet map
```

Existing pages:

```text
/discover
/map
```

Existing commands:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

```bash
cd frontend
npm run dev
```

---

# Replit Operating Rules

Use this git workflow:

```bash
git pull
```

Implement changes.

Then before pushing:

```bash
git status
git add backend frontend
git commit -m "Add coordinate capture and correction workflow"
git pull --rebase
git push
```

Never commit:

```text
local.db
node_modules
runtime JSON files
runtime CSV files
geocoding cache files
```

If any of those appear in `git status`, update `.gitignore` and remove them from staging.

Recommended `.gitignore` additions if missing:

```gitignore
# local database
local.db
*.db
*.sqlite
*.sqlite3

# Python runtime/cache
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/

# frontend
node_modules/
dist/

# runtime discovery/review artifacts
data/starter_sources/discovered_sources_v0_1.csv
data/starter_sources/discovery_decisions_v0_1.json
data/starter_sources/manual_source_captures_v0_1.json

# geocoding/runtime caches
data/geocoding/
*geocode_cache*.json

# logs/temp
*.log
.tmp/
tmp/
```

---

# Implementation Scope

Build the manual coordinate workflow only.

Do not add automated batch geocoding in this task.

Optional future geocoding warning: if public OpenStreetMap Nominatim is later used, follow the official policy: no heavy use, maximum one request per second, valid identifying User-Agent or Referer, and attribution. Do not batch geocode aggressively against public Nominatim.

Reference: https://operations.osmfoundation.org/policies/nominatim/

---

# Backend Implementation

## Step 1 — Inspect Existing Backend

Inspect these files or equivalent repo locations:

```text
backend/app/models*
backend/app/schemas*
backend/app/routes*
backend/app/main.py
backend/alembic/
backend/migrations/
```

Find:

```text
Project model
Existing project response schema
Existing project list/map endpoint
Existing Alembic config
```

Preserve existing API behavior.

## Step 2 — Add Coordinate Fields

Add nullable fields to the project model if missing:

```python
latitude
longitude
coordinate_status
coordinate_precision
coordinate_source
coordinate_source_url
coordinate_notes
coordinate_confidence
coordinate_updated_at
coordinate_verified_at
```

Allowed coordinate status values:

```text
missing
unverified
verified
needs_review
```

Allowed coordinate precision values:

```text
exact_site
parcel
campus
city_centroid
county_centroid
state_centroid
approximate
unknown
```

Allowed source values for UI dropdown:

```text
manual_review
project_announcement
utility_filing
county_record
company_website
inferred_from_city
imported_dataset
other
```

## Step 3 — Add Coordinate History Table

Create a model/table similar to:

```text
ProjectCoordinateHistory
```

Fields:

```text
id
project_id
old_latitude
old_longitude
new_latitude
new_longitude
old_coordinate_precision
new_coordinate_precision
old_coordinate_status
new_coordinate_status
source
source_url
notes
changed_by
created_at
```

Every coordinate update or clearing action must write a history row.

## Step 4 — Create Alembic Migration

Create migration:

```bash
cd backend
source .venv/bin/activate
alembic revision --autogenerate -m "add project coordinate workflow"
```

Review the generated migration before running it.

The migration should:

```text
- Add missing project coordinate columns.
- Create coordinate history table.
- Preserve existing data.
- Set coordinate_status = "missing" where coordinates are absent.
- Set coordinate_status = "unverified" where coordinates exist but status is null.
```

Then run:

```bash
alembic upgrade head
```

If autogenerate is not configured, write the migration manually in the repo's existing migration style.

## Step 5 — Add Schemas and Validation

Add a request schema equivalent to:

```python
class ProjectCoordinateUpdate(BaseModel):
    latitude: float
    longitude: float
    coordinate_precision: str
    coordinate_status: str = "verified"
    coordinate_source: str | None = None
    coordinate_source_url: str | None = None
    coordinate_notes: str | None = None
    coordinate_confidence: float | None = None
    changed_by: str | None = "manual"
```

Validation:

```text
latitude: -90 to 90
longitude: -180 to 180
coordinate_confidence: blank/null or 0 to 1
coordinate_status: missing, unverified, verified, needs_review
coordinate_precision: exact_site, parcel, campus, city_centroid, county_centroid, state_centroid, approximate, unknown
```

## Step 6 — Add API Endpoints

Add:

```http
GET /projects/missing-coordinates
```

Returns projects where:

```text
latitude is null
OR longitude is null
OR coordinate_status in ("missing", "needs_review")
```

Add:

```http
PATCH /projects/{project_id}/coordinates
```

Behavior:

```text
- Validate payload.
- Load project.
- Write history row with old and new values.
- Update coordinate fields.
- Set coordinate_updated_at.
- Set coordinate_verified_at if status is verified.
- Return updated project.
```

Add:

```http
GET /projects/{project_id}/coordinates/history
```

Returns newest-first history rows.

Add:

```http
DELETE /projects/{project_id}/coordinates
```

Behavior:

```text
- Write history row.
- Set latitude/longitude null.
- Set coordinate_status = missing.
- Set coordinate_precision = unknown.
- Set coordinate_updated_at.
- Return updated project.
```

---

# Frontend Implementation

## Step 7 — Inspect Existing Frontend

Inspect:

```text
frontend/src
frontend/src/pages
frontend/src/components
frontend/src/api
frontend/src/routes
```

Find:

```text
/map implementation
project API client
Leaflet marker rendering
popup code
routing setup
```

Preserve existing map behavior.

## Step 8 — Create Coordinate Editor Component

Create:

```text
ProjectCoordinateEditor
```

It should accept a project and callbacks like:

```text
onSave
onCancel
onClear
onPickFromMap
```

Fields:

```text
Latitude
Longitude
Coordinate status
Coordinate precision
Coordinate source
Coordinate source URL
Coordinate confidence
Notes
```

Required fields:

```text
Latitude
Longitude
Coordinate status
Coordinate precision
```

Validation before submit:

```text
latitude must be numeric and between -90 and 90
longitude must be numeric and between -180 and 180
confidence must be blank or between 0 and 1
status is required
precision is required
```

Default values for new manual entry:

```text
coordinate_status = verified
coordinate_precision = exact_site
coordinate_source = manual_review
coordinate_confidence = 0.8
```

## Step 9 — Add Map Popup Editing

In `/map` marker popups, show:

```text
Coordinate status
Coordinate precision
Coordinate confidence
Coordinate source
Last updated
```

Add popup button:

```text
Edit coordinates
```

Clicking opens `ProjectCoordinateEditor`.

After save:

```text
- Refresh project/map data.
- Move marker to new lat/lon.
- Close editor or show saved confirmation.
```

## Step 10 — Add Pick Coordinates from Map

Add editor button:

```text
Pick coordinates from map
```

Behavior:

```text
1. User clicks button.
2. Map enters coordinate-picking mode.
3. Next map click fills latitude/longitude in editor.
4. Preview marker moves to selected point.
5. User must click Save to persist.
6. Cancel exits pick mode without saving.
```

Do not auto-save on map click.

## Step 11 — Add Missing Coordinate Review UI

Create one of:

```text
/coordinates
```

or:

```text
/map?filter=missing-coordinates
```

Prefer `/coordinates` if routing is easy.

Call:

```http
GET /projects/missing-coordinates
```

Show table columns:

```text
Project name
Developer
Utility
City
County
State
Coordinate status
Coordinate precision
Action: Add/Edit
```

Action opens the coordinate editor.

## Step 12 — Update Marker Filtering

Default map behavior:

```text
exact_site / parcel / campus:
  show normally

city_centroid:
  show, but label as city-level in popup

county_centroid:
  show, but label as county-level in popup

state_centroid / approximate:
  hide unless "Show approximate coordinates" is enabled

unknown / missing:
  do not show
```

Add map control:

```text
Show approximate coordinates
```

---

# Data Quality Behavior

Use these defaults:

```text
Exact manually entered site:
  status = verified
  precision = exact_site
  source = manual_review
  confidence = 0.8

City-level coordinate:
  status = unverified
  precision = city_centroid
  source = inferred_from_city
  confidence = 0.4

County-level coordinate:
  status = unverified
  precision = county_centroid
  source = inferred_from_city
  confidence = 0.3

Questionable coordinate:
  status = needs_review
```

Suspicious coordinate warnings:

```text
- coordinate is 0,0
- exact_site has no source URL and no notes
- coordinate state mismatch, only if existing state-boundary logic already exists
```

Reject invalid lat/lon ranges. Warnings may be non-blocking.

---

# Backend Test Checklist

Run or add tests for:

```text
PATCH coordinates saves valid lat/lon
PATCH rejects latitude > 90
PATCH rejects latitude < -90
PATCH rejects longitude > 180
PATCH rejects longitude < -180
PATCH rejects invalid status
PATCH rejects invalid precision
PATCH rejects invalid confidence
PATCH creates history row
GET missing-coordinates returns missing projects
GET missing-coordinates returns needs_review projects
GET coordinate history returns newest-first rows
DELETE coordinates clears coordinates
DELETE coordinates creates history row
```

Run:

```bash
cd backend
source .venv/bin/activate
pytest
```

If there is no test setup, perform the manual QA below and document anything not covered by automated tests.

---

# Manual QA in Replit

## Start Backend

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload
```

## Start Frontend

In a separate shell:

```bash
cd frontend
npm run dev
```

## Verify Backend Endpoints

Use browser, curl, or FastAPI docs.

Check:

```http
GET /projects/missing-coordinates
```

Pick one project ID.

Update coordinates:

```http
PATCH /projects/{project_id}/coordinates
```

Example payload:

```json
{
  "latitude": 39.8283,
  "longitude": -98.5795,
  "coordinate_precision": "approximate",
  "coordinate_status": "needs_review",
  "coordinate_source": "manual_review",
  "coordinate_source_url": "",
  "coordinate_notes": "Manual test coordinate; replace with real source.",
  "coordinate_confidence": 0.2,
  "changed_by": "manual"
}
```

Check history:

```http
GET /projects/{project_id}/coordinates/history
```

Clear coordinates:

```http
DELETE /projects/{project_id}/coordinates
```

## Verify Frontend

Manual checklist:

```text
1. Open /map.
2. Confirm existing markers still render.
3. Open the coordinate editor from a marker popup.
4. Edit latitude/longitude.
5. Save.
6. Confirm marker moves.
7. Confirm popup metadata updates.
8. Use "Pick coordinates from map".
9. Click map.
10. Confirm editor fields update.
11. Save.
12. Confirm marker moves to clicked location.
13. Open /coordinates or missing-coordinate filter.
14. Confirm missing projects appear.
15. Add coordinates to a missing project.
16. Confirm it appears on the map.
17. Mark one project as approximate.
18. Confirm approximate toggle hides/shows it.
19. Clear coordinates.
20. Confirm project disappears from default map.
```

---

# Final Git Checks

Before commit:

```bash
git status
```

Make sure these are not staged:

```text
local.db
node_modules
data/starter_sources/discovered_sources_v0_1.csv
data/starter_sources/discovery_decisions_v0_1.json
data/starter_sources/manual_source_captures_v0_1.json
data/geocoding/*
```

Then:

```bash
git add backend frontend .gitignore
git commit -m "Add coordinate capture and correction workflow"
git pull --rebase
git push
```

If migration files are under a backend migration directory, include them in the commit.

---

# Acceptance Criteria

Complete when:

```text
- Alembic migration applies.
- Backend starts.
- Frontend starts.
- Projects support latitude/longitude plus coordinate metadata.
- Users can add missing coordinates.
- Users can edit existing coordinates.
- Users can clear coordinates.
- Every update or clear creates coordinate history.
- Missing-coordinate projects can be reviewed.
- Map updates after edits.
- Approximate coordinates are clearly labeled.
- Approximate coordinates can be hidden.
- Invalid lat/lon values are rejected.
- Runtime files are not committed.
```

---

# Failure Handling

If something breaks:

1. Do not push.
2. Capture the exact command and traceback.
3. Check whether the failure is backend migration, backend API, frontend compile, or map runtime.
4. Fix the smallest failing layer first.
5. Re-run the relevant command.
6. Only commit after backend and frontend start successfully.

Useful commands:

```bash
git status
git diff
git diff --staged
```

Rollback an accidental staged runtime file:

```bash
git reset HEAD local.db
```

If a runtime file was committed accidentally, remove it from git tracking without deleting the local file:

```bash
git rm --cached local.db
```
