"""Generate team combinations, simulate them, and rank the best.

This is the orchestration layer that ties the simulator and scoring
together:

1. Enumerate every valid team (2-5 humans, 0-2 AI agents), skipping
   duplicates.
2. Simulate each team to get its raw metrics.
3. Normalise cost across all teams into a cost-efficiency score.
4. Compute the weighted ``total_score`` and return the top N.
5. Attach a deterministic plain-English explanation to each top team.
"""

from __future__ import annotations

from itertools import combinations
from typing import List

import scoring
from models import Team, Task, Worker
from simulator import SimulationResult, simulate_team


# Team size constraints from the brief.
MIN_HUMANS = 2
MAX_HUMANS = 5
MIN_AI = 0
MAX_AI = 2


def generate_teams(humans: List[Worker], ai_agents: List[Worker]) -> List[Team]:
    """Enumerate all valid, unique team combinations.

    Combinations are inherently order-independent so duplicates only arise
    if the input data contains repeated names; we de-dup defensively using
    each team's signature.
    """
    teams: List[Team] = []
    seen = set()

    human_counts = range(MIN_HUMANS, min(MAX_HUMANS, len(humans)) + 1)
    ai_counts = range(MIN_AI, min(MAX_AI, len(ai_agents)) + 1)

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


def rank_teams(
    humans: List[Worker],
    ai_agents: List[Worker],
    tasks: List[Task],
    top_n: int = 5,
) -> List[SimulationResult]:
    """Simulate every team and return the ``top_n`` ranked results."""
    teams = generate_teams(humans, ai_agents)
    results = [simulate_team(team, tasks) for team in teams]

    if not results:
        return []

    # Cost efficiency needs the global cost range.
    costs = [r.estimated_cost for r in results]
    min_cost, max_cost = min(costs), max(costs)

    for r in results:
        r.cost_efficiency_score = round(
            scoring.cost_efficiency_score(r.estimated_cost, min_cost, max_cost), 2
        )
        r.total_score = round(
            scoring.total_score(
                {
                    "skill_coverage_score": r.skill_coverage_score,
                    "capacity_fit_score": r.capacity_fit_score,
                    "productivity_score": r.productivity_score,
                    "workload_balance_score": r.workload_balance_score,
                    "cost_efficiency_score": r.cost_efficiency_score,
                    "risk_score": r.risk_score,
                }
            ),
            2,
        )

    # Rank by total score. Ties broken deterministically: lower risk, then
    # lower cost, then team signature.
    results.sort(
        key=lambda r: (
            -r.total_score,
            r.risk_score,
            r.estimated_cost,
            r.team.signature(),
        )
    )

    top = results[:top_n]
    for i, r in enumerate(top, start=1):
        r.rank = i
        r.plain_english_explanation = explain(r)
    return top


def explain(result: SimulationResult) -> str:
    """Build a deterministic, template-based explanation (no LLM).

    The explanation cites the team's strongest reasons for its rank and
    surfaces its biggest risk, using the numbers already computed.
    """
    team = result.team
    human_part = ", ".join(team.human_names) if team.human_names else "no humans"
    if team.ai_names:
        ai_part = " plus " + ", ".join(team.ai_names)
    else:
        ai_part = " with no AI agents"

    parts: List[str] = []
    parts.append(
        f"Team {result.rank} ({human_part}{ai_part}) ranked "
        f"#{result.rank} with a total score of {result.total_score}."
    )
    parts.append(
        f"It covers {result.skill_coverage_score:.0f} percent of the "
        f"required skills"
    )

    # Capacity phrasing.
    if result.capacity_fit_score >= 99:
        parts[-1] += " and stays comfortably within available capacity"
    elif result.capacity_fit_score >= 60:
        parts[-1] += " and mostly fits within available capacity"
    else:
        parts[-1] += " but is stretched beyond its available capacity"

    # Highlight AI leverage if any agent picked up work.
    ai_used = [
        a.assigned_to
        for a in result.assignments
        if a.assigned_type == "ai_agent"
    ]
    if ai_used:
        unique_ai = sorted(set(ai_used))
        parts[-1] += (
            f", using {', '.join(unique_ai)} to speed up part of the work"
        )
    parts[-1] += "."

    # Risk sentence.
    if result.missing_skills:
        parts.append(
            "The main risk is missing coverage for: "
            + ", ".join(result.missing_skills)
            + "."
        )
    elif result.overloaded_members:
        parts.append(
            "The main risk is overload on: "
            + ", ".join(result.overloaded_members)
            + "."
        )
    elif result.workload_balance_score < 60:
        parts.append(
            "The main risk is uneven workload distribution across the team."
        )
    else:
        parts.append(
            f"Overall risk is low (risk score {result.risk_score}) and "
            f"confidence is {result.confidence_score:.0f}."
        )

    return " ".join(parts)
