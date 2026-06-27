"""Staffing-strategy candidate generators (deterministic; no LLM).

Each strategy is *only* a candidate-plan generator: it decides which kind of
worker (human vs AI) should own each task, conjures the AI agents the plan
needs, and returns a ``Team`` plus a per-task ``allowed_types`` constraint. The
plan is then handed to the **unchanged** scheduler and scorer (via
``simulator.simulate_team``) like any other team. Nothing here scores,
schedules, or changes the task-routing rules.

AI agents are **dynamic and unlimited**: there is no fixed catalog. For every
task a strategy assigns to AI, one agent is conjured on demand, with its
capability and effectiveness derived from the same per-skill routing
"suitability sheet" the rest of the engine uses (``routing.SKILL_PROFILES``).
The number of agents simply falls out of the work - no cap, no menu.

Strategies (all draw humans from the manager's selected team):

* ``ai_first_eligible``     - AI owns every task the routing marks AI_ONLY or
  AI_FIRST_HUMAN_REVIEW (a human still reviews the latter, via the routing
  burden layer); humans own the rest.
* ``human_core_ai_gap_fill`` - humans lead by default; AI is added only for
  clearly-safe AI_ONLY work and to fill skill gaps no human can cover (when the
  routing says AI can credibly own that skill).
* ``human_first_ai_assist`` - humans own every task; AI never owns or fills a
  gap, so a required skill no human has shows up as an (honest) invalid plan.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import routing
from models import AI_AGENT, HUMAN, Task, Team, Worker


# Strategy keys.
AI_FIRST = "ai_first_eligible"
HUMAN_CORE = "human_core_ai_gap_fill"
HUMAN_FIRST = "human_first_ai_assist"
ASSIGNMENT_STRATEGIES = (HUMAN_CORE, AI_FIRST, HUMAN_FIRST)

# A conjured AI agent's hourly cost. Generic and cheap relative to humans
# (~$70-110/h here); in the same ballpark as the engine's historical agents.
AI_AGENT_COST_RATE = 18.0


def _ai_can_own(decision: str) -> bool:
    """AI may *own* a task only where the routing says it can lead it."""
    return decision in (routing.AI_ONLY, routing.AI_FIRST_HUMAN_REVIEW)


def _derive_quality(scores: Optional[Dict[str, int]]) -> float:
    """0-10 quality for a conjured agent, from the skill's AI-capability fit."""
    fit = (scores or {}).get("ai_capability_fit", 3) or 3
    return round(min(10.0, max(2.0, fit * 2.0)), 1)


def _derive_speed(scores: Optional[Dict[str, int]]) -> float:
    """Speed multiplier (>1) for a conjured agent, from the skill's speed value."""
    sv = (scores or {}).get("speed_value", 3) or 3
    return round(1.0 + 0.1 * float(sv), 2)  # 1.1 .. 1.5


def synthesize_agent(task: Task, scores: Optional[Dict[str, int]], name: str) -> Worker:
    """Conjure a single AI agent sized for one task, grounded in the sheet.

    Capacity is right-sized to this one task so the agent is fully (and only)
    occupied by it - which keeps the workload-balance score honest and gives
    unlimited, fully-parallel AI (one agent per AI-owned task).
    """
    speed = _derive_speed(scores)
    effort = float(task.effort_hours)
    needed = effort / speed if speed else effort
    return Worker(
        name=name,
        type=AI_AGENT,
        role="AI agent",
        skills=[task.required_skill],
        capacity_hours=round(max(needed, 0.01), 4),
        workload_hours=0.0,
        cost_rate=AI_AGENT_COST_RATE,
        quality_score=_derive_quality(scores),
        speed_multiplier=speed,
    )


def _owner_for(strategy: str, decision: str, has_human_skill: bool) -> str:
    """Return HUMAN or AI_AGENT for one task under a given strategy."""
    if strategy == AI_FIRST:
        return AI_AGENT if _ai_can_own(decision) else HUMAN

    if strategy == HUMAN_CORE:
        if decision == routing.AI_ONLY:
            return AI_AGENT                       # clearly-safe AI work
        if not has_human_skill and _ai_can_own(decision):
            return AI_AGENT                       # gap fill (AI can own it)
        return HUMAN

    # HUMAN_FIRST: humans own everything; AI never owns.
    return HUMAN


def _note(strategy: str, name: str, task: Task, decision: str, has_human_skill: bool) -> str:
    """Plain-English reason an AI agent was conjured for a task."""
    if strategy == HUMAN_CORE and not has_human_skill:
        return f"{name}: fills the {task.required_skill} gap (no human covers it)."
    if decision == routing.AI_ONLY:
        return f"{name}: owns {task.task} (routing says AI can handle it end to end)."
    return f"{name}: drafts {task.task}; a human reviews ({decision})."


def build_plan(
    strategy: str,
    humans: List[Worker],
    tasks: List[Task],
    routing_by_task: Dict[str, dict],
) -> Tuple[Team, Dict[str, set], List[Worker], List[str]]:
    """Build one strategy's candidate plan.

    Returns ``(team, allowed_types, agents_added, notes)`` ready to feed to
    ``simulator.simulate_team(team, tasks, ..., allowed_types=allowed_types)``.
    ``routing_by_task`` maps a task name to ``{"decision": str, "scores": dict}``
    from the existing routing layer (so strategies use the same routing the user
    sees; this module never changes routing).
    """
    human_skills = {
        s.strip().lower() for h in humans for s in h.skills
    }
    agents: List[Worker] = []
    allowed: Dict[str, set] = {}
    notes: List[str] = []
    skill_counts: Dict[str, int] = {}

    for t in tasks:
        info = routing_by_task.get(t.task, {})
        decision = info.get("decision", routing.ESCALATE)
        scores = info.get("scores")
        has_human = t.required_skill.strip().lower() in human_skills
        owner = _owner_for(strategy, decision, has_human)

        if owner == AI_AGENT:
            key = t.required_skill.strip().lower()
            n = skill_counts.get(key, 0) + 1
            skill_counts[key] = n
            name = f"AI {t.required_skill} Agent" if n == 1 else f"AI {t.required_skill} Agent {n}"
            agents.append(synthesize_agent(t, scores, name))
            allowed[t.task] = {AI_AGENT}
            notes.append(_note(strategy, name, t, decision, has_human))
        else:
            allowed[t.task] = {HUMAN}

    return Team(list(humans), agents), allowed, agents, notes
