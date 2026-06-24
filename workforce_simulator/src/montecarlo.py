"""Monte-Carlo uncertainty analysis.

Project estimates are uncertain: a task that "should" take 20 hours might take
16 or 35. This module propagates that uncertainty by running the *existing*
critical-path simulation many times. Each iteration samples a duration for
every task from a three-point (optimistic / likely / pessimistic) range, then
runs the real scheduler to get a project duration and cost. Over hundreds of
iterations we report true statistics: P10/P50/P90 duration and cost, and the
empirical probability of hitting a deadline or budget.

This is the patent's "run a plurality of iterations… factoring in unforeseen
challenges, resource availability, or changes in project scope." Nothing is
invented - it is correct statistics over the uncertainty the user supplies.

Reproducible: a fixed ``seed`` makes every run identical.
"""

from __future__ import annotations

import random
from dataclasses import replace
from typing import List, Optional, Tuple

from config_loader import SimConfig
from models import Task, Team, Worker
from project_mode import ProjectModeError, tasks_from_request
from simulator import simulate_team


# Default uncertainty band applied to a task's single effort estimate when no
# explicit optimistic/pessimistic value is given. Optimistic = 0.8x, likely =
# the given estimate, pessimistic = 1.5x. These are visible, editable
# assumptions - not hidden fudge factors.
DEFAULT_LOW_FACTOR = 0.8
DEFAULT_HIGH_FACTOR = 1.5
DEFAULT_ITERATIONS = 500
MAX_ITERATIONS = 5000
DEFAULT_SEED = 42


def _three_point(task_dict: dict, low_factor: float, high_factor: float) -> Tuple[float, float, float]:
    """Return (optimistic, likely, pessimistic) effort for one task.

    Uses explicit ``effort_optimistic`` / ``effort_pessimistic`` when supplied,
    otherwise derives them from the single ``effort_hours`` estimate using the
    default band. The three values are sorted so low <= mode <= high regardless
    of how they were provided.
    """
    likely = float(task_dict["effort_hours"])
    low = task_dict.get("effort_optimistic")
    high = task_dict.get("effort_pessimistic")
    low = float(low) if low is not None else likely * low_factor
    high = float(high) if high is not None else likely * high_factor
    low, mode, high = sorted([low, likely, high])
    return low, mode, high


def _percentile(sorted_values: List[float], pct: float) -> float:
    """Linear-interpolation percentile (pct in 0..100) on a sorted list."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low_idx = int(rank)
    frac = rank - low_idx
    if low_idx + 1 >= len(sorted_values):
        return sorted_values[-1]
    return sorted_values[low_idx] + frac * (
        sorted_values[low_idx + 1] - sorted_values[low_idx]
    )


def _histogram(values: List[float], bins: int = 10) -> List[dict]:
    """Bucket values into ``bins`` equal-width bins for a simple chart."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi <= lo:
        return [{"lo": round(lo, 2), "hi": round(hi, 2), "count": len(values)}]
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(bins - 1, int((v - lo) / width))
        counts[idx] += 1
    return [
        {"lo": round(lo + i * width, 2), "hi": round(lo + (i + 1) * width, 2), "count": c}
        for i, c in enumerate(counts)
    ]


def _stats(values: List[float], bins: int = 10) -> dict:
    """Summary statistics + histogram for a sample."""
    s = sorted(values)
    n = len(s)
    mean = sum(s) / n if n else 0.0
    var = sum((v - mean) ** 2 for v in s) / n if n else 0.0
    return {
        "mean": round(mean, 2),
        "std": round(var ** 0.5, 2),
        "min": round(s[0], 2) if n else 0.0,
        "p10": round(_percentile(s, 10), 2),
        "p50": round(_percentile(s, 50), 2),
        "p90": round(_percentile(s, 90), 2),
        "max": round(s[-1], 2) if n else 0.0,
        "histogram": _histogram(s, bins),
    }


def run_uncertainty(
    employees: List[Worker],
    ai_agents: List[Worker],
    request: dict,
    config: SimConfig,
    calibration: dict = None,
) -> dict:
    """Run the Monte-Carlo uncertainty analysis for one team.

    ``request`` carries the tasks (with optional per-task effort ranges), the
    team (human + AI agent names), iteration count, seed, and optional
    deadline/budget targets. Raises ``ProjectModeError`` for user-fixable input
    problems (unknown names, empty team/tasks).

    ``calibration`` (optional) applies approved multipliers to the baseline and
    every sampled iteration, so the uncertainty bands reflect calibration too.
    ``None`` leaves all iterations unchanged.
    """
    task_dicts = request.get("tasks") or []
    if not task_dicts:
        raise ProjectModeError("At least one task is required.")

    iterations = int(request.get("iterations") or DEFAULT_ITERATIONS)
    if iterations < 1 or iterations > MAX_ITERATIONS:
        raise ProjectModeError(
            f"iterations must be between 1 and {MAX_ITERATIONS}."
        )
    seed = int(request.get("seed", DEFAULT_SEED))
    low_factor = float(request.get("default_low_factor", DEFAULT_LOW_FACTOR))
    high_factor = float(request.get("default_high_factor", DEFAULT_HIGH_FACTOR))

    humans_by = {w.name: w for w in employees}
    ais_by = {w.name: w for w in ai_agents}
    human_names = request.get("human_names", []) or []
    ai_names = request.get("ai_agent_names", []) or []
    unknown_h = [n for n in human_names if n not in humans_by]
    unknown_a = [n for n in ai_names if n not in ais_by]
    if unknown_h or unknown_a:
        raise ProjectModeError(
            f"Unknown team names. Humans: {unknown_h}. AI agents: {unknown_a}."
        )
    if not human_names and not ai_names:
        raise ProjectModeError("Select at least one team member.")

    team = Team(
        humans=[humans_by[n] for n in human_names],
        ai_agents=[ais_by[n] for n in ai_names],
    )
    require_full = config.require_full_required_skill_coverage

    # Base tasks (engine objects) + the sampling range for each, in order.
    base_tasks: List[Task] = tasks_from_request(task_dicts)
    ranges = [_three_point(td, low_factor, high_factor) for td in task_dicts]

    # Deterministic baseline using the "likely" (mode) effort for reference.
    baseline_tasks = [
        replace(base_tasks[i], effort_hours=ranges[i][1]) for i in range(len(base_tasks))
    ]
    baseline = simulate_team(
        Team(team.humans, team.ai_agents), baseline_tasks, require_full, calibration
    )

    rng = random.Random(seed)
    durations: List[float] = []
    costs: List[float] = []
    for _ in range(iterations):
        sampled = [
            replace(
                base_tasks[i],
                effort_hours=rng.triangular(ranges[i][0], ranges[i][2], ranges[i][1]),
            )
            for i in range(len(base_tasks))
        ]
        res = simulate_team(
            Team(team.humans, team.ai_agents), sampled, require_full, calibration
        )
        durations.append(res.estimated_duration)
        costs.append(res.estimated_cost)

    deadline = request.get("deadline_target_hours")
    budget = request.get("budget_target")
    prob_deadline = (
        round(sum(1 for d in durations if d <= float(deadline)) / iterations, 4)
        if deadline is not None else None
    )
    prob_budget = (
        round(sum(1 for c in costs if c <= float(budget)) / iterations, 4)
        if budget is not None else None
    )

    return {
        "iterations": iterations,
        "seed": seed,
        "deterministic": True,
        "team": {"humans": team.human_names, "ai_agents": team.ai_names},
        "is_valid_team": baseline.is_valid_team,
        "missing_required_skills": baseline.missing_required_skills,
        "effort_model": {
            "distribution": "triangular",
            "default_low_factor": low_factor,
            "default_high_factor": high_factor,
            "note": (
                "Each task's effort is sampled from a triangular distribution "
                "between its optimistic, likely, and pessimistic estimates. "
                "Ranges default to the band shown and are editable per task."
            ),
        },
        "baseline": {
            "duration": baseline.estimated_duration,
            "cost": baseline.estimated_cost,
            "note": "Single run using each task's 'likely' effort.",
        },
        "duration": _stats(durations),
        "cost": _stats(costs),
        "deadline_target_hours": deadline,
        "probability_meets_deadline": prob_deadline,
        "budget_target": budget,
        "probability_within_budget": prob_budget,
        "task_ranges": [
            {
                "task": base_tasks[i].task,
                "optimistic": round(ranges[i][0], 2),
                "likely": round(ranges[i][1], 2),
                "pessimistic": round(ranges[i][2], 2),
            }
            for i in range(len(base_tasks))
        ],
    }
