"""Load the sample CSV data into model objects.

Uses pandas for convenient CSV parsing. Each loader returns a list of
the relevant model objects so the rest of the engine never touches raw
rows or DataFrames.
"""

from __future__ import annotations

import os
from typing import List

import pandas as pd

from models import Worker, Task, HUMAN, AI_AGENT


def _split_skills(raw: str) -> List[str]:
    """Turn a ``A|B|C`` skills string into ``['A', 'B', 'C']``."""
    if not isinstance(raw, str):
        return []
    return [part.strip() for part in raw.split("|") if part.strip()]


def load_employees(path: str) -> List[Worker]:
    """Load human employees from ``employees.csv``."""
    df = pd.read_csv(path)
    workers: List[Worker] = []
    for _, row in df.iterrows():
        workers.append(
            Worker(
                name=str(row["name"]).strip(),
                type=HUMAN,
                role=str(row["role"]).strip(),
                skills=_split_skills(row["skills"]),
                capacity_hours=float(row["capacity_hours"]),
                workload_hours=float(row["workload_hours"]),
                cost_rate=float(row["cost_rate"]),
                quality_score=float(row["quality_score"]),
                speed_multiplier=1.0,  # humans always work at 1x
            )
        )
    return workers


def load_ai_agents(path: str) -> List[Worker]:
    """Load AI agents from ``ai_agents.csv``.

    AI agents have no pre-existing workload (workload_hours = 0) and use
    the ``speed_multiplier`` from the data.
    """
    df = pd.read_csv(path)
    workers: List[Worker] = []
    for _, row in df.iterrows():
        workers.append(
            Worker(
                name=str(row["name"]).strip(),
                type=AI_AGENT,
                role=str(row["agent_type"]).strip(),
                skills=_split_skills(row["capabilities"]),
                capacity_hours=float(row["capacity_hours"]),
                workload_hours=0.0,
                cost_rate=float(row["cost_rate"]),
                quality_score=float(row["quality_score"]),
                speed_multiplier=float(row["speed_multiplier"]),
            )
        )
    return workers


def _parse_bool(raw) -> bool:
    """Interpret a CSV truthy value (``true``/``1``/``yes``) as a bool."""
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"true", "1", "yes", "y"}


def _split_dependencies(raw) -> List[str]:
    """Parse the ``dependency_ids`` column into a list of task names."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def load_tasks(path: str) -> List[Task]:
    """Load project tasks from ``project_tasks.csv``.

    Supports the dependency and required/optional columns added in v2.
    These columns are optional: if a CSV omits them, tasks default to no
    dependencies and ``is_required = True`` so older data still loads.
    """
    df = pd.read_csv(path)
    tasks: List[Task] = []
    for _, row in df.iterrows():
        dependencies = (
            _split_dependencies(row["dependency_ids"])
            if "dependency_ids" in df.columns
            else []
        )
        is_required = (
            _parse_bool(row["is_required"]) if "is_required" in df.columns else True
        )
        tasks.append(
            Task(
                task=str(row["task"]).strip(),
                required_skill=str(row["required_skill"]).strip(),
                effort_hours=float(row["effort_hours"]),
                priority=int(row["priority"]),
                dependencies=dependencies,
                is_required=is_required,
            )
        )
    return tasks


def load_all(data_dir: str):
    """Convenience loader returning ``(employees, ai_agents, tasks)``."""
    employees = load_employees(os.path.join(data_dir, "employees.csv"))
    ai_agents = load_ai_agents(os.path.join(data_dir, "ai_agents.csv"))
    tasks = load_tasks(os.path.join(data_dir, "project_tasks.csv"))
    return employees, ai_agents, tasks
