"""Honest handling of work nobody on the roster can do, and of project length.

Two input problems used to produce misleading numbers:

* **Skill gaps.** A task whose skill no person or AI agent has was silently
  left out of cost and duration, so a plan could read "$0, 0h, 100% chance of
  hitting the deadline" while nothing was actually staffed. Now each such
  skill gets a clearly labelled placeholder, "Outside hire (<skill>)", so the
  gap work is scheduled and counted. Its cost uses the hourly rate the user
  gives; with no rate the cost is reported as *not included*, never as $0.
* **Capacity basis.** Roster capacity/workload columns are hours **per week**.
  The engine compares them with the whole project's work, so they are
  multiplied by the project length in weeks.

Deterministic, no LLM.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional, Tuple

from models import HUMAN, Task, Worker

OUTSIDE_ROLE = "Outside help"
# Placeholder quality (0-10): an unknown contractor is assumed average.
OUTSIDE_QUALITY = 7.0
HOURS_PER_WEEK = 40.0


def is_outside(worker: Worker) -> bool:
    return getattr(worker, "role", "") == OUTSIDE_ROLE


def outside_name(skill: str) -> str:
    return f"Outside hire ({skill})"


def gap_skills(tasks: List[Task], employees: List[Worker], ai_agents: List[Worker]) -> List[str]:
    """Skills some task needs that no person or AI agent has (first-seen casing)."""
    pool = list(employees) + list(ai_agents)
    seen = set()
    gaps: List[str] = []
    for t in tasks:
        key = t.required_skill.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        if not any(w.has_skill(t.required_skill) for w in pool):
            gaps.append(t.required_skill)
    return gaps


def outside_workers(gaps: List[str], tasks: List[Task], rate: Optional[float]) -> List[Worker]:
    """One placeholder per gap skill, with room for all of that skill's work."""
    workers = []
    for skill in gaps:
        hours = sum(
            t.effort_hours for t in tasks
            if t.required_skill.strip().lower() == skill.strip().lower()
        )
        workers.append(Worker(
            name=outside_name(skill), type=HUMAN, role=OUTSIDE_ROLE,
            skills=[skill], capacity_hours=hours + 1.0, workload_hours=0.0,
            cost_rate=float(rate or 0.0), quality_score=OUTSIDE_QUALITY,
        ))
    return workers


def staffable_tasks(tasks: List[Task], gaps: List[str]) -> List[Task]:
    """Tasks the roster can do, with dependencies on gap tasks removed.

    Used to choose the roster part of each team; the gap work is added back
    (done by the placeholders) before any number is reported.
    """
    gap_keys = {g.strip().lower() for g in gaps}
    gap_names = {t.task for t in tasks if t.required_skill.strip().lower() in gap_keys}
    return [
        replace(t, dependencies=[d for d in t.dependencies if d not in gap_names])
        for t in tasks if t.task not in gap_names
    ]


def gap_summary(tasks: List[Task], gaps: List[str], rate: Optional[float]) -> dict:
    """What the user needs to know about the outside help."""
    gap_keys = {g.strip().lower() for g in gaps}
    items = [
        {"task": t.task, "skill": t.required_skill, "hours": t.effort_hours}
        for t in tasks if t.required_skill.strip().lower() in gap_keys
    ]
    hours = round(sum(i["hours"] for i in items), 2)
    rate = float(rate) if rate else None
    if not items:
        message = ""
    else:
        skills = ", ".join(gaps)
        lead = (
            f"Nobody on your roster (and no AI agent) has: {skills}. "
            f"That's {hours:g}h of work across {len(items)} task(s), planned "
            "here as outside help."
        )
        if rate:
            message = (
                f"{lead} At ${rate:,.0f}/h that adds about "
                f"${hours * rate:,.0f}, included in the costs shown."
            )
        else:
            message = (
                f"{lead} Its cost is NOT included in the costs shown - add an "
                "hourly rate for outside help to include it."
            )
    return {
        "skills": list(gaps),
        "tasks": items,
        "hours": hours,
        "rate": rate,
        "cost_estimate": round(hours * rate, 2) if (rate and items) else None,
        "cost_included": bool(rate) or not items,
        "message": message,
    }


def resolve_weeks(
    project_weeks: Optional[float], deadline_target_hours: Optional[float]
) -> Tuple[float, str, str]:
    """Project length in weeks, where it came from, and a plain explanation."""
    if project_weeks and project_weeks > 0:
        weeks, source = float(project_weeks), "set"
        how = f"the project length you set ({weeks:g} week{'' if weeks == 1 else 's'})"
    elif deadline_target_hours and deadline_target_hours > 0:
        weeks, source = max(1.0, deadline_target_hours / HOURS_PER_WEEK), "deadline"
        how = (
            f"your {deadline_target_hours:g}h deadline (~{weeks:.1f} weeks at "
            f"{HOURS_PER_WEEK:g}h a week)"
        )
    else:
        weeks, source = 1.0, "default"
        how = "a 1-week project, because no project length or deadline was set"
    text = (
        "Roster hours are per week. Each person's free time per week "
        f"(capacity minus current workload) is multiplied by {how}."
    )
    return weeks, source, text


def scale_capacity(employees: List[Worker], weeks: float) -> List[Worker]:
    """Copies of ``employees`` with weekly capacity/workload scaled to the project."""
    if weeks == 1.0:
        return list(employees)
    return [
        replace(w, capacity_hours=w.capacity_hours * weeks,
                workload_hours=w.workload_hours * weeks)
        for w in employees
    ]


def capacity_basis(project_weeks, deadline_target_hours) -> Dict[str, object]:
    weeks, source, text = resolve_weeks(project_weeks, deadline_target_hours)
    return {"weeks": round(weeks, 2), "source": source, "explanation": text}
