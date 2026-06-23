"""Pydantic request/response schemas for the API.

These describe the JSON shapes the API accepts and returns, and provide
clear validation errors (negative weights, impossible team constraints,
etc.). They are deliberately separate from the engine's internal dataclasses
in ``models.py`` so the wire format can evolve independently.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Data entities
# ---------------------------------------------------------------------------

class Employee(BaseModel):
    """A human employee as returned by ``GET /employees``."""

    name: str
    type: str = "human"
    role: str
    skills: List[str]
    capacity_hours: float
    workload_hours: float
    available_hours: float
    cost_rate: float
    quality_score: float
    speed_multiplier: float = 1.0


class AIAgent(BaseModel):
    """An AI agent as returned by ``GET /ai-agents``."""

    name: str
    type: str = "ai_agent"
    agent_type: str
    capabilities: List[str]
    capacity_hours: float
    workload_hours: float
    available_hours: float
    cost_rate: float
    quality_score: float
    speed_multiplier: float


class ProjectTask(BaseModel):
    """A project task as returned by ``GET /tasks``."""

    task: str
    required_skill: str
    effort_hours: float
    priority: int
    dependencies: List[str] = Field(default_factory=list)
    is_required: bool = True


# ---------------------------------------------------------------------------
# Scoring config
# ---------------------------------------------------------------------------

# The weight keys the engine understands.
WEIGHT_KEYS = (
    "skill_coverage",
    "capacity_fit",
    "productivity",
    "workload_balance",
    "cost_efficiency",
    "low_risk",
)


class ScoringConfig(BaseModel):
    """Scoring weights + team constraints (``GET``/``POST /config``).

    Weights are on any relative scale (the defaults sum to 100) and must be
    non-negative with a positive total. Team-size constraints must be
    non-negative and have ``min <= max``; at least one human is required.
    """

    weights: Dict[str, float]
    require_full_required_skill_coverage: bool = True
    min_humans_per_team: int = 2
    max_humans_per_team: int = 5
    min_ai_agents_per_team: int = 0
    max_ai_agents_per_team: int = 2

    @field_validator("weights")
    @classmethod
    def _check_weights(cls, value: Dict[str, float]) -> Dict[str, float]:
        unknown = set(value) - set(WEIGHT_KEYS)
        if unknown:
            raise ValueError(
                f"Unknown weight key(s): {sorted(unknown)}. "
                f"Allowed keys: {list(WEIGHT_KEYS)}"
            )
        missing = set(WEIGHT_KEYS) - set(value)
        if missing:
            raise ValueError(f"Missing weight key(s): {sorted(missing)}")
        for key, weight in value.items():
            if weight < 0:
                raise ValueError(f"Weight '{key}' must be non-negative (got {weight})")
        if sum(value.values()) <= 0:
            raise ValueError("Weights must sum to a positive number")
        return value

    @model_validator(mode="after")
    def _check_constraints(self) -> "ScoringConfig":
        if self.min_humans_per_team < 1:
            raise ValueError("min_humans_per_team must be at least 1")
        if self.min_ai_agents_per_team < 0:
            raise ValueError("min_ai_agents_per_team must be non-negative")
        if self.max_humans_per_team < self.min_humans_per_team:
            raise ValueError(
                "max_humans_per_team must be >= min_humans_per_team "
                f"({self.max_humans_per_team} < {self.min_humans_per_team})"
            )
        if self.max_ai_agents_per_team < self.min_ai_agents_per_team:
            raise ValueError(
                "max_ai_agents_per_team must be >= min_ai_agents_per_team "
                f"({self.max_ai_agents_per_team} < {self.min_ai_agents_per_team})"
            )
        return self


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

class ManualTeamRequest(BaseModel):
    """Body for ``POST /simulate/manual-team``."""

    human_names: List[str] = Field(default_factory=list)
    ai_agent_names: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _at_least_one(self) -> "ManualTeamRequest":
        if not self.human_names and not self.ai_agent_names:
            raise ValueError(
                "Provide at least one human or AI agent name for the team"
            )
        return self


class TaskScheduleItem(BaseModel):
    """One task's slot in the computed schedule."""

    task: str
    assigned_to: Optional[str] = None
    required_skill: str
    effort_hours: float
    adjusted_effort_hours: float
    start_time: Optional[float] = None
    finish_time: Optional[float] = None
    dependencies: List[str] = Field(default_factory=list)
    is_on_critical_path: bool = False


class SimulationResult(BaseModel):
    """A single ranked team result (matches ``exporter.result_to_dict``)."""

    rank: int
    team_members: List[str]
    ai_agents: List[str]
    is_valid_team: bool
    invalid_reasons: List[str]
    total_score: float
    skill_coverage_score: float
    required_skill_coverage_score: float
    optional_skill_coverage_score: float
    capacity_fit_score: float
    estimated_cost: float
    estimated_duration: float
    critical_path: List[str]
    workload_balance_score: float
    productivity_score: float
    cost_efficiency_score: float
    risk_score: float
    confidence_score: float
    missing_required_skills: List[str]
    missing_optional_skills: List[str]
    overloaded_members: List[str]
    task_schedule: List[TaskScheduleItem]
    task_assignments: List[Dict[str, Any]]
    plain_english_explanation: str


class HealthResponse(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Project Mode
# ---------------------------------------------------------------------------

OBJECTIVE_CHOICES = (
    "balanced",
    "fastest",
    "lowest_cost",
    "best_skill_coverage",
    "best_workload_balance",
    "lowest_risk",
)


class ProjectTaskInput(BaseModel):
    """A task supplied in a project scenario (not loaded from CSV).

    ``routing_scores`` optionally overrides the engine's derived 1-5
    suitability scores for the task-level human/AI routing layer.
    """

    task: str
    required_skill: str
    effort_hours: float = Field(gt=0)
    priority: int = 1
    dependencies: List[str] = Field(default_factory=list)
    is_required: bool = True
    routing_scores: Optional[Dict[str, int]] = None
    # Optional three-point estimate for Monte-Carlo uncertainty. When omitted,
    # the engine derives a band from ``effort_hours``.
    effort_optimistic: Optional[float] = Field(default=None, gt=0)
    effort_pessimistic: Optional[float] = Field(default=None, gt=0)
    # Optional descriptive fields used only by the (preview) prior matcher.
    description: Optional[str] = None
    expected_output: Optional[str] = None
    task_type: Optional[str] = None
    required_skills: Optional[List[str]] = None


class RouteTasksRequest(BaseModel):
    """Body for ``POST /route/tasks`` - routing only, no team needed."""

    tasks: List[ProjectTaskInput]

    @field_validator("tasks")
    @classmethod
    def _check_tasks(cls, value):
        if not value:
            raise ValueError("Provide at least one task.")
        return value


class MatchTasksRequest(BaseModel):
    """Body for ``POST /priors/match-tasks`` - prior matching preview."""

    tasks: List[ProjectTaskInput]

    @field_validator("tasks")
    @classmethod
    def _check_tasks(cls, value):
        if not value:
            raise ValueError("Provide at least one task.")
        return value


class UncertaintyRequest(BaseModel):
    """Body for ``POST /simulate/uncertainty`` (Monte-Carlo analysis)."""

    tasks: List[ProjectTaskInput]
    human_names: List[str] = Field(default_factory=list)
    ai_agent_names: List[str] = Field(default_factory=list)
    iterations: int = Field(default=500, ge=1, le=5000)
    seed: int = 42
    deadline_target_hours: Optional[float] = None
    budget_target: Optional[float] = None
    default_low_factor: float = Field(default=0.8, gt=0)
    default_high_factor: float = Field(default=1.5, gt=0)

    @field_validator("tasks")
    @classmethod
    def _check_tasks(cls, value):
        if not value:
            raise ValueError("Provide at least one task.")
        return value

    @model_validator(mode="after")
    def _check_team(self) -> "UncertaintyRequest":
        if not self.human_names and not self.ai_agent_names:
            raise ValueError("Select at least one team member.")
        return self


class TeamConstraints(BaseModel):
    """Optional per-request overrides for team-size limits."""

    min_humans_per_team: Optional[int] = None
    max_humans_per_team: Optional[int] = None
    min_ai_agents_per_team: Optional[int] = None
    max_ai_agents_per_team: Optional[int] = None


class ProjectScenarioRequest(BaseModel):
    """Body for ``POST /simulate/project``."""

    project_name: str = ""
    project_goal: str = ""
    deadline_target_hours: Optional[float] = None
    budget_target: Optional[float] = None
    optimization_objective: str = "balanced"
    team_constraints: Optional[TeamConstraints] = None
    tasks: List[ProjectTaskInput]
    current_team_human_names: List[str] = Field(default_factory=list)
    current_team_ai_agent_names: List[str] = Field(default_factory=list)

    @field_validator("optimization_objective")
    @classmethod
    def _check_objective(cls, value: str) -> str:
        if value not in OBJECTIVE_CHOICES:
            raise ValueError(
                f"optimization_objective must be one of {list(OBJECTIVE_CHOICES)}"
            )
        return value

    @field_validator("tasks")
    @classmethod
    def _check_tasks(cls, value):
        if not value:
            raise ValueError("Provide at least one task.")
        return value
