# Workforce Simulator (MVP v2)

A command-line simulation engine that helps a manager compare different
combinations of **people + AI agents** for a project and predict outcomes
such as duration, cost, skill coverage, workload balance, productivity,
and risk.

This is an MVP focused on proving the **core simulation logic**. There is
no frontend, no database, and no API keys. All scoring is done with
**deterministic formulas** — no LLM is used to invent numbers, so the same
inputs always produce the same ranked output.

**New in v2:** required vs optional task skills, task dependencies,
resource-constrained **critical-path scheduling**, a **configurable**
weights/constraints file, and richer per-team output (validity, schedule,
critical path).

---

## What it does

Given a pool of employees, a pool of AI agents, and a list of project
tasks, the simulator:

1. Generates every valid team combination within the configured size
   limits (default **2–5 humans, 0–2 AI agents**).
2. Assigns each task to the best available team member.
3. **Schedules** the assigned tasks, respecting task dependencies and each
   worker's availability, to compute duration and the critical path.
4. Scores each team across several metrics and marks it valid or invalid.
5. Ranks the teams with a configurable weighted total score.
6. Prints the **top 5 valid teams** and saves full results to JSON and CSV,
   each with a plain-English explanation of *why* it ranked where it did.

---

## MVP walkthrough (read this first)

The **Workforce Simulator** helps a manager answer one question: *given this
project, which mix of people and AI agents should I use, and what outcome should
I expect?* Everything is **deterministic** — the same inputs always produce the
same output, and no LLM is used to invent numbers.

The primary flow is **Project Mode**. You describe a project (tasks, your current
team, an objective), run a simulation, and get five staffing options with a
recommendation, a human-vs-AI routing plan per task, an uncertainty analysis, and
a tradeoff view.

**The five staffing options:**

| Option | What it means |
|---|---|
| **Current Team** | Exactly the people + AI agents you selected (your baseline). |
| **AI-Assisted Current Team** | Your humans plus AI agents the engine adds where they improve coverage, speed, cost, or risk. |
| **Recommended Balanced Team** | The valid team with the best overall weighted score. |
| **Fastest Valid Team** | The valid team with the shortest estimated duration. |
| **Lowest-Cost Valid Team** | The cheapest valid team. |

A team is **valid** when it covers every required skill.

**Task routing** splits each task between humans and AI (AI_ONLY,
AI_FIRST_HUMAN_REVIEW, HUMAN_FIRST_AI_ASSIST, HUMAN_ONLY, or ESCALATE). From that
split it estimates **review hours** (human time checking AI output), **rework
hours** (expected time fixing AI mistakes), and **net AI time saved** (AI time
saved minus review + rework). Each routing number is traceable in a **Why?**
panel.

**Three optional scoring data sources** (all off by default, all independent):

- **Public priors** — built-in *representative seed* values (illustrative, not
  exact published figures). Toggle: *Use public priors for scoring*.
- **WORKBank priors** — your own *imported, normalized* WORKBank data. Toggle:
  *Use WORKBank for scoring*. Takes precedence over public priors.
- **Calibration multipliers** — adjustments derived from *your approved
  historical calibration*. Toggle: *Use approved calibration multipliers* (in the
  Calibration panel).

When all three are off, scoring uses only your manual inputs and the built-in
skill heuristics. Each one, when enabled, **can change the recommendation** — and
every affected number is labelled with its source (manual / public prior /
WORKBank / heuristic / fallback / calibration).

The **Pareto Tradeoff View** marks which staffing options are *non-dominated*
(no other option beats them on every objective at once). It is read-only context
and never changes the recommendation.

### Demo script

A ~5-minute click-through for a manual demo (start the API + frontend first —
see *Install & run* below):

1. **Open Project Mode** — the dashboard leads with it.
2. **Review the sample project** — 10 preloaded tasks and a suggested current
   team. Click *Fill current best team* to populate humans + AI agents.
3. **Run simulation** — click *Run Project Simulation*.
4. **Compare staffing options** — read the recommendation summary, then the
   five option cards and the comparison table (cost, duration, review/rework,
   reviewer bottleneck).
5. **Open a task routing Why? panel** — expand any routing row to see each 1–5
   score's source and the routing rationale.
6. **Review uncertainty** — run the Monte Carlo panel for P10/P50/P90 duration &
   cost. The deadline/budget probabilities also appear when those targets are set
   (the sample pre-fills them; clear a field to omit it).
7. **Review the Pareto Tradeoff View** — see which options are on the frontier
   and what tradeoff each represents.
8. **Review priors and calibration settings** — open *Data and Settings*: the
   three scoring toggles (all off by default), the Evidence Priors panel
   (including WORKBank import status), and the Calibration panel.

### Intentionally NOT built yet

This MVP focuses on the deterministic simulation core. It deliberately does
**not** include: authentication / user accounts, a database (data lives in local
CSV/JSON files), or payments. **Scoring is entirely formula-driven and never
calls an LLM.** The one optional AI feature is an *input-assist* layer: uploading
a project brief can draft editable tasks for you (see
[AI-assisted task drafting](#ai-assisted-task-drafting-from-a-brief-optional)).
It only fills the editable task list — it never scores, routes, schedules, or
runs the engine, and it's off unless an Anthropic API key is configured.

---

## Project structure

```
workforce_simulator/
├── README.md
├── requirements.txt
├── config/
│   └── scoring_weights.json   # weights + team constraints (editable)
├── data/
│   ├── employees.csv          # the human talent pool
│   ├── ai_agents.csv          # the available AI agents
│   └── project_tasks.csv      # the work, with deps + required flags
├── src/
│   ├── main.py                # CLI entry point (run this)
│   ├── config_loader.py       # loads scoring_weights.json
│   ├── priors.py              # public evidence priors (foundation + loader)
│   ├── prior_matching.py      # deterministic task-to-prior matching (preview)
│   ├── calibration.py         # historical actuals vs predictions (informational)
│   ├── data_loader.py         # reads CSVs into model objects
│   ├── models.py              # Worker / Task / Team / Assignment models
│   ├── simulator.py           # task assignment + per-team metrics
│   ├── scheduler.py           # critical-path scheduling
│   ├── scoring.py             # deterministic scoring formulas
│   ├── optimizer.py           # team generation, ranking, explanations
│   ├── exporter.py            # writes results.json / results.csv
│   └── api/                   # FastAPI layer (thin wrapper over the engine)
│       ├── __init__.py        # sets up imports
│       ├── app.py             # FastAPI app (uvicorn entry point)
│       ├── routes.py          # endpoints, delegating to the engine
│       ├── brief_extract.py   # deterministic .docx/.pdf text extraction (no LLM)
│       ├── brief_parser.py    # LLM input-assist: brief text -> draft tasks
│       └── schemas.py         # Pydantic request/response models
├── outputs/
│   ├── results.json           # full results (generated)
│   └── results.csv            # flat summary (generated)
└── tests/
    ├── test_simulator.py      # engine unit tests
    └── test_api.py            # API tests
```

---

## Install & run

Requires **Python 3.8+**. The only third-party dependency is `pandas`.

```bash
cd workforce_simulator
pip install -r requirements.txt
python src/main.py
```

This prints the top 5 teams and writes `outputs/results.json` and
`outputs/results.csv`. **The CLI is unchanged** — adding the API did not
alter how `python src/main.py` behaves.

### Run the API server

The same engine is also exposed over HTTP via FastAPI. From the
`workforce_simulator` directory:

```bash
uvicorn src.api.app:app --reload
```

- API root: <http://127.0.0.1:8000>
- Interactive docs (Swagger UI): <http://127.0.0.1:8000/docs>

The API is a thin wrapper — every route calls the existing engine modules,
so it always reflects the current `data/` CSVs and
`config/scoring_weights.json`.

### Run the frontend (web dashboard)

A local **React + Vite** dashboard lives in [`frontend/`](frontend/) and talks
to the API above. Start the backend first, then in a second terminal:

```bash
cd workforce_simulator/frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The dashboard now leads with **Project Mode**
(below); the raw data tables, CSV upload, scoring config, manual team builder,
and full team-ranking simulation are tucked under a collapsible **Data and
Settings** section. See [`frontend/README.md`](frontend/README.md) for details.

### Deploy to staging

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/katkemner/Deploy)

One-click staging deploy on Render (FastAPI backend + Vite static frontend).
Click the button, sign in to Render, and click **Apply** — the two services are
declared in [`render.yaml`](../render.yaml), and the frontend is preconfigured
with the backend's public URL (`https://workforce-simulator-api.onrender.com`,
the default service name), so there's nothing to copy/paste. Full step-by-step
instructions (and a manual option) are in
**[`docs/deployment.md`](docs/deployment.md)**.

⚠️ Staging is a demo only — no auth, database, or tenant isolation, so do not
enter sensitive company data.

### Project Mode (the primary flow)

Project Mode reframes the app around a single question: *“Given this project,
what team should I use, should I add AI agents, and what outcome should I
expect?”* Instead of starting from raw data tables, the manager describes the
project and their current team, then compares **staffing options**.

**How to use it:**

0. **Load your team — Employee Digital Twin Seed Upload.** Upload an employee
   seed file (`.xlsx`/`.csv`) to use your own people, or click **Use demo
   roster**. The uploaded file becomes the active roster **for the session
   only** (in memory; nothing is written to disk). Required columns:
   `name, role/job_title, department/team, skills, capacity_hours,
   workload_hours` (an `employee_id` is generated if absent); `cost_rate` and
   `quality_score` default to 75 and 7 if missing and are **flagged** in the
   validation report. **Sensitive columns** (DOB, address, SSN/ID, contact,
   bank, medical, demographics, visa, disciplinary, …) are **dropped on ingest,
   never stored or returned**, and listed in the report. These are *seed
   profiles used for simulation — not full digital twins yet.* Real simulation
   is **gated**: until you upload a seed or choose the demo roster, the Run
   button is disabled and shows *“Upload employee data or choose demo roster.”*
   A badge shows **Uploaded seed active** or **Demo roster active**.
1. Fill in the project (name, goal, optional deadline-hours and budget targets,
   max team size, max AI agents) and pick an **optimization objective**
   (Balanced, Fastest delivery, Lowest cost, Best skill coverage, Best workload
   balance, Lowest risk, or **Most innovative** — the valid team with the
   strongest `innovation_score` for the actual project: cross-functional,
   human-led capacity to explore, prototype, validate, and launch, guarded by
   the project's real coverage/overload/bottleneck/AI-burden so an unfit or
   AI-churny team can't win).
2. Edit the **Project Task Builder** — it preloads the 10 sample tasks; add,
   edit, or delete tasks and pick dependencies from existing task names. No CSV
   editing required. *(Optional shortcut: upload a brief to draft tasks — see
   [AI-assisted task drafting](#ai-assisted-task-drafting-from-a-brief-optional).)*
3. Select your **Current Team** (humans + AI agents). A live required-skill
   coverage preview shows gaps before you simulate.
4. Click **Run Project Simulation**.

**What you get back** — six decision options, a comparison table, and a
deterministic recommendation summary:

| Option | Meaning |
|---|---|
| **Current Team** | Exactly the team you selected. |
| **AI-Assisted Current Team** | Your humans + AI agents the engine greedily adds where they improve coverage, speed, cost, or risk. |
| **Recommended Balanced Team** | The highest total-score valid team. |
| **Fastest Valid Team** | The valid team with the shortest estimated duration. |
| **Lowest-Cost Valid Team** | The cheapest valid team. |
| **Most Innovative Valid Team** | The valid team with the strongest cross-functional mix for exploring, prototyping, validating, and launching new ideas, scored by a deterministic `innovation_score` (0–100). |

The **Recommendation Summary** names the recommended option, why it won, the
main bottleneck, the critical path, the biggest risk, and a concrete *what to
change next* (e.g. “add a React-capable person”, “extend the deadline or move
Frontend build off Alex”, “add the recommended AI agents”). A team is
“**valid**” when it covers every required skill.

#### AI-assisted task drafting (from a brief, optional)

Typing every task by hand is the main friction in Project Mode. The **Start from
a project brief** panel removes it: upload a Word `.docx` or text-based PDF, and
Claude drafts editable tasks you review before anything runs. This is an
*input-assist* layer only — **the LLM never scores, routes, schedules,
optimises, or runs the engine**, which stays fully deterministic and auditable.

The flow is deliberately two-step and human-gated:

1. **Upload** a `.docx` or text-based PDF.
2. The backend **extracts the text deterministically** (`python-docx` / `pypdf`,
   no OCR) and shows a **preview** — `POST /projects/extract-brief-text`. No file
   is persisted; only in-memory text is processed.
3. After a **staging privacy warning**, you explicitly click **Generate draft
   tasks with AI** — `POST /projects/parse-brief` sends only the confirmed text
   to Claude (`claude-opus-4-8`) via the Anthropic SDK's structured-output
   `messages.parse()`.
4. Claude returns **draft tasks**. `required_skill` is constrained to the team's
   real skill vocabulary (employee skills + AI-agent capabilities, injected into
   the prompt); anything outside it — or any AI-estimated effort — is **flagged
   for review**. Reconciliation is re-checked in code, so an invented skill can't
   slip through even if the model ignores the instruction.
5. You **review and edit** the drafts, click **Use these tasks**, and they load
   into the normal Project Task Builder. From there the existing simulation runs
   unchanged.

Setup is one optional env var, `ANTHROPIC_API_KEY` (see
[deployment](docs/deployment.md#enabling-ai-task-drafting-optional)). If it's not
set, the drafting step returns a clear `503` and **manual entry keeps working** —
the feature is purely additive. v1 supports `.docx` and text-based PDFs only (no
OCR for scanned PDFs), and uploaded files are never stored.

> ⚠️ With a key set, the extracted brief text is sent to Anthropic. On the
> staging demo, **do not upload sensitive company data.**

#### How `POST /simulate/project` works

The endpoint accepts a **JSON project scenario** instead of reading
`project_tasks.csv`:

```json
{
  "project_name": "Sample Project",
  "project_goal": "Ship the MVP",
  "deadline_target_hours": 90,
  "budget_target": 15000,
  "optimization_objective": "balanced",
  "team_constraints": { "max_humans_per_team": 5, "max_ai_agents_per_team": 2 },
  "tasks": [ { "task": "Backend API", "required_skill": "API", "effort_hours": 35,
               "priority": 2, "dependencies": [], "is_required": true } ],
  "current_team_human_names": ["Sarah", "Maya", "Priya", "Alex", "Casey"],
  "current_team_ai_agent_names": ["AI Research Agent", "AI QA Reviewer"]
}
```

It uses the current employees/AI agents from CSV, uses the **tasks from the
request body** (it does **not** read or overwrite `project_tasks.csv`),
simulates the current team and an AI-assisted version, ranks all valid teams to
find the balanced/fastest/cheapest picks, and returns the options + comparison
table + recommendation. It reuses the existing engine (`optimizer`,
`simulator`, `scheduler`, `scoring`) — no scoring or scheduling logic is
duplicated. Everything is deterministic; no LLM is used.

**Known limitations (Project Mode MVP):** the recommended option follows the
chosen objective strictly (e.g. “Balanced” picks the top total-score team even
if your AI-assisted current team is close and cheaper — the summary points this
out so you can choose differently); the AI-assist greedy adds agents one at a
time by a fixed coverage→speed→cost→risk priority; task dependencies are
respected only within the submitted task set; and cost efficiency is normalised
across the generated team population for the run.

#### Tradeoff view — Pareto-front preview (read-only)

Alongside the single recommendation, `POST /simulate/project` returns a
**Pareto-front preview** that marks which of the five staffing options are
**non-dominated** across ten objectives — minimize *duration, cost, human hours,
review hours, expected rework hours, risk*; maximize *skill coverage,
productivity, workload balance, delivery confidence*.

Option *A dominates* option *B* when A is at least as good as B on **every**
objective and strictly better on **at least one**. An option is **Pareto-optimal**
when nothing dominates it: you cannot improve any objective without sacrificing
another. The response adds two keys:

- `pareto_front` — one `ParetoOption` per staffing option: `option_id`,
  `option_name`, `is_pareto_optimal`, `dominated_by`, `dominates`,
  `tradeoff_summary`, `objective_values` (the ten values), `strengths`,
  `weaknesses`.
- `pareto_explanation` — a deterministic paragraph naming the frontier options
  and noting the recommendation's place on it.

This is **informational only**: it does not re-rank options, change the
recommendation, or touch scoring/routing. If the recommended option happens to
be dominated, the explanation (and the UI's **Tradeoff View** section) adds a
warning — but the recommendation is left unchanged. The frontend renders the
recommended option, the Pareto-optimal options and the tradeoff each represents
(fastest, lowest cost, lowest risk, most balanced, …), and an objective matrix.

### Task-level human/AI routing

Before scheduling, each task gets a deterministic **routing recommendation** for
how humans and AI should split the work (`src/routing.py`). Every task is scored
1–5 on nine dimensions — `ai_capability_fit`, `human_judgment_need`,
`verification_ease`, `error_cost`, `context_sensitivity`, `repetition_level`,
`speed_value`, `human_learning_value`, `collaboration_value` — derived from a
per-skill profile table (with small adjustments for required/optional and
priority, and optional per-task overrides via `routing_scores`). From those
scores a rule set assigns one of:

| Routing | When |
|---|---|
| **AI_ONLY** | high AI fit + high repetition + easy verification + low judgment + low error cost |
| **AI_FIRST_HUMAN_REVIEW** | strong AI fit and verifiable, but human approval still adds value |
| **HUMAN_FIRST_AI_ASSIST** | human judgment leads; AI accelerates research/drafting/analysis/QA/formatting |
| **HUMAN_ONLY** | two or more of: high error cost, hard to verify, high context, heavy judgment |
| **ESCALATE** | inputs missing (unprofiled skill) or scores too uncertain |

Each routed task also gets an **explanation**, a **review-hours** estimate
(human time to check AI output, scaled by error cost and verification ease), an
**expected-rework-hours** estimate (AI errors needing fixing), and the **AI time
saved**. At the project level these roll up so the recommendation can say
whether **AI actually saves time or just shifts work to reviewers**
(`net_ai_time_saved = ai_time_saved − review − rework`). Per option, a
**reviewer-bottleneck** check flags when AI review burden exceeds ~35% of the
team’s human capacity (a team with no AI agents carries no review burden).

Routing surfaces in two places:

* `POST /route/tasks` — routing table + summary for a set of tasks, no team
  needed (used by the “Preview task routing” button).
* `POST /simulate/project` — the response now also includes `task_routing`,
  `routing_summary`, per-option `review_burden_hours` / `expected_rework_hours`
  / `net_time_saved` / `reviewer_bottleneck`, and an `ai_time_verdict` in the
  recommendation.

**Routing limitations (MVP):** routing is **advisory** — it informs the
review/rework/bottleneck analysis but does not yet change how tasks are assigned
or scheduled; suitability scores come from a fixed skill-profile table (override
per task if needed); and review/rework hours are transparent heuristics, not
calibrated against real data.

#### Routing provenance (explainability)

Every routing record carries **provenance** — metadata explaining *where each
value came from* — without changing any value or decision (`src/provenance.py`).
Three source types are used:

- **`MANUAL_INPUT`** — you supplied it (a per-task `routing_scores` override).
- **`EXISTING_HEURISTIC`** — the built-in deterministic logic produced it (a
  skill profile, a routing rule, or a formula).
- **`DEFAULT_FALLBACK`** — a default was used because nothing else applied (an
  unprofiled skill, or a score missing from a partial override).

Each `/route/tasks` and `/simulate/project` task-routing record gains:

- **`score_provenance`** — one entry per suitability score
  (`ai_capability_fit`, `human_judgment_need`, `verification_ease`,
  `error_cost`, `context_sensitivity`, `repetition_level`, `speed_value`,
  `human_learning_value`, `collaboration_value`).
- **`route_provenance`** — one entry each for `recommended_route`,
  `estimated_review_hours`, `expected_rework_hours`, and `net_ai_time_saved`.

Each entry has `field_name`, `value`, `source_type`, `source_name`,
`confidence` (a deterministic 0–1 number set by source type: manual 0.95,
heuristic 0.7, fallback 0.3), and a short `explanation`. In the UI, each routed
task has an expandable **“Why?”** panel listing these entries. This layer is
purely additive — it changes no score, formula, or routing decision.

### Monte-Carlo uncertainty analysis

The plain simulation returns single-number (point) estimates. Real projects are
uncertain, so `POST /simulate/uncertainty` (`src/montecarlo.py`) propagates that
uncertainty by running the **real critical-path scheduler many times**. Each
iteration samples every task's effort from a **triangular distribution** between
its optimistic, likely, and pessimistic estimates, then schedules the team and
records the resulting duration and cost. Over hundreds of iterations it reports:

- **P10 / P50 / P90** (and min/mean/max) for **duration** and **cost**,
- a **duration histogram**, and
- the **empirical probability** of meeting a deadline and staying within budget.

This is exactly the patent's "run a plurality of iterations… factoring in
unforeseen challenges, resource availability, or changes in project scope."
Nothing is invented — it is correct statistics over the ranges *you* supply.

- **Inputs:** the team (human + AI names), the tasks, optional per-task
  `effort_optimistic` / `effort_pessimistic` (otherwise a default band of
  0.8×–1.5× of `effort_hours` is used and shown back to you), `iterations`
  (default 500), and a `seed`.
- **Reproducible:** a fixed `seed` makes every run identical (the engine uses a
  seeded RNG), so results are deterministic and auditable.
- **Honest scope:** it propagates the uncertainty you enter — it does not invent
  accuracy. Outputs are only as good as the effort ranges provided; they are not
  calibrated against historical outcomes.

In the UI, the **Uncertainty analysis (Monte Carlo)** panel in Project Mode runs
this for the currently-selected team and shows P10/P50/P90 duration & cost, the
deadline/budget probabilities, and a duration histogram.

### Public evidence priors (foundation only)

A data foundation for *future* grounding of task routing in public evidence
(`src/priors.py`, `data/priors/public_priors_seed.json`). This slice ships the
structures, a validating loader, and a read-only API/UI — **the priors are not
yet connected to routing or scoring, and they change no behaviour.**

The seed file carries four sections, validated on load:

- **`source_weights`** (`PriorSourceWeight`) — one per source category, with a
  `source_weight` and `source_confidence` (both validated to 0–1).
- **`evidence_priors`** (`EvidencePrior`) — individual evidence points
  (`task_type`, `skill`, `occupation`, `metric_name`, `metric_value`, …).
- **`task_routing_priors`** (`TaskRoutingPrior`) — per task-type prior scores
  (`ai_capability_fit_prior`, `human_judgment_need_prior`, … `human_agency_prior`),
  each validated to 0–100, with `source_refs`.
- **`hybrid_guardrail_priors`** (`HybridGuardrailPrior`) — `hybrid_bonus_or_penalty`
  plus `human_ai_synergy_prior` / `human_augmentation_prior` (0–100).

The five seed source categories are `WORKBank_STYLE`,
`NATURE_HUMAN_AI_META_ANALYSIS`, `BLS_ORS_STYLE`, `SOFTWARE_WORKFLOW_PRIOR`, and
`AI_AGENT_BENCHMARK_PRIOR`. **All seed values are representative placeholders,
not exact figures from those sources** — the file is marked
`representative_seed: true`. `GET /priors` returns the loaded sections, and a
read-only **Evidence Priors** panel under *Data and Settings* shows the sources,
weights, and counts with a clear "not yet connected to routing" note.

#### WORKBank importer (read-only; not connected to scoring)

`src/workbank.py` imports real **WORKBank** CSV exports into a single
normalized, local priors file and exposes them read-only. It reads three files
from `data/imports/workbank/` (git-ignored — place your own exports there):

- `task_statement_with_metadata.csv` — the task spine: `task_id`,
  `task_statement`, `occupation_title`, `onet_soc_code`, `task_type`, and the
  four 0–1 requirement metadata columns (`physical_action_requirement`,
  `uncertainty_or_high_stakes_requirement`, `domain_expertise_requirement`,
  `interpersonal_communication_requirement`).
- `domain_worker_desires.csv` — worker survey rows (`worker_automation_desire`,
  `worker_desired_has`), many per task, averaged.
- `expert_rated_technological_capability.csv` — expert rating rows
  (`expert_ai_capability`, `expert_feasible_has`), many per task, averaged.

The importer validates required columns, joins the survey/rating rows onto each
task **by `task_id` (with a stable task-text fallback)**, computes per-task
averages and sample counts, derives a `source_confidence` from data coverage,
and writes `data/priors/workbank_normalized.json` (also git-ignored). It **fails
clearly** when a file is missing or a required column is absent/malformed.

`GET /priors/workbank` returns `import_status` (`imported` / `not_imported` /
`error`), `task_count`, `occupation_count`, `normalized_priors`, and
`validation_warnings`. The **Evidence Priors** panel shows the import status,
task/occupation counts, any missing-file warning, and the label *"Read-only. Not
yet connected to scoring."* **The normalized WORKBank data is NOT used by
routing, scoring, prior-backed scoring, calibration, Monte Carlo, or Project
Mode — it changes no simulation behaviour.**

#### WORKBank matching preview (preview only)

`src/workbank_matching.py` deterministically matches each project task to its
closest **imported WORKBank task**, reusing the same normalisation/similarity
primitives and confidence thresholds as the public-prior matcher (HIGH ≥ 0.70,
MEDIUM ≥ 0.45, else LOW). It blends a primary text score (token Jaccard +
`difflib` over the project task's descriptive text vs the WORKBank `task_text`)
with deterministic task-type and skill/occupation bonuses into one score.

`POST /priors/workbank/match-tasks` returns one `WorkbankTaskMatch` per task
(`project_task_id`, `project_task_name`, `matched_workbank_task_id`,
`matched_task_text`, `matched_occupation_title`, `matched_task_type`,
`match_score`, `match_confidence`, `match_method`, `explanation`, and up to three
`candidate_matches`). `POST /simulate/project` additionally annotates each
`task_routing` row with a read-only `workbank_match_preview`, shown in the
Project Mode routing **Why?** panel under *"Preview only. Not yet used for
scoring."* **The match is informational — it does NOT affect routing, scoring,
review/rework, calibration, Pareto, Monte Carlo, the optimizer, or any
recommendation.**

#### WORKBank-backed scoring (opt-in, off by default)

A **separate** toggle, **`use_workbank_for_scoring`** (default **`false`**),
lets matched imported WORKBank tasks supply/blend the routing suitability
scores. It is independent of `use_public_priors_for_scoring` — existing
public-prior scoring keeps working as-is. When on, the per-field override order
is:

1. `MANUAL_INPUT` — a per-task `routing_scores` override
2. `MATCHED_WORKBANK_PRIOR` — a usable WORKBank match (HIGH/MEDIUM)
3. `MATCHED_PUBLIC_PRIOR` — when `use_public_priors_for_scoring` is also on
4. `EXISTING_HEURISTIC` — the built-in skill profile
5. `DEFAULT_FALLBACK`

WORKBank normalized fields map onto the 1–5 routing scores (`workbank_matching.workbank_scores`):
`ai_capability_fit`←`avg_expert_ai_capability`; `human_judgment_need`←mean of the
HAS values; `verification_ease`←inverse of `uncertainty_or_high_stakes_requirement`;
`error_cost`←`uncertainty_or_high_stakes_requirement`; `context_sensitivity`←`domain_expertise_requirement`;
`speed_value`←`avg_worker_automation_desire`; `collaboration_value`←HAS (peaking at
mid agency); `repetition_level`←`task_type` (only when recognised, else not filled).
Manual scores are never overwritten. Blend by match confidence: **HIGH** 80%
WORKBank / 20% heuristic, **MEDIUM** 50/50, **LOW** ignored.

Every WORKBank-influenced score carries full provenance: `field_name`, `value`,
`source_type: MATCHED_WORKBANK_PRIOR`, `source_name: WORKBank`, `confidence`,
`explanation`, `matched_workbank_task_id`, `matched_occupation_title`,
`match_confidence`, and `blend_ratio` (when blended). Task routing responses also
expose `workbank_scoring_enabled`, `matched_workbank_prior_used`,
`workbank_match_confidence`, and a `workbank_warning` (MEDIUM blend, or toggle-on
but no imported data). The **Use WORKBank for scoring** toggle lives under *Data
and Settings*, and the routing **Why?** panel shows the source of each score
(manual / WORKBank / public prior / heuristic / fallback) plus the matched
WORKBank task, occupation, confidence, and blend ratio. **With the toggle off
(the default) nothing changes.**

#### Prior matching preview (preview only)

`src/prior_matching.py` deterministically matches each project task to its
**closest** public prior, purely for explanation — **the match is not used by
routing, scoring, review/rework, Monte Carlo, the optimizer, or Project Mode.**
Matching normalises the task text (lowercase, strip punctuation, drop a small
stopword set, tokenize) and blends three deterministic signals: skill equality/
overlap, a text score (token **Jaccard** + `difflib` sequence ratio), and an
optional task-type match. The blended score maps to confidence: **HIGH ≥ 0.70,
MEDIUM ≥ 0.45, else LOW**.

- `POST /priors/match-tasks` returns a `PriorMatch` per task (`project_task_id`,
  `matched_prior_id`, `matched_prior_type`, `matched_task_type`,
  `matched_skill`, `match_score`, `match_confidence`, `match_method`,
  `explanation`) plus up to three candidate matches.
- `POST /simulate/project` task-routing records gain **informational-only**
  `prior_match_preview`, `prior_match_confidence`, and `prior_match_explanation`
  fields (added in the API layer; the simulation itself is untouched).
- The **Evidence Priors** panel shows a **Matched Prior Preview** table for the
  sample tasks, labelled *"Preview only. Not yet used for scoring."*

#### Prior-backed scoring (opt-in, off by default)

A config flag, **`use_public_priors_for_scoring`** (default **`false`**), lets
matched public priors actually supply the routing suitability scores. **When it
is false, all routing and scoring behaviour is exactly as before** (guaranteed
and tested). When true, scores follow this override order:

1. **MANUAL_INPUT** — a per-task `routing_scores` override (never overwritten)
2. **MATCHED_PUBLIC_PRIOR** — from the closest matched `TaskRoutingPrior`
3. **EXISTING_HEURISTIC** — the skill profile
4. **DEFAULT_FALLBACK** — a neutral default

Eight of the nine suitability scores can be prior-backed (`ai_capability_fit`,
`human_judgment_need`, `verification_ease`, `error_cost`, `context_sensitivity`,
`repetition_level`, `speed_value`, `collaboration_value`); `human_learning_value`
has no prior and stays heuristic. The prior's 0–100 value is converted to the
1–5 scale and **blended** with the heuristic by match confidence: **HIGH = 80%
prior / 20% heuristic, MEDIUM = 50/50, LOW = ignored** (not used). Because the
blended scores feed the routing rules, a route decision **may change — but only
when the flag is on**.

Every prior-backed score carries provenance with `source_type =
MATCHED_PUBLIC_PRIOR`, plus `matched_prior_id`, `match_confidence`, and
`blend_ratio`. Each task routing record also reports `public_priors_enabled`,
`matched_prior_used`, `prior_match_confidence`, and a `prior_warning` when the
match is MEDIUM. The flag is exposed in `GET`/`POST /config`, respected by
`POST /route/tasks` and `POST /simulate/project`, toggled by a **"Use public
priors for scoring"** checkbox in *Data and Settings*, and explained in each
task's **"Why?"** panel (which shows the source, matched-prior confidence, and
blend ratio).

**Limitations:** priors are blended only where a heuristic profile exists;
matched-prior selection uses the deterministic text matcher; values remain
representative seeds, not calibrated data.

### Historical calibration scaffold (informational only)

`src/calibration.py` lets a user record the **actual** outcomes of a completed
project and compare them to what the simulator predicted. It computes signed
**error percentages** (duration, cost, human hours, review, rework), checks
whether the **bottleneck** was predicted correctly, and **suggests** multiplier
updates — `task_duration_multiplier`, `review_time_multiplier`,
`rework_multiplier`, `dependency_buffer_multiplier`, `skill_gap_penalty`,
`context_switching_penalty`. **These suggestions are informational and are never
applied** — no scoring or simulation behaviour changes (every comparison carries
`applied: false`). No ML, LLM, external API, or database: actuals live in a
local, git-ignored JSON file.

- `POST /calibration/actuals` — store a completed project's actuals and return
  its comparison.
- `POST /calibration/compare` — compare without storing.
- `GET /calibration/summary` — aggregate mean-absolute errors, bottleneck
  accuracy, and the biggest misses across all stored projects.

A **Calibration** panel under *Data and Settings* provides a form for entering
actuals, a prediction-vs-actual error table, the suggested multipliers, and the
label *"Calibration suggestions are not applied automatically."*

#### Manual calibration apply flow (opt-in, traceable)

Building on the scaffold, users can **review and manually apply** suggested
multiplier updates. Nothing is ever applied automatically — each proposal must
be explicitly selected and applied.

- `GET /calibration/proposals` — one `CalibrationUpdateProposal` per
  calibration multiplier per stored project (`current_value`, `suggested_value`,
  `reason`, `error_pct`, `confidence`, `applied`, `rejected`), plus the current
  calibration config.
- `POST /calibration/apply` — apply **only** the selected `proposal_ids`. Each
  applied proposal updates one of the six calibration multipliers
  (`task_duration_multiplier`, `review_time_multiplier`, `rework_multiplier`,
  `dependency_buffer_multiplier`, `skill_gap_penalty`,
  `context_switching_penalty`) and records provenance (`updated_by:
  CALIBRATION_APPLY_FLOW`, `source_project_id`, `previous_value`, `new_value`,
  `reason`). Returns applied vs skipped proposals and the updated config.
- `POST /calibration/reject` — mark proposals rejected (no config change).

The applied multipliers live in a **dedicated, git-ignored calibration config
file** (`data/calibration/applied_config.json`) — separate from
`scoring_weights.json` — so `POST /config` can never clobber them. Applying a
proposal only updates the calibration **config values** (traceably); whether the
engine then *consumes* them is governed by the consumption flag below.
Calibration **cannot** touch source weights, public prior values, or the routing
**decision rules** / task-matching logic — approved multipliers only scale the
duration, review/rework, and risk *estimates* when consumption is enabled.

The Calibration panel adds a proposals table (current vs suggested value,
reason, confidence, a select checkbox), **Apply selected** / **Reject selected**
buttons, and the warning *"Applying calibration updates may change future
simulation outputs."*

#### Calibration consumption (engine applies approved multipliers)

Once multipliers are approved (above), the engine **consumes** them on future
simulations:

- `task_duration_multiplier` and `dependency_buffer_multiplier` scale each task's
  scheduled duration (the latter only for tasks that have dependencies). Worker
  cost and workload are unchanged — only the schedule/critical path shift.
- `review_time_multiplier` and `rework_multiplier` scale the routing layer's
  estimated review and rework hours (the routing **decision** is never changed),
  and `net_ai_time_saved` is recomputed from the scaled values.
- `skill_gap_penalty` and `context_switching_penalty` raise the risk score in
  proportion to uncovered required skills and member overload, respectively.

A tri-state config flag, **`use_calibration_multipliers`**, controls this:

- `null` (default) — **auto**: enabled if an applied calibration config exists,
  otherwise disabled. So with no approved multipliers, **behaviour is identical**
  to before.
- `true` — consume approved multipliers (still neutral if none applied).
- `false` — ignore them **without deleting** the applied config.

Every simulation response (`/simulate/project`, `/simulate/uncertainty`,
`/route/tasks`) carries a calibration block: `calibration_multipliers_enabled`,
`calibration_multipliers_applied` (the effective values), and
`calibration_provenance` (per applied multiplier: `multiplier_name`, `value`,
`source_project_id`, `previous_value`, `reason`, `updated_by`). `GET
/calibration/active` reports the same block plus all current multiplier values
and descriptions. The Calibration panel adds a **"Use approved calibration
multipliers"** toggle, a read-only active-multipliers table, and the warning
*"Approved calibration multipliers may change future simulation outputs."*

Applied multipliers still live only in the **dedicated, git-ignored**
`data/calibration/applied_config.json` — consumption never reads or changes
source weights, public prior values, or the routing decision rules.

#### Endpoints

| Method & path | What it does |
|---|---|
| `GET /health` | Liveness check, returns `{"status": "ok"}` |
| `GET /config` | Current scoring weights + team constraints |
| `POST /config` | Validate and save new weights/constraints |
| `GET /employees` | Employees loaded from `data/employees.csv` |
| `GET /ai-agents` | AI agents loaded from `data/ai_agents.csv` |
| `GET /tasks` | Project tasks loaded from `data/project_tasks.csv` |
| `GET /priors` | Loaded public evidence priors (representative seed; not yet wired to routing) |
| `GET /priors/workbank` | Read-only normalized WORKBank import status + data (not connected to scoring) |
| `POST /priors/workbank/match-tasks` | Closest WORKBank task per project task (preview only; not used for scoring) |
| `POST /priors/match-tasks` | Closest-prior match per task (preview only; not used for scoring) |
| `POST /calibration/actuals` | Store a completed project's actuals + return the comparison |
| `POST /calibration/compare` | Compare actuals to predictions without storing |
| `GET /calibration/summary` | Aggregate error summary + biggest misses across stored actuals |
| `GET /calibration/proposals` | Multiplier-update proposals from stored actuals (nothing applied) |
| `POST /calibration/apply` | Apply only the selected proposals to the calibration config (traceable) |
| `POST /calibration/reject` | Mark selected proposals rejected (no config change) |
| `GET /calibration/active` | Active approved multipliers the engine is consuming (toggle state + provenance) |
| `POST /simulate` | Run the full engine; returns the top 5 ranked teams (and writes `outputs/`) |
| `POST /simulate/manual-team` | Simulate one chosen team (`human_names` + `ai_agent_names`); full result |
| `POST /simulate/project` | **Project Mode** — compare staffing options for a JSON project scenario (see above) |
| `POST /simulate/uncertainty` | **Monte Carlo** — P10/P50/P90 duration & cost + deadline/budget probabilities for a team |
| `POST /route/tasks` | **Task routing** — human/AI routing table + summary for a set of tasks |
| `POST /upload/employees` | Replace `employees.csv` from a validated CSV upload |
| `POST /upload/ai-agents` | Replace `ai_agents.csv` from a validated CSV upload |
| `POST /upload/tasks` | Replace `project_tasks.csv` from a validated CSV upload |
| `GET /outputs/latest` | The latest `results.json`, or 404 if none yet |

Example — simulate a specific team:

```bash
curl -X POST http://127.0.0.1:8000/simulate/manual-team \
  -H "Content-Type: application/json" \
  -d '{"human_names": ["Sarah","Maya","Priya","Alex","Casey"],
       "ai_agent_names": ["AI Research Agent","AI QA Reviewer"]}'
```

**Validation & safety.** The API rejects malformed CSV uploads (missing
columns or unparseable data), manual teams that reference unknown names,
configs with negative weights, and impossible team constraints (e.g.
`min > max`), each with a helpful error message. Uploads are validated
against the engine loader and only replace the real file on success.

> Note on manual-team `cost_efficiency_score`: cost efficiency is normalised
> across *all* teams, so for a single manual team there is no population to
> compare against and it is reported as `100`. Use `POST /simulate` when you
> need cost efficiency compared across teams.

### Run the tests

```bash
# with pytest (engine + API)
python -m pytest tests/

# or, without pytest installed
python tests/test_simulator.py   # engine
python tests/test_api.py         # API
```

The engine suite covers required-skill coverage, team validity (valid vs
invalid), dependency ordering, critical-path calculation, configurable
weights, and that the top-5 ranking excludes invalid teams when full required
coverage is mandatory. The API suite covers health, the data endpoints,
`POST /simulate`, manual-team simulation (including the current best team),
and the validation/error paths.

---

## The data files

### `employees.csv` — the human talent pool
`name, role, skills, capacity_hours, workload_hours, cost_rate, quality_score`

A human's **available hours** = `capacity_hours − workload_hours`, and their
`speed_multiplier` is always `1.0`.

### `ai_agents.csv` — the AI agents
`name, agent_type, capabilities, capacity_hours, cost_rate, quality_score, speed_multiplier`

AI agents have **no pre-existing workload**, so available hours equal
capacity. Because they work faster, a task needing `E` effort hours consumes
only `E / speed_multiplier` of an agent's time.

### `project_tasks.csv` — the work
`task, required_skill, effort_hours, priority, dependency_ids, is_required`

| field | meaning |
|---|---|
| `task` | task name (also used as its dependency id) |
| `required_skill` | the single skill needed to do it |
| `effort_hours` | nominal effort at human speed |
| `priority` | `1` = highest priority, assigned first |
| `dependency_ids` | `\|`-separated **task names** that must finish first (blank = none) |
| `is_required` | `true` = mandatory skill; `false` = optional |

To simulate a different scenario, edit these CSVs and re-run — no code
changes needed.

---

## Required vs optional skills

- **Required** tasks (`is_required = true`) represent skills the project
  *must* have. A team that cannot cover a required skill receives a **major
  score penalty**, and — if `require_full_required_skill_coverage` is on —
  is marked **invalid** and excluded from the ranking.
- **Optional** tasks (`is_required = false`) are nice-to-haves. Covering
  them *improves* the score (via productivity and the optional-coverage
  metric) but their absence never invalidates a team.

The ranking's skill-coverage component is driven by **required** coverage, so
required skills dominate which teams rise to the top.

## Task dependencies

Each task may depend on one or more earlier tasks via `dependency_ids`
(referenced by task name). In the sample data:

- *Frontend build* depends on *Prototype design*
- *QA testing* depends on *Frontend build* and *Backend API*
- *Documentation* depends on *QA testing*

A task cannot start until **all** of its dependencies have finished.

## Critical path & scheduling

Duration is no longer "total effort ÷ capacity". Instead `scheduler.py`
builds a real schedule:

1. Tasks are processed in dependency (topological) order, ties broken by
   priority then name for determinism.
2. Each task starts at the **later** of (a) when all its dependencies
   finish and (b) when its assigned worker becomes free — a worker is a
   single resource and can only do one task at a time.
3. Project **duration** = the latest task finish time.
4. The **critical path** is recovered by walking backwards from the
   last-finishing task through whatever constrained each task's start —
   either a dependency *or* a worker being busy.

That last point matters: if one person is the only holder of two skills,
their tasks serialise and *they* become the critical path even without a
formal dependency between those tasks. The schedule exposes `start_time`,
`finish_time`, and `is_on_critical_path` per task.

---

## Configurable scoring (`config/scoring_weights.json`)

```json
{
  "weights": {
    "skill_coverage": 30,
    "capacity_fit": 20,
    "productivity": 20,
    "workload_balance": 15,
    "cost_efficiency": 10,
    "low_risk": 5
  },
  "require_full_required_skill_coverage": true,
  "max_humans_per_team": 5,
  "min_humans_per_team": 2,
  "max_ai_agents_per_team": 2,
  "min_ai_agents_per_team": 0
}
```

- **`weights`** — relative importance of each scoring dimension. They are
  normalised to sum to 1.0 at load time, so any scale works. Raise
  `cost_efficiency` to favour cheaper teams, raise `workload_balance` to
  punish overloaded stars, etc.
- **`require_full_required_skill_coverage`** — when `true`, teams missing any
  required skill are invalid and excluded from the top 5. Set to `false` to
  keep them in the running (still penalised, just ranked lower).
- **Team constraints** — `min/max_humans_per_team` and
  `min/max_ai_agents_per_team` control which combinations are generated.

Edit the file and re-run `python src/main.py`; no code changes are needed.

---

## How the scores are calculated

All scores are 0–100 (higher is better) **except `risk_score`** (higher =
worse). The formulas live in [`src/scoring.py`](src/scoring.py).

| score | meaning | how it's computed |
|---|---|---|
| **skill_coverage_score** | % of *all* tasks the team can staff | `covered / total × 100` |
| **required_skill_coverage_score** | % of *required* tasks covered (drives ranking) | required covered / required total |
| **optional_skill_coverage_score** | % of *optional* tasks covered | optional covered / optional total |
| **capacity_fit_score** | are individuals within their hours? | `100 × (1 − overflow_hours / assigned_hours)` |
| **estimated_cost** | total project cost | Σ `assigned_hours × cost_rate` |
| **estimated_duration** | calendar time from the schedule | last task finish time (critical path) |
| **workload_balance_score** | how evenly work is spread | from the spread of member utilisation |
| **productivity_score** | throughput quality | `0.40×coverage + 0.20×quality + 0.20×speed + 0.20×capacity_fit` |
| **risk_score** | total risk (higher = worse) | `40×missing + 25×overload + 20×imbalance + 15×low_coverage` |
| **confidence_score** | how much to trust the result | starts from coverage, −15 per missing skill |
| **cost_efficiency_score** | cheapest team = 100, dearest = 0 | min-max normalised cost across all teams |

### Final ranking (`total_score`)

`total_score` is the weighted blend of the dimensions above (using the
**config weights**), where the skill-coverage slot uses **required** coverage.
On top of that, a **major required-skill penalty** (up to 40 points, scaled
by the fraction of required skills missing) is subtracted. Teams are then
sorted valid-first, then by total score (ties broken by lower risk, then
lower cost) for reproducible output.

---

## How to read the output

For each top team (terminal and `results.json`):

- **is_valid_team / invalid_reasons** — whether it covers all required
  skills (and why not, if invalid).
- the metrics above, plus **missing_required_skills** /
  **missing_optional_skills** and **overloaded_members**.
- **critical_path** — the ordered chain of tasks driving the duration.
- **task_schedule** — per task: `assigned_to`, `effort_hours`,
  `adjusted_effort_hours`, `start_time`, `finish_time`, `dependencies`,
  `is_on_critical_path`.
- **task_assignments** — who got each task.
- a deterministic **plain_english_explanation** covering why it ranked
  where it did, required-skill coverage, which AI agents helped and how, the
  biggest bottleneck, the critical path, and the main tradeoff.

### Interpreting invalid teams

With `require_full_required_skill_coverage: true` (the default), any team
that cannot staff a required skill is **invalid** and never appears in the
top 5 — even if it would otherwise score well. Flip the flag to `false` to
see those teams ranked (penalised) alongside the rest, which is useful for
spotting *what skill you are short of* and how close an almost-complete team
gets.

### Changing team constraints

Edit `min/max_humans_per_team` and `min/max_ai_agents_per_team` in the
config. For example, set both human bounds to `3` to compare only 3-person
human teams, or raise `max_ai_agents_per_team` to explore heavier AI use.

---

## What to build next

1. **Multi-skill tasks** — tasks needing several skills at once.
2. **Partial / shared task assignment** — let members split one task.
3. **Smarter scheduling** — true critical-path method with slack, plus
   look-ahead list scheduling instead of pure topological order.
4. **Pruning / heuristic search** — the engine still brute-forces all
   teams; add pruning to scale to larger pools.
5. **Calibration** — tune the formulas against real historical data.
6. **API + frontend** — wrap the engine in a service and build the
   manager-facing UI for interactive "what-if" comparisons.
```
