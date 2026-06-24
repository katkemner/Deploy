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

- **Project Mode (primary flow):** describe a project (goal, deadline/budget
  targets, objective), edit tasks in the Project Task Builder (preloaded with
  the 10 sample tasks), pick your Current Team with a live coverage preview, and
  **Run Project Simulation** to compare five staffing options (Current,
  AI-Assisted Current, Recommended Balanced, Fastest, Lowest-Cost) with a
  recommendation summary and comparison table.
- **Task routing (human vs AI):** each task gets a routing recommendation
  (AI_ONLY / AI_FIRST_HUMAN_REVIEW / HUMAN_FIRST_AI_ASSIST / HUMAN_ONLY /
  ESCALATE) with 1–5 suitability scores, review/rework-hour estimates, and an
  explanation. The comparison table shows review burden, rework, net AI hours,
  and a reviewer-bottleneck flag; the recommendation says whether AI actually
  saves time or just shifts work to reviewers. Use **Preview task routing** to
  see the table before running a full simulation.
- **Uncertainty analysis (Monte Carlo):** for the selected current team, runs
  the scheduler hundreds of times over per-task effort ranges and shows
  P10/P50/P90 duration & cost, deadline/budget probabilities, and a duration
  histogram. Reproducible via a seed.
- **Routing provenance (“Why?”):** each routed task has an expandable **Why?**
  panel showing, for every score and routing output, where it came from
  (manual input / matched public prior / built-in heuristic / default fallback),
  with a source name, confidence, and explanation.
- **Prior-backed scoring toggle (opt-in):** a *Use public priors for scoring*
  checkbox in *Data and Settings* (off by default). When on, matched public
  priors supply/blend the routing scores; the **Why?** panel shows the matched
  prior, its confidence, and the blend ratio, with a warning when MEDIUM.
- **Evidence Priors (read-only):** under *Data and Settings*, a panel lists the
  loaded public evidence-prior sources (name, type, weight, confidence) and
  counts, clearly marked *representative seed* and *not yet connected to
  routing*. It also shows a **Matched Prior Preview** — each sample task's
  closest prior with confidence, score, and explanation — labelled *"Preview
  only. Not yet used for scoring."*
- See live **API health** in the header.
- Under **Data and Settings** (collapsible, secondary): browse employees, AI
  agents, and project tasks loaded from the backend.
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
        ├── ScenarioComparison.jsx
        ├── ProjectMode.jsx          # primary Project Mode flow
        ├── ProjectTaskBuilder.jsx   # add/edit/delete tasks
        ├── CurrentTeamSelector.jsx  # pick team + coverage preview
        ├── RecommendationSummary.jsx
        ├── ProjectComparisonTable.jsx
        ├── RoutingTable.jsx         # task-level human/AI routing table
        └── UncertaintyPanel.jsx     # Monte-Carlo P10/P50/P90 + probabilities
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

**Project Mode (primary):**

1. The app loads with **Project Mode** as the first section and the header
   shows **API: ok**.
2. The Project Task Builder is preloaded with the 10 sample tasks.
3. You can add a task, edit a task, and delete a task.
4. In **Current team**, "Fill current best team" selects Sarah, Maya, Priya,
   Alex, Casey + AI Research Agent + AI QA Reviewer, and the coverage preview
   updates.
5. **Run Project Simulation** shows a **Recommendation Summary**, a **Compare
   Staffing Options** table, five option cards, and a **Task Routing** table.
6. **Preview task routing** shows the routing table (decision + scores +
   review/rework hours) before running a full simulation.
7. **Run uncertainty analysis** (Monte Carlo) shows P10/P50/P90 duration & cost,
   deadline/budget probabilities, and a histogram; re-running with the same seed
   gives identical numbers.
8. The **Data and Settings** section exists below and expands to reveal the
   employees/AI/tasks tables, CSV upload, scoring config, manual team builder,
   and full simulation.

**Data and Settings (secondary):**

9. **Run Full Simulation** returns 5 ranked team cards; **Compare** on two
   cards shows the comparison table.
10. Editing a weight and clicking **Save Config** shows "Config saved"; a
    negative weight shows a validation error.
11. Uploading a malformed CSV shows a validation error; re-uploading a valid
    file shows success and refreshes the table.
