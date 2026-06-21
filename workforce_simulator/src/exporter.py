"""Write ranked simulation results to JSON and CSV.

The JSON keeps the full nested structure (including per-task assignments),
while the CSV is a flat, spreadsheet-friendly summary with the task
assignments collapsed into a single readable string.
"""

from __future__ import annotations

import json
import os
from typing import List

import pandas as pd

from simulator import SimulationResult


def result_to_dict(result: SimulationResult) -> dict:
    """Convert a ``SimulationResult`` into the export schema."""
    return {
        "rank": result.rank,
        "team_members": result.team.human_names,
        "ai_agents": result.team.ai_names,
        "total_score": result.total_score,
        "skill_coverage_score": result.skill_coverage_score,
        "capacity_fit_score": result.capacity_fit_score,
        "estimated_cost": result.estimated_cost,
        "estimated_duration": result.estimated_duration,
        "workload_balance_score": result.workload_balance_score,
        "productivity_score": result.productivity_score,
        "cost_efficiency_score": result.cost_efficiency_score,
        "risk_score": result.risk_score,
        "confidence_score": result.confidence_score,
        "missing_skills": result.missing_skills,
        "overloaded_members": result.overloaded_members,
        "task_assignments": [a.as_dict() for a in result.assignments],
        "plain_english_explanation": result.plain_english_explanation,
    }


def _assignments_summary(result: SimulationResult) -> str:
    """Collapse task assignments into a single CSV-friendly string."""
    pieces = []
    for a in result.assignments:
        who = a.assigned_to if a.assigned_to else "UNASSIGNED"
        pieces.append(f"{a.task}->{who}")
    return "; ".join(pieces)


def export_json(results: List[SimulationResult], path: str) -> None:
    """Write the full results to a JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = [result_to_dict(r) for r in results]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def export_csv(results: List[SimulationResult], path: str) -> None:
    """Write a flat summary of the results to a CSV file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = []
    for r in results:
        rows.append(
            {
                "rank": r.rank,
                "team_members": "|".join(r.team.human_names),
                "ai_agents": "|".join(r.team.ai_names),
                "total_score": r.total_score,
                "skill_coverage_score": r.skill_coverage_score,
                "capacity_fit_score": r.capacity_fit_score,
                "estimated_cost": r.estimated_cost,
                "estimated_duration": r.estimated_duration,
                "workload_balance_score": r.workload_balance_score,
                "productivity_score": r.productivity_score,
                "cost_efficiency_score": r.cost_efficiency_score,
                "risk_score": r.risk_score,
                "confidence_score": r.confidence_score,
                "missing_skills": "|".join(r.missing_skills),
                "overloaded_members": "|".join(r.overloaded_members),
                "task_assignments": _assignments_summary(r),
                "plain_english_explanation": r.plain_english_explanation,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)
