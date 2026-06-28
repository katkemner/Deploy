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
import workbank
import workbank_matching
from models import Team

from . import brief_extract
from . import brief_parser
from . import employee_seed
from .schemas import (
    AIAgent,
    Employee,
    CalibrationApplyRequest,
    CalibrationRejectRequest,
    HealthResponse,
    HistoricalProjectActualInput,
    ManualTeamRequest,
    MatchTasksRequest,
    ParseBriefRequest,
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
WORKBANK_IMPORT_DIR = os.path.join(DATA_DIR, "imports", "workbank")
WORKBANK_NORMALIZED = os.path.join(DATA_DIR, "priors", "workbank_normalized.json")
CALIBRATION_STORE = os.path.join(DATA_DIR, "calibration", "actuals.json")
CALIBRATION_CONFIG = os.path.join(DATA_DIR, "calibration", "applied_config.json")
CALIBRATION_STATE = os.path.join(DATA_DIR, "calibration", "proposal_state.json")

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

def _active_calibration(config) -> dict:
    """Resolve the approved calibration to apply for this request.

    Reads the applied calibration config and the config's tri-state
    ``use_calibration_multipliers`` flag. When no applied config exists (or the
    flag is false) this is disabled and ``engine_multipliers`` is ``None``, so
    the simulation behaves exactly as it did before calibration consumption.
    """
    return calibration.active_calibration(
        CALIBRATION_CONFIG, getattr(config, "use_calibration_multipliers", None)
    )


def _worker_to_employee(w) -> Employee:
    return Employee(
        name=w.name, role=w.role, skills=w.skills,
        capacity_hours=w.capacity_hours, workload_hours=w.workload_hours,
        available_hours=w.available_hours, cost_rate=w.cost_rate,
        quality_score=w.quality_score, speed_multiplier=w.speed_multiplier,
    )


# ---------------------------------------------------------------------------
# Active employee "digital twin seed" set — IN-MEMORY, ephemeral, never written
# to disk. Holds the uploaded seed roster (or an explicit demo choice) for the
# current runtime. Resets on restart; no permanent persistence (by design).
# ---------------------------------------------------------------------------
_ACTIVE_ROSTER: dict = {
    "source": "none",        # "none" | "demo" | "uploaded"
    "workers": None,         # list[Worker] when uploaded, else None (-> demo CSV)
    "filename": None,
    "report": None,
    "preview": None,
}


def _reset_active_roster() -> None:
    """Reset to the un-chosen state (used by tests; not an endpoint)."""
    _ACTIVE_ROSTER.update(
        source="none", workers=None, filename=None, report=None, preview=None
    )


def _active_employees() -> List:
    """The employees that drive simulation: the uploaded seed set if present,
    otherwise the built-in demo roster CSV. (Demo is the fallback so direct API
    use keeps working; the UI gates on an explicit choice.)"""
    if _ACTIVE_ROSTER["workers"] is not None:
        return list(_ACTIVE_ROSTER["workers"])
    return data_loader.load_employees(EMPLOYEES_CSV)


def _roster_status() -> dict:
    """Compact status for the UI badge + gating."""
    src = _ACTIVE_ROSTER["source"]
    if src == "uploaded":
        count = len(_ACTIVE_ROSTER["workers"] or [])
    elif src == "demo":
        count = len(data_loader.load_employees(EMPLOYEES_CSV))
    else:
        count = 0
    return {
        "source": src,
        "filename": _ACTIVE_ROSTER["filename"],
        "employee_count": count,
        "report": _ACTIVE_ROSTER["report"],
    }


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
    """Active employees: the uploaded digital-twin seed set, else the demo roster."""
    return [_worker_to_employee(w) for w in _active_employees()]


# ---------------------------------------------------------------------------
# Employee Digital Twin Seed upload + gated roster choice
# ---------------------------------------------------------------------------

@router.post("/employees/seed-upload", tags=["data"])
async def upload_employee_seed(file: UploadFile = File(...)) -> dict:
    """Upload an Employee Digital Twin **Seed** file (.csv or .xlsx).

    Seed profiles used for simulation - **not** full digital twins. The file is
    parsed and validated in memory and becomes the active roster for this
    session. Sensitive columns are dropped on ingest (never stored or returned).
    Nothing is written to disk; the active set resets on restart.
    """
    content = await file.read()
    try:
        workers, report, preview = employee_seed.parse_seed(content, file.filename or "")
    except employee_seed.SeedError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)

    _ACTIVE_ROSTER.update(
        source="uploaded", workers=workers, filename=file.filename,
        report=report, preview=preview,
    )
    return {
        "message": f"Employee digital twin seed active — {len(workers)} employees.",
        "status": _roster_status(),
        "employees": preview,
    }


@router.post("/employees/use-demo", tags=["data"])
def use_demo_roster() -> dict:
    """Explicitly choose the built-in demo roster (clears any uploaded seed)."""
    _reset_active_roster()
    _ACTIVE_ROSTER["source"] = "demo"
    demo = data_loader.load_employees(EMPLOYEES_CSV)
    return {
        "message": f"Demo roster active — {len(demo)} sample employees.",
        "status": _roster_status(),
        "employees": [_worker_to_employee(w).model_dump() for w in demo],
    }


@router.get("/employees/active", tags=["data"])
def active_roster() -> dict:
    """Current roster status for the UI badge + simulation gate."""
    return _roster_status()


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


@router.get("/priors/workbank", tags=["data"])
def get_workbank_priors() -> dict:
    """Return the read-only normalized WORKBank import status + data.

    Imports the three WORKBank CSVs from ``data/imports/workbank/`` when present
    (writing ``data/priors/workbank_normalized.json``), else falls back to a
    previously imported file, else reports ``not_imported``. The normalized
    WORKBank data is **NOT connected to routing, scoring, or any simulation** -
    it is exposed here read-only. Returns ``import_status``, ``task_count``,
    ``occupation_count``, ``normalized_priors``, and ``validation_warnings``.
    """
    return workbank.workbank_status(WORKBANK_IMPORT_DIR, WORKBANK_NORMALIZED)


@router.post("/priors/workbank/match-tasks", tags=["data"])
def match_workbank_tasks(request: MatchTasksRequest) -> dict:
    """Match each project task to its closest imported WORKBank task (PREVIEW).

    Returns one ``WorkbankTaskMatch`` per task (with up to three candidate
    matches). This is informational - the match is NOT used by routing,
    scoring, calibration, Pareto, Monte Carlo, or any recommendation. When no
    WORKBank data has been imported, each task reports a LOW, unmatched result.
    """
    normalized = workbank.workbank_status(WORKBANK_IMPORT_DIR, WORKBANK_NORMALIZED)
    task_dicts = [t.model_dump() for t in request.tasks]
    return {
        "import_status": normalized.get("import_status"),
        "matches": workbank_matching.match_tasks(task_dicts, normalized),
    }


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


@router.get("/calibration/proposals", tags=["calibration"])
def calibration_proposals() -> dict:
    """Update proposals derived from stored actuals (none applied automatically).

    Each proposal shows the current vs suggested multiplier value, the reason,
    error %, confidence, and whether it has been applied/rejected.
    """
    proposals = calibration.all_proposals(
        CALIBRATION_STORE, CALIBRATION_CONFIG, CALIBRATION_STATE
    )
    cfg = calibration.load_calibration_config(CALIBRATION_CONFIG)
    return {
        "proposals": proposals,
        "current_config": cfg["multipliers"],
        "note": "Proposals are suggestions; nothing is applied until you explicitly apply it.",
    }


@router.get("/calibration/active", tags=["calibration"])
def calibration_active() -> dict:
    """Report which approved calibration multipliers the engine is consuming.

    Reflects the current config's ``use_calibration_multipliers`` flag against
    the applied calibration config. Drives the Calibration panel's toggle,
    active-multipliers table, and provenance display. When no applied config
    exists (or the flag is off) this is disabled and simulations are unaffected.
    """
    config = config_loader.load_config(CONFIG_PATH)
    active = _active_calibration(config)
    cfg = calibration.load_calibration_config(CALIBRATION_CONFIG)
    return {
        "config_exists": active["config_exists"],
        "use_calibration_multipliers": config.use_calibration_multipliers,
        "multipliers": cfg["multipliers"],
        "descriptions": calibration.MULTIPLIER_DESCRIPTIONS,
        "warning": (
            "Approved calibration multipliers may change future simulation outputs."
        ),
        **active["response"],
    }


@router.post("/calibration/apply", tags=["calibration"])
def calibration_apply(request: CalibrationApplyRequest) -> dict:
    """Apply ONLY the selected proposals to the calibration config (traceable).

    Updates the six calibration multipliers, records provenance
    (updated_by=CALIBRATION_APPLY_FLOW), and marks the proposals applied.
    """
    return calibration.apply_proposals(
        request.proposal_ids, request.apply_notes,
        CALIBRATION_STORE, CALIBRATION_CONFIG, CALIBRATION_STATE,
    )


@router.post("/calibration/reject", tags=["calibration"])
def calibration_reject(request: CalibrationRejectRequest) -> dict:
    """Mark the selected proposals rejected (no config change)."""
    return calibration.reject_proposals(
        request.proposal_ids, CALIBRATION_STORE, CALIBRATION_STATE
    )


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

@router.post("/simulate", response_model=List[SimulationResult], tags=["simulate"])
def simulate() -> List[dict]:
    """Run the full engine on the current CSV data + config; top 5 teams."""
    config = config_loader.load_config(CONFIG_PATH)
    _, ai_agents, tasks = data_loader.load_all(DATA_DIR)
    employees = _active_employees()
    active = _active_calibration(config)
    results = optimizer.rank_teams(
        employees, ai_agents, tasks, config, top_n=5,
        calibration=active["engine_multipliers"],
    )

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
    _, ai_agents, tasks = data_loader.load_all(DATA_DIR)
    employees = _active_employees()

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
    active = _active_calibration(config)
    result = optimizer.simulate_single_team(
        team, tasks, config, calibration=active["engine_multipliers"]
    )
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
    employees = _active_employees()
    ai_agents = data_loader.load_ai_agents(AI_AGENTS_CSV)
    task_dicts = [t.model_dump() for t in request.tasks]
    bindings = (
        _prior_bindings(task_dicts)
        if config.use_public_priors_for_scoring else None
    )
    use_workbank = config.use_workbank_for_scoring
    wb_bindings, wb_present = (
        _workbank_bindings(task_dicts) if use_workbank else (None, False)
    )
    active = _active_calibration(config)
    try:
        response = project_mode.run_project_simulation(
            employees, ai_agents, request.model_dump(), config,
            prior_bindings=bindings, calibration=active["engine_multipliers"],
            workbank_bindings=wb_bindings, use_workbank=use_workbank,
        )
    except project_mode.ProjectModeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if use_workbank and not wb_present:
        response["workbank_warning"] = (
            "WORKBank scoring is enabled but no imported WORKBank data is "
            "available; scores fall back to public priors / heuristics.")

    # Additive, informational-only prior-match preview. This does NOT affect
    # any routing/scoring/recommendation produced above - it only annotates the
    # task_routing records with the closest matching prior.
    _attach_prior_match_preview(response, [t.model_dump() for t in request.tasks])
    # Additive, informational-only WORKBank match preview (read-only; never used
    # for routing/scoring/recommendations).
    _attach_workbank_match_preview(response, [t.model_dump() for t in request.tasks])
    # Surface which approved calibration multipliers shaped this run (if any).
    response.update(active["response"])
    return response


def _attach_workbank_match_preview(response: dict, task_dicts: list) -> None:
    """Add a read-only ``workbank_match_preview`` to each task_routing row.

    Best-effort and side-effect free with respect to the simulation: the match
    is informational and changes no routing/scoring/recommendation. When no
    WORKBank data is imported, each row's preview reports an unmatched, LOW
    result rather than failing.
    """
    normalized = workbank.workbank_status(WORKBANK_IMPORT_DIR, WORKBANK_NORMALIZED)
    matches = workbank_matching.match_tasks(task_dicts, normalized)
    by_task = {m["project_task_id"]: m for m in matches}
    for row in response.get("task_routing", []):
        m = by_task.get(row.get("task"))
        if m is None:
            continue
        row["workbank_match_preview"] = {
            "matched_workbank_task_id": m["matched_workbank_task_id"],
            "matched_task_text": m["matched_task_text"],
            "matched_occupation_title": m["matched_occupation_title"],
            "matched_task_type": m["matched_task_type"],
            "match_score": m["match_score"],
            "match_confidence": m["match_confidence"],
            "explanation": m["explanation"],
        }


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
    employees = _active_employees()
    ai_agents = data_loader.load_ai_agents(AI_AGENTS_CSV)
    active = _active_calibration(config)
    try:
        response = montecarlo.run_uncertainty(
            employees, ai_agents, request.model_dump(), config,
            calibration=active["engine_multipliers"],
        )
    except project_mode.ProjectModeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    response.update(active["response"])
    return response


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
    use_workbank = config.use_workbank_for_scoring
    task_dicts = [t.model_dump() for t in request.tasks]
    bindings = _prior_bindings(task_dicts) if use_priors else None
    wb_bindings, wb_present = _workbank_bindings(task_dicts) if use_workbank else (None, False)
    active = _active_calibration(config)
    records = routing.route_tasks(
        task_dicts, bindings=bindings, use_priors=use_priors,
        calibration=active["engine_multipliers"],
        workbank_bindings=wb_bindings, use_workbank=use_workbank,
    )
    out = {
        "public_priors_enabled": use_priors,
        "workbank_scoring_enabled": use_workbank,
        "task_routing": records,
        "routing_summary": routing.summarize_routing(records),
        **active["response"],
    }
    if use_workbank and not wb_present:
        out["workbank_warning"] = (
            "WORKBank scoring is enabled but no imported WORKBank data is "
            "available; scores fall back to public priors / heuristics.")
    return out


def _prior_bindings(task_dicts: list):
    """Build prior-score bindings for tasks, or None if priors can't load."""
    try:
        bundle = priors.load_priors(PRIORS_PATH)
    except priors.PriorsError:
        return None
    return prior_matching.build_score_bindings(task_dicts, bundle)


def _workbank_bindings(task_dicts: list):
    """Build WORKBank score bindings for tasks. Returns (bindings, data_present).

    ``data_present`` is True only when imported WORKBank data actually exists,
    so callers can warn when the toggle is on but nothing was imported.
    """
    normalized = workbank.workbank_status(WORKBANK_IMPORT_DIR, WORKBANK_NORMALIZED)
    present = bool(normalized.get("normalized_priors"))
    return workbank_matching.build_score_bindings(task_dicts, normalized), present


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
# Brief upload -> AI-drafted tasks (input-assist only; engine untouched)
# ---------------------------------------------------------------------------

def _available_skills() -> List[str]:
    """Union of human skills + AI-agent capabilities, for skill reconciliation.

    Injected into the drafting prompt so the LLM picks ``required_skill`` from
    the team's real vocabulary, and used afterwards to flag anything outside it.
    """
    skills: set[str] = set()
    for w in data_loader.load_employees(EMPLOYEES_CSV):
        skills.update(w.skills)
    for w in data_loader.load_ai_agents(AI_AGENTS_CSV):
        skills.update(w.skills)
    return sorted(s for s in skills if s)


@router.post("/projects/extract-brief-text", tags=["brief"])
async def extract_brief_text(file: UploadFile = File(...)) -> dict:
    """Deterministically extract plain text from an uploaded brief (NO LLM).

    Accepts a ``.docx`` or text-based ``.pdf`` and returns the extracted text
    for the user to preview. Nothing is persisted and no AI is involved; the
    text is only sent for AI drafting later, via ``/projects/parse-brief``,
    after the user explicitly confirms.
    """
    content = await file.read()
    try:
        result = brief_extract.extract_brief_text(content, file.filename or "")
    except brief_extract.BriefExtractionError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)
    return {
        "filename": result.filename,
        "file_type": result.file_type,
        "char_count": result.char_count,
        "truncated": result.truncated,
        "text": result.text,
    }


@router.post("/projects/parse-brief", tags=["brief"])
def parse_brief(request: ParseBriefRequest) -> dict:
    """Draft EDITABLE tasks from confirmed brief text using Claude.

    The LLM only proposes draft tasks for the user to review and edit; it does
    not score, route, schedule, optimise, or recommend staffing, and the
    deterministic engine is never touched. ``required_skill`` is constrained to
    the team's real skill vocabulary; anything outside it is flagged
    ``needs_user_review``. Returns 503 if AI drafting isn't configured on this
    server (no ``ANTHROPIC_API_KEY``), so the rest of the app keeps working.
    """
    try:
        result = brief_parser.parse_brief(request.text, _available_skills())
    except brief_parser.BriefParserUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except brief_parser.BriefParserError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)
    return result.model_dump()


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
