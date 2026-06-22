# Workforce Simulator — Frontend

A local **React + Vite** dashboard for the Workforce Simulator MVP. It is a
clean, clickable demo that talks to the existing FastAPI backend — no
database, auth, or build pipeline beyond Vite.

## Prerequisites

- Node.js 18+ (tested on Node 22)
- The backend running locally (see below)

## Run it

**1. Start the backend** (from the `workforce_simulator` directory):

```bash
cd workforce_simulator
uvicorn src.api.app:app --reload
# serves http://127.0.0.1:8000  (docs at /docs)
```

**2. Start the frontend** (in a second terminal):

```bash
cd workforce_simulator/frontend
npm install
npm run dev
```

Open the app at **http://localhost:5173**.

> The frontend calls the backend at `http://127.0.0.1:8000` by default. To
> point at a different backend, set `VITE_API_BASE`, e.g.
> `VITE_API_BASE=http://localhost:9000 npm run dev`.

## What you can do

- See live **API health** in the header.
- Browse **employees, AI agents, and project tasks** loaded from the backend.
- **Upload** replacement CSVs (validated by the backend; the relevant table
  refreshes on success, errors are shown inline).
- Edit and save the **scoring config** (weights, required-coverage rule, team
  size constraints) with validation errors surfaced clearly.
- Build a **manual team** from checkboxes and simulate just that team — full
  metrics, missing skills, overloaded members, critical path, explanation,
  and a highlighted task-schedule table.
- **Run the full simulation** to see the top 5 ranked teams as cards, view any
  team's schedule, and **compare** two or more teams side by side.

## Project layout

```
frontend/
├── index.html
├── package.json
├── vite.config.js
└── src/
    ├── main.jsx
    ├── App.jsx                 # dashboard layout + data loading
    ├── api/client.js           # wraps every backend endpoint
    ├── styles/global.css
    └── components/
        ├── Header.jsx
        ├── HealthStatus.jsx
        ├── DataUploadPanel.jsx
        ├── ConfigPanel.jsx
        ├── EmployeeTable.jsx
        ├── AIAgentTable.jsx
        ├── TaskTable.jsx
        ├── ManualTeamBuilder.jsx
        ├── SimulationResults.jsx
        ├── TaskScheduleTable.jsx
        └── ScenarioComparison.jsx
```

## Build / checks

```bash
npm run build     # production build — also serves as a compile check
npm run preview   # preview the production build locally
```

There is no separate unit-test runner for this demo; `npm run build`
type-checks JSX and bundles, and the manual verification flow below covers the
key paths.

## Manual verification checklist

With both servers running, confirm:

1. The app loads and the header shows **API: ok**.
2. Employees, AI agents, and tasks tables populate.
3. **Run Full Simulation** returns 5 ranked team cards.
4. **Manual Team Builder** → "Fill current best team" (Sarah, Maya, Priya,
   Alex, Casey + AI Research Agent, AI QA Reviewer) → **Run** shows a valid
   team with 100% required coverage and a critical path.
5. Selecting **Compare** on two cards shows the comparison table.
6. Editing a weight and clicking **Save Config** shows "Config saved";
   entering a negative weight shows a validation error.
7. Uploading a malformed CSV shows a validation error; re-uploading a valid
   file shows a success message and refreshes the table.
