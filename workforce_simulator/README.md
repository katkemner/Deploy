# Workforce Simulator (MVP)

A command-line simulation engine that helps a manager compare different
combinations of **people + AI agents** for a project and predict outcomes
such as duration, cost, skill coverage, workload balance, productivity,
and risk.

This is an MVP focused on proving the **core simulation logic**. There is
no frontend, no database, and no API keys. All scoring is done with
**deterministic formulas** — no LLM is used to invent numbers, so the same
inputs always produce the same ranked output.

---

## What it does

Given a pool of employees, a pool of AI agents, and a list of project
tasks, the simulator:

1. Generates every valid team combination (**2–5 humans, 0–2 AI agents**).
2. Assigns each task to the best available team member.
3. Scores each team across several metrics.
4. Ranks the teams with a weighted total score.
5. Prints the **top 5 teams** and saves full results to JSON and CSV, each
   with a plain-English explanation of *why* it ranked where it did.

---

## Project structure

```
workforce_simulator/
├── README.md
├── requirements.txt
├── data/
│   ├── employees.csv        # the human talent pool
│   ├── ai_agents.csv        # the available AI agents
│   └── project_tasks.csv    # the work to be done
├── src/
│   ├── main.py              # CLI entry point (run this)
│   ├── data_loader.py       # reads CSVs into model objects
│   ├── models.py            # Worker / Task / Team / Assignment models
│   ├── simulator.py         # task assignment + per-team metrics
│   ├── scoring.py           # deterministic scoring formulas
│   ├── optimizer.py         # team generation, ranking, explanations
│   └── exporter.py          # writes results.json / results.csv
├── outputs/
│   ├── results.json         # full results (generated)
│   └── results.csv          # flat summary (generated)
└── tests/
    └── test_simulator.py    # unit tests
```

---

## Install

Requires **Python 3.8+**. The only third-party dependency is `pandas`
(used for CSV reading/writing).

```bash
cd workforce_simulator
pip install -r requirements.txt
```

## Run

```bash
python src/main.py
```

This prints the top 5 teams to the terminal and writes
`outputs/results.json` and `outputs/results.csv`.

## Test

```bash
# with pytest
python -m pytest tests/

# or without pytest installed
python tests/test_simulator.py
```

---

## The data files

### `employees.csv` — the human talent pool
| field | meaning |
|---|---|
| `name` | employee name |
| `role` | job title (informational) |
| `skills` | `\|`-separated skills, e.g. `Python\|API\|Database` |
| `capacity_hours` | total hours available for this project window |
| `workload_hours` | hours already committed to other work |
| `cost_rate` | cost per hour |
| `quality_score` | quality rating, 0–10 |

A human's **available hours** = `capacity_hours − workload_hours`, and
their `speed_multiplier` is always `1.0`.

### `ai_agents.csv` — the AI agents
| field | meaning |
|---|---|
| `name` | agent name |
| `agent_type` | agent category (informational) |
| `capabilities` | `\|`-separated skills the agent can do |
| `capacity_hours` | hours the agent can work |
| `cost_rate` | cost per hour |
| `quality_score` | quality rating, 0–10 |
| `speed_multiplier` | how much faster than a human (e.g. `1.3` = 30% faster) |

AI agents have **no pre-existing workload**, so their available hours equal
their capacity. Because they work faster, a task needing `E` effort hours
consumes only `E / speed_multiplier` of an agent's time.

### `project_tasks.csv` — the work
| field | meaning |
|---|---|
| `task` | task name |
| `required_skill` | the single skill needed to do it |
| `effort_hours` | nominal effort (at human speed) |
| `priority` | `1` = highest priority, assigned first |

To simulate a different scenario, just edit these CSVs and re-run — no code
changes needed.

---

## How tasks are assigned

Tasks are processed **highest priority first**. For each task the simulator
finds every team member whose skills include the required skill, then picks
the best one using a weighted candidate score:

- **40% quality** — prefer higher-quality workers
- **20% cost efficiency** — prefer cheaper workers
- **20% speed** — prefer faster workers (rewards AI agents)
- **20% remaining capacity** — prefer workers who still have free time

That last factor is what spreads work across the team instead of dumping
everything on the single "best" person. If **no** team member has the
required skill, the task is recorded as a **missing-skill risk** and left
unassigned.

---

## How the scores are calculated

All scores are on a **0–100 scale where higher is better**, except
`risk_score` where higher means *more risk*. The exact formulas live in
[`src/scoring.py`](src/scoring.py) and are intentionally simple and
readable.

| score | meaning | how it's computed |
|---|---|---|
| **skill_coverage_score** | % of tasks the team can actually staff | `covered_tasks / total_tasks × 100` |
| **capacity_fit_score** | are people within their available hours? | `100 × (1 − overflow_hours / assigned_hours)` where overflow is work beyond each member's capacity |
| **estimated_cost** | total project cost | Σ `assigned_hours × member.cost_rate` |
| **estimated_duration** | calendar time, assuming parallel work | the busiest member's assigned hours (the critical path) |
| **workload_balance_score** | how evenly work is spread | based on the spread (std dev) of member utilisation; even = high |
| **productivity_score** | overall throughput quality | `0.40×coverage + 0.20×quality + 0.20×speed + 0.20×capacity_fit` |
| **risk_score** | total risk (higher = worse) | `40×missing_skills + 25×overload + 20×imbalance + 15×low_coverage` |
| **confidence_score** | how much to trust the result | starts from coverage, −15 per missing skill |
| **cost_efficiency_score** | cheapest team = 100, dearest = 0 | min-max normalised cost across all teams |

### Final ranking (`total_score`)

Teams are ranked by a weighted blend (the weights sum to 100%):

| weight | component |
|---|---|
| 30% | skill coverage |
| 20% | capacity fit |
| 20% | productivity |
| 15% | workload balance |
| 10% | cost efficiency |
| 5%  | low risk (`100 − risk_score`) |

The top 5 teams by `total_score` are returned. Ties are broken
deterministically (lower risk, then lower cost) so output is reproducible.

---

## How to read the output

Terminal output (and `results.json`) gives, for each of the top 5 teams:

- the **humans** and **AI agents** on the team
- every metric above
- **missing_skills** — skills no member could cover (the biggest risk)
- **overloaded_members** — people assigned more than their available hours
- **task_assignments** — who got each task and for how many hours
- a **plain_english_explanation**, e.g.:

  > *"Team 1 ranked #1 with a total score of 78.52. It covers 80 percent of
  > the required skills and mostly fits within available capacity, using
  > AI QA Reviewer, AI Research Agent to speed up part of the work. The main
  > risk is missing coverage for: API, React."*

`results.csv` is the same information flattened for spreadsheets, with task
assignments collapsed into one column.

> **Tip:** With the sample data, the highest-ranked teams trade a little
> skill coverage (they omit the only React engineer) for much better cost,
> balance, and capacity fit. That is the weighting working as designed —
> adjust the weights in `scoring.py` if your priorities differ.

---

## What to build next

This MVP proves the simulation core. Sensible next steps:

1. **Multi-skill tasks & dependencies** — tasks needing several skills, or
   that must finish before others start (real critical-path scheduling).
2. **Partial / shared task assignment** — let two members split one task
   instead of one owner per task.
3. **Configurable weights & constraints** — pass the ranking weights, team
   size limits, and budget caps as CLI flags or a config file.
4. **Smarter optimisation** — the current engine brute-forces all teams;
   add pruning or a heuristic search to scale to larger pools.
5. **Calibration** — tune the formulas against real historical project
   data so the scores predict real outcomes.
6. **API + frontend** — wrap the engine in a small service and build the
   manager-facing UI for interactive "what-if" comparisons.
```
