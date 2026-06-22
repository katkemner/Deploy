"""Deterministic scoring formulas for the workforce simulator.

Every function here is a pure, deterministic calculation: the same input
always produces the same output. No randomness and no LLM calls are used
anywhere.

All scores are expressed on a 0-100 scale (higher is better) except
``risk_score`` where higher means *more* risk. Quality ratings in the
source data are on a 0-10 scale and are converted to 0-100 internally.

A note on the formulas: these are intentionally simple, transparent
heuristics chosen so a human can read the code and understand exactly why
a team scored the way it did. They are not calibrated against real
project data - that tuning is future work.
"""

from __future__ import annotations

from statistics import pstdev
from typing import Dict, List


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Clamp ``value`` into the ``[low, high]`` range."""
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# Individual metric scores
# ---------------------------------------------------------------------------

def skill_coverage_score(covered_tasks: int, total_tasks: int) -> float:
    """Percentage of tasks for which at least one member has the skill.

    Used for overall coverage and, with the right counts, for required-only
    or optional-only coverage. When ``total_tasks`` is 0 (e.g. no optional
    tasks exist) coverage is treated as a perfect 100 - there is nothing
    left uncovered.
    """
    if total_tasks == 0:
        return 100.0
    return _clamp(100.0 * covered_tasks / total_tasks)


def capacity_fit_score(total_assigned: float, total_overflow: float) -> float:
    """How well individual members' capacity covers their assigned work.

    ``total_overflow`` is the sum, across members, of hours assigned beyond
    each member's available hours. Using per-member overflow (rather than a
    team-wide total) means a team is only "a good fit" when no single person
    is overloaded - even if the team as a whole has spare capacity sitting
    on idle members.

    * No overflow -> perfect fit (100).
    * The score falls as a larger share of the assigned work spills past
      individual capacity, reaching 0 when overflow equals the total work.
    """
    if total_assigned <= 0:
        return 100.0
    return _clamp(100.0 * (1.0 - total_overflow / total_assigned))


def workload_balance_score(utilizations: List[float]) -> float:
    """Reward evenly distributed workload.

    ``utilizations`` is each member's ``assigned_hours / available_hours``.
    We measure the spread with the population standard deviation: a team
    where everyone is loaded similarly has a low spread and a high score.
    A perfectly even team scores 100.
    """
    if not utilizations:
        return 0.0
    if len(utilizations) == 1:
        # A single worker is trivially "balanced".
        return 100.0
    spread = pstdev(utilizations)
    # A spread of 0 -> 100. A spread of 2.0 (very uneven, e.g. one member
    # badly overloaded while others sit idle) -> 0. Dividing by 2 keeps the
    # score from saturating to 0 too quickly so teams stay distinguishable.
    return _clamp(100.0 * (1.0 - spread / 2.0))


def productivity_score(
    coverage: float,
    avg_quality_0_100: float,
    avg_speed_multiplier: float,
    capacity_fit: float,
) -> float:
    """Blend coverage, quality, speed, and capacity fit into one score.

    Speed is normalised so that an average multiplier of 1.0 (all humans)
    maps to ~67 and 1.5 (fast AI-heavy team) maps to 100.
    """
    speed_component = _clamp(100.0 * (avg_speed_multiplier / 1.5))
    return _clamp(
        0.40 * coverage
        + 0.20 * avg_quality_0_100
        + 0.20 * speed_component
        + 0.20 * capacity_fit
    )


def risk_score(
    missing_skill_fraction: float,
    overload_fraction: float,
    workload_balance: float,
    coverage: float,
) -> float:
    """Combine the main sources of risk. Higher means riskier.

    * Missing skills are the biggest risk (40% weight).
    * Overloaded members come next (25%).
    * Poor workload balance (20%) and low coverage (15%) round it out.
    """
    return _clamp(
        40.0 * missing_skill_fraction
        + 25.0 * overload_fraction
        + 20.0 * (1.0 - workload_balance / 100.0)
        + 15.0 * (1.0 - coverage / 100.0)
    )


def confidence_score(
    coverage: float,
    missing_skill_count: int,
    data_complete: bool,
) -> float:
    """How much to trust this simulation.

    Confidence tracks data completeness and skill coverage. Each missing
    skill knocks off 15 points, and incomplete input data caps the score.
    """
    score = coverage  # start from coverage as the base confidence
    score -= 15.0 * missing_skill_count
    if not data_complete:
        score = min(score, 50.0)
    return _clamp(score)


def cost_efficiency_score(cost: float, min_cost: float, max_cost: float) -> float:
    """Normalise cost across all teams so cheaper teams score higher.

    This is the only score that depends on the whole population of teams
    (it needs the cheapest and most expensive costs to normalise). The
    cheapest team scores 100, the most expensive scores 0.
    """
    if max_cost <= min_cost:
        return 100.0  # all teams cost the same
    return _clamp(100.0 * (max_cost - cost) / (max_cost - min_cost))


# ---------------------------------------------------------------------------
# Final ranking score
# ---------------------------------------------------------------------------

# Default weights (already normalised to sum to 1.0). The config file can
# override these; see ``config_loader.py``.
DEFAULT_WEIGHTS = {
    "skill_coverage": 0.30,
    "capacity_fit": 0.20,
    "productivity": 0.20,
    "workload_balance": 0.15,
    "cost_efficiency": 0.10,
    "low_risk": 0.05,
}

# Maximum points subtracted from a team's total when *all* of its required
# skills are missing. Scaled by the fraction of required skills missing, this
# is the "major penalty" required tasks impose.
REQUIRED_MISSING_PENALTY = 40.0


def total_score(
    scores: Dict[str, float],
    weights: Dict[str, float] = None,
    missing_required_fraction: float = 0.0,
) -> float:
    """Weighted total used to rank teams.

    ``scores`` supplies each component on a 0-100 scale. The ``skill_coverage``
    component should be the *required* skill coverage so required skills drive
    the ranking. ``weights`` are the (normalised) config weights; defaults are
    used if omitted.

    ``missing_required_fraction`` applies the major required-skill penalty:
    the more required skills a team cannot cover, the more its total drops.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    low_risk = 100.0 - scores["risk_score"]
    components = {
        "skill_coverage": scores["skill_coverage_score"],
        "capacity_fit": scores["capacity_fit_score"],
        "productivity": scores["productivity_score"],
        "workload_balance": scores["workload_balance_score"],
        "cost_efficiency": scores["cost_efficiency_score"],
        "low_risk": low_risk,
    }
    base = sum(weights.get(key, 0.0) * value for key, value in components.items())
    penalty = REQUIRED_MISSING_PENALTY * missing_required_fraction
    return _clamp(base - penalty)
