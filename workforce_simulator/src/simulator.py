"""Run a single team through the project and compute its raw metrics.

The simulator does three things for one team:

1. **Assign tasks** to the best available member (``assign_tasks``).
2. **Schedule** the assigned tasks respecting dependencies and each
   worker's single-threaded availability (via ``scheduler``).
3. **Compute metrics** from the assignment + schedule (``simulate_team``).

The only score it cannot finish here is ``cost_efficiency_score`` and the
final ``total_score``: those need to compare against *all* teams, so they
are added later by the optimizer. Everything in this module is
deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import scoring
import scheduler
from models import Assignment, Task, Team


# ---------------------------------------------------------------------------
# Candidate selection
# ---------------------------------------------------------------------------

def _candidate_score(worker, task: Task, remaining_hours: float) -> float:
    """Score how good ``worker`` is for ``task`` right now.

    Combines four factors the brief asks for (all workers here already
    match the skill):

    * quality     - higher quality workers preferred (40%)
    * cost        - cheaper workers preferred (20%)
    * speed       - faster workers preferred (20%)
    * capacity    - workers with spare capacity preferred (20%)

    The capacity factor is what makes assignment spread work across the
    team instead of piling everything on the single "best" person.
    """
    quality = worker.quality_score / 10.0                 # 0..1
    cost_efficiency = min(1.0, 70.0 / worker.cost_rate)   # 0..1
    speed = min(1.0, worker.speed_multiplier / 1.5)       # 0..1
    needed = worker.effective_hours_for(task.effort_hours)
    if needed <= 0:
        capacity = 1.0
    else:
        capacity = max(0.0, min(1.0, remaining_hours / needed))
    return 0.40 * quality + 0.20 * cost_efficiency + 0.20 * speed + 0.20 * capacity


def assign_tasks(team: Team, tasks: List[Task], allowed_types=None) -> List[Assignment]:
    """Assign every task to the best available team member.

    Tasks are processed in priority order (priority 1 first). For each task
    we find members whose skills match, then pick the one with the highest
    candidate score given how much capacity they have left. A task with no
    skilled member is recorded as a missing-skill risk.

    ``allowed_types`` (optional) maps a task name to the set of worker types
    (``HUMAN`` / ``AI_AGENT``) permitted to own that task. It lets a staffing
    strategy pin which kind of worker does each task (e.g. AI-First vs
    Human-Core). When ``None`` (the default) assignment is unconstrained and
    behaves exactly as before. A task whose allowed candidates are empty after
    the filter is recorded as a missing-skill/gap, just like an unskilled task.

    The worker objects are not mutated; remaining capacity is tracked in a
    local dict so the same ``Team`` can be reused across simulations.
    """
    members = team.members
    remaining: Dict[str, float] = {w.name: w.available_hours for w in members}
    ordered = sorted(tasks, key=lambda t: (t.priority, t.task))

    assignments: List[Assignment] = []
    for task in ordered:
        candidates = [w for w in members if w.has_skill(task.required_skill)]
        if allowed_types is not None and task.task in allowed_types:
            allowed = allowed_types[task.task]
            candidates = [w for w in candidates if w.type in allowed]
        if not candidates:
            assignments.append(
                Assignment(
                    task=task.task,
                    required_skill=task.required_skill,
                    effort_hours=task.effort_hours,
                    priority=task.priority,
                    is_required=task.is_required,
                    dependencies=list(task.dependencies),
                    missing_skill=True,
                )
            )
            continue

        best = max(
            candidates,
            key=lambda w: (_candidate_score(w, task, remaining[w.name]), w.name),
        )
        hours = best.effective_hours_for(task.effort_hours)
        remaining[best.name] -= hours
        assignments.append(
            Assignment(
                task=task.task,
                required_skill=task.required_skill,
                effort_hours=task.effort_hours,
                priority=task.priority,
                is_required=task.is_required,
                dependencies=list(task.dependencies),
                assigned_to=best.name,
                assigned_type=best.type,
                assigned_hours=hours,
            )
        )

    # Restore the original task order for readability.
    by_name = {a.task: a for a in assignments}
    return [by_name[t.task] for t in tasks]


# ---------------------------------------------------------------------------
# Simulation result
# ---------------------------------------------------------------------------

@dataclass
class SimulationResult:
    """All raw metrics for one team (pre-ranking).

    ``cost_efficiency_score``, ``total_score`` and ``rank`` are filled in
    later by the optimizer once every team has been simulated.
    """

    team: Team
    assignments: List[Assignment]
    is_valid_team: bool
    invalid_reasons: List[str]
    skill_coverage_score: float
    required_skill_coverage_score: float
    optional_skill_coverage_score: float
    capacity_fit_score: float
    estimated_cost: float
    estimated_duration: float
    critical_path: List[str]
    workload_balance_score: float
    productivity_score: float
    risk_score: float
    confidence_score: float
    missing_required_skills: List[str]
    missing_optional_skills: List[str]
    overloaded_members: List[str]
    missing_required_fraction: float
    member_hours: Dict[str, float] = field(default_factory=dict)
    # Filled in during ranking:
    cost_efficiency_score: float = 0.0
    total_score: float = 0.0
    rank: int = 0
    plain_english_explanation: str = ""


def simulate_team(
    team: Team,
    tasks: List[Task],
    require_full_required_skill_coverage: bool = True,
    calibration: Dict[str, float] = None,
    allowed_types=None,
) -> SimulationResult:
    """Assign + schedule ``team`` and compute every per-team metric.

    ``calibration`` (optional) is a dict of approved calibration multipliers.
    When supplied it scales the schedule (via the scheduler) and adds the
    skill-gap / context-switching penalties to the risk score. When ``None``
    (the default) every metric is computed exactly as before.

    ``allowed_types`` (optional) pins which worker type may own each task (see
    :func:`assign_tasks`); ``None`` leaves assignment unconstrained. Scoring and
    scheduling are unchanged - only which member ends up on each task differs.
    """
    members = team.members
    assignments = assign_tasks(team, tasks, allowed_types)

    # --- coverage (overall / required / optional) --------------------------
    required_tasks = [t for t in tasks if t.is_required]
    optional_tasks = [t for t in tasks if not t.is_required]
    by_task = {a.task: a for a in assignments}

    covered = sum(1 for a in assignments if not a.missing_skill)
    req_covered = sum(
        1 for t in required_tasks if not by_task[t.task].missing_skill
    )
    opt_covered = sum(
        1 for t in optional_tasks if not by_task[t.task].missing_skill
    )

    missing_required_skills = sorted(
        {t.required_skill for t in required_tasks if by_task[t.task].missing_skill}
    )
    missing_optional_skills = sorted(
        {t.required_skill for t in optional_tasks if by_task[t.task].missing_skill}
    )

    coverage = scoring.skill_coverage_score(covered, len(tasks))
    required_coverage = scoring.skill_coverage_score(req_covered, len(required_tasks))
    optional_coverage = scoring.skill_coverage_score(opt_covered, len(optional_tasks))
    missing_required_fraction = (
        (len(required_tasks) - req_covered) / len(required_tasks)
        if required_tasks else 0.0
    )

    # --- schedule (duration + critical path) -------------------------------
    sched = scheduler.schedule(assignments, calibration)
    estimated_duration = sched["duration"]
    critical_path = sched["critical_path"]

    # --- workload / capacity -----------------------------------------------
    member_hours: Dict[str, float] = {w.name: 0.0 for w in members}
    for a in assignments:
        if a.assigned_to is not None:
            member_hours[a.assigned_to] += a.assigned_hours

    total_assigned = sum(member_hours.values())
    overloaded_members = sorted(
        w.name for w in members
        if member_hours[w.name] > w.available_hours + 1e-9
    )
    total_overflow = sum(
        max(0.0, member_hours[w.name] - w.available_hours) for w in members
    )
    utilizations = [
        (member_hours[w.name] / w.available_hours) if w.available_hours > 0 else 0.0
        for w in members
    ]

    # --- scores ------------------------------------------------------------
    capacity_fit = scoring.capacity_fit_score(total_assigned, total_overflow)
    balance = scoring.workload_balance_score(utilizations)
    avg_quality_0_100 = (
        sum(w.quality_score for w in members) / len(members) * 10.0
        if members else 0.0
    )
    avg_speed = (
        sum(w.speed_multiplier for w in members) / len(members) if members else 1.0
    )
    productivity = scoring.productivity_score(
        coverage, avg_quality_0_100, avg_speed, capacity_fit
    )

    missing_fraction = (len(tasks) - covered) / len(tasks) if tasks else 0.0
    overload_fraction = len(overloaded_members) / len(members) if members else 0.0
    risk = scoring.risk_score(missing_fraction, overload_fraction, balance, coverage)
    # Approved calibration penalties raise risk for the patterns the user's
    # historical actuals showed we under-modelled: uncovered required skills and
    # member overload (a context-switching proxy). Neutral defaults (0.0) and a
    # missing config leave risk untouched.
    if calibration:
        risk += (
            calibration.get("skill_gap_penalty", 0.0) * 100.0 * missing_required_fraction
        )
        risk += (
            calibration.get("context_switching_penalty", 0.0) * 100.0 * overload_fraction
        )
        risk = max(0.0, min(100.0, risk))
    total_missing = len(missing_required_skills) + len(missing_optional_skills)
    confidence = scoring.confidence_score(coverage, total_missing, data_complete=True)
    estimated_cost = _estimate_cost(assignments, members)

    # --- validity ----------------------------------------------------------
    invalid_reasons: List[str] = []
    is_valid = True
    if require_full_required_skill_coverage and missing_required_skills:
        is_valid = False
        invalid_reasons.append(
            "Missing required skill(s): " + ", ".join(missing_required_skills)
        )

    return SimulationResult(
        team=team,
        assignments=assignments,
        is_valid_team=is_valid,
        invalid_reasons=invalid_reasons,
        skill_coverage_score=round(coverage, 2),
        required_skill_coverage_score=round(required_coverage, 2),
        optional_skill_coverage_score=round(optional_coverage, 2),
        capacity_fit_score=round(capacity_fit, 2),
        estimated_cost=round(estimated_cost, 2),
        estimated_duration=round(estimated_duration, 2),
        critical_path=critical_path,
        workload_balance_score=round(balance, 2),
        productivity_score=round(productivity, 2),
        risk_score=round(risk, 2),
        confidence_score=round(confidence, 2),
        missing_required_skills=missing_required_skills,
        missing_optional_skills=missing_optional_skills,
        overloaded_members=overloaded_members,
        missing_required_fraction=missing_required_fraction,
        member_hours={k: round(v, 2) for k, v in member_hours.items()},
    )


def _estimate_cost(assignments: List[Assignment], members) -> float:
    """Sum of assigned hours * the assigned member's cost rate."""
    rate_by_name = {w.name: w.cost_rate for w in members}
    total = 0.0
    for a in assignments:
        if a.assigned_to is not None:
            total += a.assigned_hours * rate_by_name[a.assigned_to]
    return total
