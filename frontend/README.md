# Power Risk Analyst Console — Frontend

React + Vite + TypeScript internal tool for reviewing data-center power risk.

---

## Running the frontend

```bash
cd frontend
npm install     # first time only
npm run dev     # starts dev server on port 5000
```

The Replit workflow named **"Start application"** runs `npm run dev` automatically, so no manual start is needed inside Replit.

---

## Mock mode

Mock mode is on by default. All data comes from `src/api/mock.ts` — no backend is required.

**Where it is controlled:** `src/api/adapter.ts`, top of file:

```ts
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "false";
```

As long as `VITE_USE_MOCK` is unset (or anything other than `"false"`), the app uses mock data.

---

## Switching to the real API

1. Create `frontend/.env.local`:

```
VITE_USE_MOCK=false
VITE_API_BASE_URL=http://localhost:5000
```

2. Restart the dev server.

That is the only change needed. All components import exclusively from `src/api/adapter.ts` — none import from `mock.ts` directly — so no component changes are required when switching modes.

---

## File structure

```
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
└── src/
    ├── main.tsx               # Entry point
    ├── App.tsx                # Router + Layout shell
    ├── index.css              # Global CSS variables and resets
    ├── api/
    │   ├── types.ts           # TypeScript interfaces (matches backend schema)
    │   ├── mock.ts            # Mock data fixtures
    │   └── adapter.ts         # API adapter — the only file that touches mock.ts
    ├── components/
    │   ├── layout/
    │   │   └── Layout.tsx     # Sidebar + main content shell
    │   ├── shared/
    │   │   ├── Badge.tsx      # RiskBadge, LifecycleBadge, StatusBadge
    │   │   ├── KeyValue.tsx   # Label/value display and grid
    │   │   └── ScoreBar.tsx   # Score bar and percentage display
    │   ├── projects/
    │   │   └── ProjectListTable.tsx   # Sortable, filterable project table
    │   └── detail/
    │       ├── ProjectDetailPanel.tsx # Project metadata header
    │       ├── PhaseList.tsx          # Phase breakdown table
    │       └── ScorePanel.tsx         # Full score + drivers + signals
    └── pages/
        ├── ProjectsPage.tsx       # Route: /
        └── ProjectDetailPage.tsx  # Route: /projects/:id
```

## Routes

| Path | View |
|------|------|
| `/` | Project list table |
| `/projects/:id` | Project detail (Overview / Phases / Score / Evidence Timeline tabs) |
