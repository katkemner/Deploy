"""Data models for the workforce simulator.

This module defines the core domain objects used throughout the
simulation:

* ``Worker`` - a person (human) or an AI agent. Both are treated as
  workers so the rest of the engine can reason about them uniformly.
* ``Task``   - a unit of project work that requires a single skill.
* ``Assignment`` - the record of a task being given to a worker.

The models are plain dataclasses with a few small helper methods. They
contain no scoring logic; scoring lives in ``scoring.py`` and the
assignment / metric logic lives in ``simulator.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# Worker "type" constants so we never sprinkle raw strings around.
HUMAN = "human"
AI_AGENT = "ai_agent"


@dataclass
class Worker:
    """A person or AI agent that can be assigned project tasks.

    Humans and AI agents share the same shape so the simulator can treat
    a mixed team uniformly. The differences:

    * Humans carry an existing ``workload_hours`` (work they are already
      committed to) and always have a ``speed_multiplier`` of ``1.0``.
    * AI agents start with no existing workload and have a
      ``speed_multiplier`` greater than ``1.0`` meaning they get the same
      work done in fewer effective hours.
    """

    name: str
    type: str                      # HUMAN or AI_AGENT
    role: str                      # role (human) or agent_type (ai agent)
    skills: List[str]              # skills (human) or capabilities (ai agent)
    capacity_hours: float
    workload_hours: float
    cost_rate: float
    quality_score: float           # 0-10 quality rating from the source data
    speed_multiplier: float = 1.0

    @property
    def available_hours(self) -> float:
        """Hours the worker can still take on (never negative)."""
        return max(0.0, self.capacity_hours - self.workload_hours)

    def has_skill(self, skill: str) -> bool:
        """Return True if the worker can perform ``skill``.

        Matching is case-insensitive so that data entry casing does not
        break assignment.
        """
        skill = skill.strip().lower()
        return any(s.strip().lower() == skill for s in self.skills)

    def effective_hours_for(self, effort_hours: float) -> float:
        """How many of *this worker's* hours ``effort_hours`` will consume.

        AI agents work faster, so a task that nominally needs
        ``effort_hours`` is completed in ``effort_hours / speed_multiplier``
        of their time. Humans (speed 1.0) consume the full effort.
        """
        return effort_hours / self.speed_multiplier


@dataclass
class Task:
    """A single piece of project work requiring one skill."""

    task: str
    required_skill: str
    effort_hours: float
    priority: int   # 1 == highest priority


@dataclass
class Assignment:
    """The result of giving a task to a worker (or failing to)."""

    task: str
    required_skill: str
    effort_hours: float
    priority: int
    assigned_to: Optional[str] = None     # worker name, or None if unassigned
    assigned_type: Optional[str] = None   # HUMAN / AI_AGENT, or None
    assigned_hours: float = 0.0           # hours consumed on the worker
    missing_skill: bool = False           # True when no worker had the skill

    def as_dict(self) -> dict:
        """Plain dict suitable for JSON / CSV export."""
        return {
            "task": self.task,
            "required_skill": self.required_skill,
            "priority": self.priority,
            "effort_hours": self.effort_hours,
            "assigned_to": self.assigned_to,
            "assigned_type": self.assigned_type,
            "assigned_hours": round(self.assigned_hours, 2),
            "missing_skill": self.missing_skill,
        }


@dataclass
class Team:
    """A candidate team made of humans and (optionally) AI agents."""

    humans: List[Worker] = field(default_factory=list)
    ai_agents: List[Worker] = field(default_factory=list)

    @property
    def members(self) -> List[Worker]:
        """All workers on the team (humans first, then AI agents)."""
        return list(self.humans) + list(self.ai_agents)

    @property
    def human_names(self) -> List[str]:
        return [w.name for w in self.humans]

    @property
    def ai_names(self) -> List[str]:
        return [w.name for w in self.ai_agents]

    def signature(self) -> tuple:
        """A hashable identity used to de-duplicate teams.

        Two teams with the same members (in any order) share a signature.
        """
        return (
            tuple(sorted(self.human_names)),
            tuple(sorted(self.ai_names)),
        )
