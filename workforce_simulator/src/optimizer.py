"""Generate team combinations, simulate them, and rank the best.

This is the orchestration layer that ties the simulator, scheduler, and
scoring together:

1. Enumerate every valid team within the configured size limits, skipping
   duplicates.
2. Simulate + schedule each team to get its raw metrics.
3. Normalise cost across all teams into a cost-efficiency score.
4. Compute the weighted ``total_score`` (using the config weights and the
   required-skill penalty) and return the top N.
5. When ``require_full_required_skill_coverage`` is on, invalid teams are
   excluded from the top N; otherwise they are merely penalised.
6. Attach a deterministic plain-English explanation to each top team.
"""

from __future__ import annotations

from itertools import combinations
from typing import List

import scoring
from config_loader import SimConfig
from models import Team, Task, Worker
from simulator import SimulationResult, simulate_team


def generate_teams(
    humans: List[Worker], ai_agents: List[Worker], config: SimConfig
) -> List[Team]:
    """Enumerate all valid, unique team combinations within size limits."""
    teams: List[Team] = []
    seen = set()

    human_counts = range(
        config.min_humans_per_team,
        min(config.max_humans_per_team, len(humans)) + 1,
    )
    ai_counts = range(
        config.min_ai_agents_per_team,
        min(config.max_ai_agents_per_team, len(ai_agents)) + 1,
    )

    for h_count in human_counts:
        for human_combo in combinations(humans, h_count):
            for a_count in ai_counts:
                for ai_combo in combinations(ai_agents, a_count):
                    team = Team(humans=list(human_combo), ai_agents=list(ai_combo))
                    sig = team.signature()
                    if sig in seen:
                        continue
                    seen.add(sig)
                    teams.append(team)
    return teams


def simulate_all_teams(
    humans: List[Worker],
    ai_agents: List[Worker],
    tasks: List[Task],
    config: SimConfig,
    calibration: dict = None,
) -> List[SimulationResult]:
    """Generate and simulate every valid team (raw, pre-scoring).

    Returns one ``SimulationResult`` per team with all per-team metrics
    computed except ``cost_efficiency_score`` and ``total_score`` (those need
    the whole population and are added by ``finalize_scores``). Shared by
    ``rank_teams`` and the Project Mode endpoint so the simulation/scheduling
    logic lives in exactly one place.

    ``calibration`` (optional) is threaded into each team's simulation so
    approved multipliers affect duration/risk consistently across the
    population. ``None`` leaves every team's metrics unchanged.
    """
    teams = generate_teams(humans, ai_agents, config)
    require_full = config.require_full_required_skill_coverage
    return [simulate_team(t, tasks, require_full, calibration) for t in teams]


def finalize_scores(results: List[SimulationResult], config: SimConfig) -> None:
    """Compute cost efficiency + total score for a population, in place.

    Cost efficiency is min-max normalised across exactly the ``results`` list
    passed in, so totals are only comparable within one call. Pass every team
    you want to compare (including any manually built teams) in a single call.
    """
    if not results:
        return
    costs = [r.estimated_cost for r in results]
    min_cost, max_cost = min(costs), max(costs)
    for r in results:
        r.cost_efficiency_score = round(
            scoring.cost_efficiency_score(r.estimated_cost, min_cost, max_cost), 2
        )
        # Required coverage drives the skill_coverage slot so required skills
        # dominate the ranking; the required penalty further punishes gaps.
        r.total_score = round(
            scoring.total_score(
                {
                    "skill_coverage_score": r.required_skill_coverage_score,
                    "capacity_fit_score": r.capacity_fit_score,
                    "productivity_score": r.productivity_score,
                    "workload_balance_score": r.workload_balance_score,
                    "cost_efficiency_score": r.cost_efficiency_score,
                    "risk_score": r.risk_score,
                },
                weights=config.weights,
                missing_required_fraction=r.missing_required_fraction,
            ),
            2,
        )


def rank_teams(
    humans: List[Worker],
    ai_agents: List[Worker],
    tasks: List[Task],
    config: SimConfig,
    top_n: int = 5,
    calibration: dict = None,
) -> List[SimulationResult]:
    """Simulate every team and return the ``top_n`` ranked results."""
    results = simulate_all_teams(humans, ai_agents, tasks, config, calibration)
    if not results:
        return []

    finalize_scores(results, config)
    require_full = config.require_full_required_skill_coverage

    # When full required coverage is mandatory, drop invalid teams entirely.
    # Otherwise keep them - they are still ranked, just penalised, and sort
    # below valid teams via the is_valid_team key.
    pool = [r for r in results if r.is_valid_team] if require_full else results

    pool.sort(
        key=lambda r: (
            not r.is_valid_team,        # valid teams first
            -r.total_score,
            r.risk_score,
            r.estimated_cost,
            r.team.signature(),
        )
    )

    top = pool[:top_n]
    for i, r in enumerate(top, start=1):
        r.rank = i
        r.plain_english_explanation = explain(r)
    return top


def simulate_single_team(
    team: Team, tasks: List[Task], config: SimConfig, calibration: dict = None
) -> SimulationResult:
    """Simulate one explicitly chosen team (used by the API's manual mode).

    Reuses the same simulation, scoring, and explanation logic as the full
    ranking. Because only one team is evaluated, there is no population to
    normalise cost against, so ``cost_efficiency_score`` is reported as 100
    (the lone team is trivially the cheapest among the set of size one). Use
    ``rank_teams`` when you need cost efficiency compared across teams.

    ``calibration`` (optional) applies approved multipliers to this team's
    simulation; ``None`` leaves the metrics unchanged.
    """
    require_full = config.require_full_required_skill_coverage
    r = simulate_team(team, tasks, require_full, calibration)
    r.cost_efficiency_score = 100.0
    r.total_score = round(
        scoring.total_score(
            {
                "skill_coverage_score": r.required_skill_coverage_score,
                "capacity_fit_score": r.capacity_fit_score,
                "productivity_score": r.productivity_score,
                "workload_balance_score": r.workload_balance_score,
                "cost_efficiency_score": r.cost_efficiency_score,
                "risk_score": r.risk_score,
            },
            weights=config.weights,
            missing_required_fraction=r.missing_required_fraction,
        ),
        2,
    )
    r.rank = 1
    r.plain_english_explanation = explain(r)
    return r


# ---------------------------------------------------------------------------
# Deterministic explanation
# ---------------------------------------------------------------------------

def explain(result: SimulationResult) -> str:
    """Build a deterministic, template-based explanation (no LLM).

    Mentions, in order: why the team ranked where it did, required-skill
    coverage, which AI agents helped and how, the biggest bottleneck, the
    critical path, and the main tradeoff.
    """
    team = result.team
    humans = ", ".join(team.human_names) if team.human_names else "no humans"
    ai_part = (
        " plus " + ", ".join(team.ai_names) if team.ai_names else " with no AI agents"
    )

    sentences: List[str] = []

    # 1. Headline / why it ranked here. ``rank`` is 0 for standalone teams
    # (e.g. Project Mode options) that are not part of a 1..N ranking.
    if result.rank:
        sentences.append(
            f"Team {result.rank} ({humans}{ai_part}) ranked #{result.rank} "
            f"with a total score of {result.total_score}."
        )
    else:
        sentences.append(
            f"This team ({humans}{ai_part}) scores "
            f"{result.total_score} overall."
        )

    # 2. Required skill coverage.
    if not result.missing_required_skills:
        sentences.append(
            f"All required skills are covered "
            f"(required coverage {result.required_skill_coverage_score:.0f}%, "
            f"optional {result.optional_skill_coverage_score:.0f}%)."
        )
    else:
        sentences.append(
            "It is missing required skill(s): "
            + ", ".join(result.missing_required_skills)
            + f" (required coverage only "
            f"{result.required_skill_coverage_score:.0f}%)."
        )

    # 3. How AI agents helped.
    ai_tasks = [a for a in result.assignments if a.assigned_type == "ai_agent"]
    if ai_tasks:
        details = ", ".join(
            f"{a.assigned_to} on {a.task}" for a in ai_tasks
        )
        sentences.append(
            "AI agents sped up work by taking: " + details + "."
        )
    else:
        sentences.append("No AI agents were used on this team.")

    # 4. Biggest bottleneck = busiest member (longest serial workload).
    if result.member_hours:
        busiest = max(result.member_hours.items(), key=lambda kv: (kv[1], kv[0]))
        if busiest[1] > 0:
            sentences.append(
                f"The biggest bottleneck is {busiest[0]} carrying "
                f"{busiest[1]:.1f} hours of work."
            )

    # 5. Critical path.
    if result.critical_path:
        sentences.append(
            "The critical path (driving the "
            f"{result.estimated_duration:.0f}h duration) is: "
            + " -> ".join(result.critical_path)
            + "."
        )

    # 6. Main tradeoff: strongest vs weakest scored dimension.
    sentences.append(_tradeoff_sentence(result))

    return " ".join(sentences)


def _tradeoff_sentence(result: SimulationResult) -> str:
    """Describe the team's main tradeoff from its strongest/weakest scores."""
    dimensions = {
        "skill coverage": result.required_skill_coverage_score,
        "cost efficiency": result.cost_efficiency_score,
        "speed/productivity": result.productivity_score,
        "workload balance": result.workload_balance_score,
        "capacity fit": result.capacity_fit_score,
    }
    strongest = max(dimensions.items(), key=lambda kv: kv[1])
    weakest = min(dimensions.items(), key=lambda kv: kv[1])
    if strongest[0] == weakest[0]:
        return "It is well balanced across all scoring dimensions."
    return (
        f"The main tradeoff is strong {strongest[0]} ({strongest[1]:.0f}) "
        f"at the cost of weaker {weakest[0]} ({weakest[1]:.0f})."
    )
