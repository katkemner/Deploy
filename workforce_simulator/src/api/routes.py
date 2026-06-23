"""API routes. Every endpoint delegates to the existing engine modules -
no simulation logic is reimplemented here.
"""

from __future__ import annotations

import io
import json
import os
from typing import Callable, List

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File

# Engine modules (importable thanks to the path setup in ``api/__init__``).
import calibration
import config_loader
import data_loader
import exporter
import montecarlo
import optimizer
import prior_matching
import priors
import project_mode
import routing
from models import Team

from .schemas import (
    AIAgent,
    Employee,
    HealthResponse,
    HistoricalProjectActualInput,
    ManualTeamRequest,
    MatchTasksRequest,
    ProjectScenarioRequest,
    ProjectTask,
    RouteTasksRequest,
    ScoringConfig,
    SimulationResult,
    UncertaintyRequest,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Paths (resolved relative to the project root = parent of ``src``)
# ---------------------------------------------------------------------------
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(_SRC_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "scoring_weights.json")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
RESULTS_JSON = os.path.join(OUTPUT_DIR, "results.json")

EMPLOYEES_CSV = os.path.join(DATA_DIR, "employees.csv")
AI_AGENTS_CSV = os.path.join(DATA_DIR, "ai_agents.csv")
TASKS_CSV = os.path.join(DATA_DIR, "project_tasks.csv")
PRIORS_PATH = os.path.join(DATA_DIR, "priors", "public_priors_seed.json")
CALIBRATION_STORE = os.path.join(DATA_DIR, "calibration", "actuals.json")

# Required columns for upload validation.
EMPLOYEE_COLUMNS = [
    "name", "role", "skills", "capacity_hours",
    "workload_hours", "cost_rate", "quality_score",
]
AI_AGENT_COLUMNS = [
    "name", "agent_type", "capabilities", "capacity_hours",
    "cost_rate", "quality_score", "speed_multiplier",
]
TASK_COLUMNS = ["task", "required_skill", "effort_hours", "priority"]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _worker_to_employee(w) -> Employee:
    return Employee(
        name=w.name, role=w.role, skills=w.skills,
        capacity_hours=w.capacity_hours, workload_hours=w.workload_hours,
        available_hours=w.available_hours, cost_rate=w.cost_rate,
        quality_score=w.quality_score, speed_multiplier=w.speed_multiplier,
    )


def _worker_to_ai_agent(w) -> AIAgent:
    return AIAgent(
        name=w.name, agent_type=w.role, capabilities=w.skills,
        capacity_hours=w.capacity_hours, workload_hours=w.workload_hours,
        available_hours=w.available_hours, cost_rate=w.cost_rate,
        quality_score=w.quality_score, speed_multiplier=w.speed_multiplier,
    )


def _validate_and_save_upload(
    content: bytes, required_columns: List[str],
    loader: Callable[[str], list], dest_path: str,
) -> int:
    """Validate an uploaded CSV and atomically replace ``dest_path``.

    Raises ``HTTPException(400)`` with a helpful message on any problem and
    leaves the existing file untouched. Returns the row count on success.
    """
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:  # malformed CSV
        raise HTTPException(
            status_code=400, detail=f"Could not parse CSV: {exc}"
        )
    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                f"CSV is missing required column(s): {missing}. "
                f"Expected columns: {required_columns}"
            ),
        )

    # Write to a temp file and confirm the engine loader accepts it before
    # overwriting the real data file.
    tmp_path = dest_path + ".tmp"
    with open(tmp_path, "wb") as fh:
        fh.write(content)
    try:
        objects = loader(tmp_path)
    except Exception as exc:
        os.remove(tmp_path)
        raise HTTPException(
            status_code=400, detail=f"CSV failed validation: {exc}"
        )
    if not objects:
        os.remove(tmp_path)
        raise HTTPException(status_code=400, detail="CSV contains no data rows.")

    os.replace(tmp_path, dest_path)
    return len(objects)


# ---------------------------------------------------------------------------
# Health & config
# ---------------------------------------------------------------------------

@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/config", response_model=ScoringConfig, tags=["config"])
def get_config() -> ScoringConfig:
    try:
        return ScoringConfig(**config_loader.read_raw_config(CONFIG_PATH))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Config file not found.")


@router.post("/config", response_model=ScoringConfig, tags=["config"])
def update_config(config: ScoringConfig) -> ScoringConfig:
    # ``config`` is already validated by the schema (non-negative weights,
    # sensible team constraints). Persist it and echo it back.
    config_loader.write_raw_config(CONFIG_PATH, config.model_dump())
    return config


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@router.get("/employees", response_model=List[Employee], tags=["data"])
def get_employees() -> List[Employee]:
    return [_worker_to_employee(w) for w in data_loader.load_employees(EMPLOYEES_CSV)]


@router.get("/ai-agents", response_model=List[AIAgent], tags=["data"])
def get_ai_agents() -> List[AIAgent]:
    return [_worker_to_ai_agent(w) for w in data_loader.load_ai_agents(AI_AGENTS_CSV)]


@router.get("/tasks", response_model=List[ProjectTask], tags=["data"])
def get_tasks() -> List[ProjectTask]:
    return [
        ProjectTask(
            task=t.task, required_skill=t.required_skill,
            effort_hours=t.effort_hours, priority=t.priority,
            dependencies=t.dependencies, is_required=t.is_required,
        )
        for t in data_loader.load_tasks(TASKS_CSV)
    ]


@router.get("/priors", tags=["data"])
def get_priors() -> dict:
    """Return the loaded public evidence priors (foundation only).

    These are representative seed values and are **not yet connected** to
    routing or scoring. Returns ``source_weights``, ``evidence_priors``,
    ``task_routing_priors``, and ``hybrid_guardrail_priors``.
    """
    try:
        bundle = priors.load_priors(PRIORS_PATH)
    except priors.PriorsError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return bundle.to_dict()


@router.post("/priors/match-tasks", tags=["data"])
def match_tasks(request: MatchTasksRequest) -> dict:
    """Match each project task to its closest public prior (PREVIEW ONLY).

    Returns one ``PriorMatch`` per task (with up to three candidate matches).
    This is informational - the match is NOT used by routing, scoring, or any
    simulation.
    """
    try:
        bundle = priors.load_priors(PRIORS_PATH)
    except priors.PriorsError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    task_dicts = [t.model_dump() for t in request.tasks]
    return {"matches": prior_matching.match_tasks(task_dicts, bundle)}


# ---------------------------------------------------------------------------
# Calibration (historical actuals vs predictions) - informational only
# ---------------------------------------------------------------------------

@router.post("/calibration/actuals", tags=["calibration"])
def submit_actuals(request: HistoricalProjectActualInput) -> dict:
    """Record a completed project's actual outcomes and compare to predictions.

    Stores the actuals locally and returns the comparison. Suggested multiplier
    updates are informational and are NOT applied to scoring or simulation.
    """
    data = request.model_dump()
    try:
        calibration.validate_actual(data)
    except calibration.CalibrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    calibration.save_actual(CALIBRATION_STORE, data)
    return {"stored": True, "comparison": calibration.compare(data).to_dict()}


@router.post("/calibration/compare", tags=["calibration"])
def compare_actuals(request: HistoricalProjectActualInput) -> dict:
    """Compare actuals to predictions WITHOUT storing. Informational only."""
    data = request.model_dump()
    try:
        calibration.validate_actual(data)
    except calibration.CalibrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return calibration.compare(data).to_dict()


@router.get("/calibration/summary", tags=["calibration"])
def calibration_summary() -> dict:
    """Aggregate error summary + biggest misses across all stored actuals."""
    return calibration.summarize(CALIBRATION_STORE)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

@router.post("/simulate", response_model=List[SimulationResult], tags=["simulate"])
def simulate() -> List[dict]:
    """Run the full engine on the current CSV data + config; top 5 teams."""
    config = config_loader.load_config(CONFIG_PATH)
    employees, ai_agents, tasks = data_loader.load_all(DATA_DIR)
    results = optimizer.rank_teams(employees, ai_agents, tasks, config, top_n=5)

    # Persist outputs so ``GET /outputs/latest`` reflects this run.
    exporter.export_json(results, RESULTS_JSON)
    exporter.export_csv(results, os.path.join(OUTPUT_DIR, "results.csv"))
    return [exporter.result_to_dict(r) for r in results]


@router.post(
    "/simulate/manual-team",
    response_model=SimulationResult,
    tags=["simulate"],
)
def simulate_manual_team(request: ManualTeamRequest) -> dict:
    """Simulate one explicitly chosen team of humans and/or AI agents."""
    config = config_loader.load_config(CONFIG_PATH)
    employees, ai_agents, tasks = data_loader.load_all(DATA_DIR)

    humans_by_name = {w.name: w for w in employees}
    ais_by_name = {w.name: w for w in ai_agents}

    unknown_humans = [n for n in request.human_names if n not in humans_by_name]
    unknown_ais = [n for n in request.ai_agent_names if n not in ais_by_name]
    if unknown_humans or unknown_ais:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Team contains unknown member name(s).",
                "unknown_humans": unknown_humans,
                "unknown_ai_agents": unknown_ais,
                "valid_humans": sorted(humans_by_name),
                "valid_ai_agents": sorted(ais_by_name),
            },
        )

    team = Team(
        humans=[humans_by_name[n] for n in request.human_names],
        ai_agents=[ais_by_name[n] for n in request.ai_agent_names],
    )
    result = optimizer.simulate_single_team(team, tasks, config)
    return exporter.result_to_dict(result)


@router.post("/simulate/project", tags=["simulate"])
def simulate_project(request: ProjectScenarioRequest) -> dict:
    """Project Mode: compare staffing options for a project scenario.

    Uses the current employees/AI agents from CSV and the tasks supplied in
    the request body (project_tasks.csv is NOT read or overwritten). Returns
    the five decision options, a comparison table, and a deterministic
    recommendation summary.
    """
    config = config_loader.load_config(CONFIG_PATH)
    # Current employees + AI agents come from CSV; tasks come from the request.
    employees = data_loader.load_employees(EMPLOYEES_CSV)
    ai_agents = data_loader.load_ai_agents(AI_AGENTS_CSV)
    task_dicts = [t.model_dump() for t in request.tasks]
    bindings = (
        _prior_bindings(task_dicts)
        if config.use_public_priors_for_scoring else None
    )
    try:
        response = project_mode.run_project_simulation(
            employees, ai_agents, request.model_dump(), config,
            prior_bindings=bindings,
        )
    except project_mode.ProjectModeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Additive, informational-only prior-match preview. This does NOT affect
    # any routing/scoring/recommendation produced above - it only annotates the
    # task_routing records with the closest matching prior.
    _attach_prior_match_preview(response, [t.model_dump() for t in request.tasks])
    return response


def _attach_prior_match_preview(response: dict, task_dicts: list) -> None:
    """Add prior_match_preview/confidence/explanation to each task_routing row.

    Best-effort and side-effect free with respect to the simulation: if priors
    cannot be loaded the response is returned unchanged.
    """
    try:
        bundle = priors.load_priors(PRIORS_PATH)
    except priors.PriorsError:
        return
    matches = prior_matching.match_tasks(task_dicts, bundle)
    by_task = {m["project_task_id"]: m for m in matches}
    for row in response.get("task_routing", []):
        m = by_task.get(row.get("task"))
        if m:
            row["prior_match_preview"] = m["matched_prior_id"]
            row["prior_match_confidence"] = m["match_confidence"]
            row["prior_match_explanation"] = m["explanation"]


@router.post("/simulate/uncertainty", tags=["simulate"])
def simulate_uncertainty(request: UncertaintyRequest) -> dict:
    """Monte-Carlo uncertainty analysis for a team and a set of tasks.

    Samples each task's effort from a triangular (optimistic/likely/
    pessimistic) range and runs the real scheduler ``iterations`` times,
    returning P10/P50/P90 duration and cost plus the empirical probability of
    meeting the deadline/budget. Reproducible for a fixed ``seed``.
    """
    config = config_loader.load_config(CONFIG_PATH)
    employees = data_loader.load_employees(EMPLOYEES_CSV)
    ai_agents = data_loader.load_ai_agents(AI_AGENTS_CSV)
    try:
        return montecarlo.run_uncertainty(
            employees, ai_agents, request.model_dump(), config
        )
    except project_mode.ProjectModeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/route/tasks", tags=["routing"])
def route_tasks(request: RouteTasksRequest) -> dict:
    """Task-level human/AI routing for a set of tasks (no team required).

    Returns the routing decision, 1-5 suitability scores, explanation, and
    review/rework/AI-time estimates per task, plus project-level totals. When
    ``use_public_priors_for_scoring`` is enabled in the config, matched public
    priors may supply/blend the suitability scores (with full provenance).
    """
    config = config_loader.load_config(CONFIG_PATH)
    use_priors = config.use_public_priors_for_scoring
    task_dicts = [t.model_dump() for t in request.tasks]
    bindings = _prior_bindings(task_dicts) if use_priors else None
    records = routing.route_tasks(task_dicts, bindings=bindings, use_priors=use_priors)
    return {
        "public_priors_enabled": use_priors,
        "task_routing": records,
        "routing_summary": routing.summarize_routing(records),
    }


def _prior_bindings(task_dicts: list):
    """Build prior-score bindings for tasks, or None if priors can't load."""
    try:
        bundle = priors.load_priors(PRIORS_PATH)
    except priors.PriorsError:
        return None
    return prior_matching.build_score_bindings(task_dicts, bundle)


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

@router.post("/upload/employees", tags=["upload"])
async def upload_employees(file: UploadFile = File(...)) -> dict:
    rows = _validate_and_save_upload(
        await file.read(), EMPLOYEE_COLUMNS,
        data_loader.load_employees, EMPLOYEES_CSV,
    )
    return {"message": "employees.csv updated", "rows": rows}


@router.post("/upload/ai-agents", tags=["upload"])
async def upload_ai_agents(file: UploadFile = File(...)) -> dict:
    rows = _validate_and_save_upload(
        await file.read(), AI_AGENT_COLUMNS,
        data_loader.load_ai_agents, AI_AGENTS_CSV,
    )
    return {"message": "ai_agents.csv updated", "rows": rows}


@router.post("/upload/tasks", tags=["upload"])
async def upload_tasks(file: UploadFile = File(...)) -> dict:
    rows = _validate_and_save_upload(
        await file.read(), TASK_COLUMNS,
        data_loader.load_tasks, TASKS_CSV,
    )
    return {"message": "project_tasks.csv updated", "rows": rows}


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

@router.get("/outputs/latest", tags=["outputs"])
def latest_outputs() -> list:
    """Return the most recent ``results.json``, or 404 if none exists yet."""
    if not os.path.exists(RESULTS_JSON):
        raise HTTPException(
            status_code=404,
            detail="No results yet. Run POST /simulate first.",
        )
    with open(RESULTS_JSON, "r", encoding="utf-8") as fh:
        return json.load(fh)
