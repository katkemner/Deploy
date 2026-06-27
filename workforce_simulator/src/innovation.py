"""Deterministic innovation scoring for a staffing option (no LLM).

``innovation_score`` (0-100) rates how well a candidate team could produce
*innovative outputs on the actual project* - not a generic capability tag count.
It deliberately still uses the project's real tasks, required skills, coverage,
overload, bottlenecks, workload slack, and the routing review/rework + AI net
benefit. Innovation-capability tags are one lens among nine, not the whole
score.

Capability tags are treated as **team skill-coverage signals only** - never as
claims that a person "is creative" or "is curious". A team simply has, or lacks,
the skills associated with each capability.

Pure formulas; the existing scorer, weights, and routing rules are untouched.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

# The ten innovation capability tags (team skill-coverage signals).
INNOVATION_TAGS = (
    "innovation",
    "creative_thinking",
    "analytical_thinking",
    "curiosity",
    "lifelong_learning",
    "resilience",
    "agility",
    "systems_thinking",
    "leadership_social_influence",
    "technological_literacy",
)

# Component weights (sum to 100). innovation_score is their weighted average.
WEIGHTS = {
    "project_fit_guardrail_score": 25,
    "cross_functional_mix_score": 15,
    "innovation_capability_coverage_score": 15,
    "exploration_customer_insight_score": 10,
    "prototype_build_capability_score": 10,
    "validation_learning_loop_score": 10,
    "slack_workload_balance_score": 7,
    "launch_adoption_capability_score": 5,
    "ai_augmentation_leverage_score": 3,
}

# Per-skill profile: which capability tags the skill covers, its functional area
# (for cross-functional mix), and which innovation phases it supports. Mirrors
# the spirit of the routing suitability sheet - a deterministic, auditable table.
_DEFAULT = {"tags": frozenset(), "function": "general", "phases": frozenset()}
SKILL_PROFILE: Dict[str, dict] = {
    "research":      {"tags": {"curiosity", "analytical_thinking", "lifelong_learning"}, "function": "research", "phases": {"exploration", "validation"}},
    "market":        {"tags": {"curiosity", "analytical_thinking"}, "function": "research", "phases": {"exploration"}},
    "data":          {"tags": {"analytical_thinking", "systems_thinking", "technological_literacy"}, "function": "data", "phases": {"exploration", "validation"}},
    "strategy":      {"tags": {"systems_thinking", "analytical_thinking", "leadership_social_influence"}, "function": "product", "phases": {"exploration"}},
    "planning":      {"tags": {"systems_thinking", "leadership_social_influence", "agility"}, "function": "product", "phases": {"launch"}},
    "coordination":  {"tags": {"leadership_social_influence", "agility"}, "function": "ops", "phases": {"launch"}},
    "operations":    {"tags": {"systems_thinking", "leadership_social_influence", "resilience"}, "function": "ops", "phases": {"launch"}},
    "scheduling":    {"tags": {"systems_thinking", "agility"}, "function": "ops", "phases": set()},
    "ux":            {"tags": {"creative_thinking", "innovation", "curiosity"}, "function": "design", "phases": {"exploration", "prototype"}},
    "prototype":     {"tags": {"creative_thinking", "innovation", "agility", "technological_literacy"}, "function": "design", "phases": {"prototype"}},
    "brand":         {"tags": {"creative_thinking", "innovation"}, "function": "design", "phases": {"launch"}},
    "python":        {"tags": {"technological_literacy", "analytical_thinking"}, "function": "engineering", "phases": {"prototype"}},
    "react":         {"tags": {"technological_literacy", "creative_thinking"}, "function": "engineering", "phases": {"prototype"}},
    "api":           {"tags": {"technological_literacy", "systems_thinking"}, "function": "engineering", "phases": {"prototype"}},
    "database":      {"tags": {"technological_literacy", "systems_thinking"}, "function": "engineering", "phases": {"prototype"}},
    "automation":    {"tags": {"technological_literacy", "agility", "resilience"}, "function": "engineering", "phases": {"prototype", "validation"}},
    "qa":            {"tags": {"analytical_thinking", "resilience"}, "function": "quality", "phases": {"validation"}},
    "testing":       {"tags": {"analytical_thinking", "resilience"}, "function": "quality", "phases": {"validation"}},
    "writing":       {"tags": {"creative_thinking", "lifelong_learning"}, "function": "content", "phases": {"launch"}},
    "documentation": {"tags": {"lifelong_learning", "technological_literacy"}, "function": "content", "phases": {"launch"}},
}


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def _human_skills(result) -> set:
    """Lower-cased skills across the HUMANS on the team (innovation = people)."""
    skills = set()
    for h in result.team.humans:
        for s in h.skills:
            skills.add(s.strip().lower())
    return skills


def _team_capabilities(human_skills: set) -> Tuple[set, set, set]:
    caps, funcs, phases = set(), set(), set()
    for sk in human_skills:
        prof = SKILL_PROFILE.get(sk, _DEFAULT)
        caps |= set(prof["tags"])
        funcs.add(prof["function"])
        phases |= set(prof["phases"])
    return caps, funcs, phases


# ---------------------------------------------------------------------------
# Components (each 0-100)
# ---------------------------------------------------------------------------

def _project_fit_guardrail(result) -> float:
    """Does the team actually fit THIS project? Guards against unfit "innovators".

    Driven by the project's real required-skill coverage, member overload, and
    single-bottleneck concentration - all from the existing simulation result.
    """
    base = result.required_skill_coverage_score
    members = result.team.members
    overload_frac = (len(result.overloaded_members) / len(members)) if members else 0.0
    mh = result.member_hours or {}
    total = sum(mh.values()) or 1.0
    max_share = (max(mh.values()) / total) if mh else 0.0
    # One person carrying >50% of the work is a fragile bottleneck.
    bottleneck_pen = max(0.0, max_share - 0.5) / 0.5 * 40.0
    return _clamp(base - 50.0 * overload_frac - bottleneck_pen)


def _cross_functional_mix(funcs: set, project_functions: set) -> float:
    """Reward a diverse, cross-disciplinary human team covering project areas."""
    if project_functions:
        coverage = len(funcs & project_functions) / len(project_functions)
    else:
        coverage = 1.0
    breadth = min(1.0, len(funcs) / 5.0)  # spanning ~5 disciplines is very diverse
    return _clamp(100.0 * (0.7 * coverage + 0.3 * breadth))


def _capability_coverage(caps: set) -> float:
    return 100.0 * len(caps & set(INNOVATION_TAGS)) / len(INNOVATION_TAGS)


def _phase_score(result, tasks_by_phase, phase: str, team_phases: set) -> float:
    """How well HUMANS cover this innovation phase on the actual project.

    Counts the project's phase tasks done by a human (novel work comes from
    people, so AI-owned tasks don't count toward the creative phases). When the
    project has no tasks in this phase, falls back to latent human capability.
    """
    items = tasks_by_phase.get(phase, [])
    if items:
        covered = sum(
            1 for a in items
            if a.assigned_type == "human" and not a.missing_skill
        )
        return 100.0 * covered / len(items)
    return 100.0 if phase in team_phases else 50.0


def _slack_workload_balance(result) -> float:
    """Even workload + spare capacity to explore (both from the simulation)."""
    bal = result.workload_balance_score
    spares = []
    for w in result.team.members:
        avail = w.available_hours
        used = (result.member_hours or {}).get(w.name, 0.0)
        if avail > 0:
            spares.append(max(0.0, 1.0 - used / avail))
    slack = (sum(spares) / len(spares) * 100.0) if spares else 0.0
    return _clamp(0.6 * bal + 0.4 * slack)


def _ai_augmentation_leverage(burden: dict) -> float:
    """Reward AI that genuinely frees humans (positive net), penalise churn."""
    saved = burden.get("ai_time_saved", 0.0)
    if saved <= 0:
        return 50.0  # no AI used -> neutral
    ratio = burden.get("net_time_saved", 0.0) / saved  # <=1; negative if churny
    return _clamp(50.0 + 50.0 * ratio)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def score(result, routing_by_task: dict, burden: dict) -> Tuple[float, Dict[str, float]]:
    """Return ``(innovation_score, components)`` for one staffing option.

    ``routing_by_task`` is unused directly here (phase grouping comes from the
    assignments' skills) but is accepted for symmetry/future use. ``burden`` is
    the option's reviewer-burden dict (review/rework/net AI saved).
    """
    human_skills = _human_skills(result)
    caps, funcs, team_phases = _team_capabilities(human_skills)

    tasks_by_phase = defaultdict(list)
    project_functions = set()
    for a in result.assignments:
        prof = SKILL_PROFILE.get(a.required_skill.strip().lower(), _DEFAULT)
        project_functions.add(prof["function"])
        for ph in prof["phases"]:
            tasks_by_phase[ph].append(a)

    comp = {
        "project_fit_guardrail_score": _project_fit_guardrail(result),
        "cross_functional_mix_score": _cross_functional_mix(funcs, project_functions),
        "innovation_capability_coverage_score": _capability_coverage(caps),
        "exploration_customer_insight_score": _phase_score(result, tasks_by_phase, "exploration", team_phases),
        "prototype_build_capability_score": _phase_score(result, tasks_by_phase, "prototype", team_phases),
        "validation_learning_loop_score": _phase_score(result, tasks_by_phase, "validation", team_phases),
        "slack_workload_balance_score": _slack_workload_balance(result),
        "launch_adoption_capability_score": _phase_score(result, tasks_by_phase, "launch", team_phases),
        "ai_augmentation_leverage_score": _ai_augmentation_leverage(burden),
    }
    total = sum(comp[k] * WEIGHTS[k] for k in WEIGHTS) / 100.0
    return round(total, 2), {k: round(v, 1) for k, v in comp.items()}
