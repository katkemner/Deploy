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

#### Endpoints

| Method & path | What it does |
|---|---|
| `GET /health` | Liveness check, returns `{"status": "ok"}` |
| `GET /config` | Current scoring weights + team constraints |
| `POST /config` | Validate and save new weights/constraints |
| `GET /employees` | Employees loaded from `data/employees.csv` |
| `GET /ai-agents` | AI agents loaded from `data/ai_agents.csv` |
| `GET /tasks` | Project tasks loaded from `data/project_tasks.csv` |
| `POST /simulate` | Run the full engine; returns the top 5 ranked teams (and writes `outputs/`) |
| `POST /simulate/manual-team` | Simulate one chosen team (`human_names` + `ai_agent_names`); full result |
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
