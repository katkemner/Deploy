"""Task-level human/AI routing layer.

Before scheduling, each task gets a deterministic recommendation for *how* it
should be done by humans vs AI:

* ``AI_ONLY``               - AI handles it end to end
* ``AI_FIRST_HUMAN_REVIEW`` - AI drafts, a human approves
* ``HUMAN_FIRST_AI_ASSIST`` - a human leads, AI accelerates parts
* ``HUMAN_ONLY``            - a human must own it
* ``ESCALATE``              - inputs missing / too uncertain to auto-route

The decision is driven by nine suitability scores (1-5 each). Scores are
derived deterministically from a per-skill profile table plus light task
attribute adjustments, and may be overridden per task. From the routing we
also estimate human **review hours** and expected **rework hours**, the AI
time saved, and (given a team) whether reviewers become a bottleneck.

Everything here is deterministic - pure formulas and the config constants
below. No LLM, randomness, or external calls.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Routing decisions
# ---------------------------------------------------------------------------

AI_ONLY = "AI_ONLY"
AI_FIRST_HUMAN_REVIEW = "AI_FIRST_HUMAN_REVIEW"
HUMAN_FIRST_AI_ASSIST = "HUMAN_FIRST_AI_ASSIST"
HUMAN_ONLY = "HUMAN_ONLY"
ESCALATE = "ESCALATE"

# The nine suitability scores (1-5). Higher = more of that quality.
SCORE_FIELDS = (
    "ai_capability_fit",
    "human_judgment_need",
    "verification_ease",
    "error_cost",
    "context_sensitivity",
    "repetition_level",
    "speed_value",
    "human_learning_value",
    "collaboration_value",
)


# ---------------------------------------------------------------------------
# Config weights / constants (tunable; deterministic)
# ---------------------------------------------------------------------------

# Fraction of a task done by AI, by routing decision. Drives rework and
# AI-time-saved estimates.
AI_INVOLVEMENT = {
    AI_ONLY: 1.0,
    AI_FIRST_HUMAN_REVIEW: 0.8,
    HUMAN_FIRST_AI_ASSIST: 0.4,
    HUMAN_ONLY: 0.0,
    ESCALATE: 0.0,
}

# Base human-review intensity (share of effort) by routing decision.
REVIEW_BASE = {
    AI_ONLY: 0.05,
    AI_FIRST_HUMAN_REVIEW: 0.30,
    HUMAN_FIRST_AI_ASSIST: 0.10,
    HUMAN_ONLY: 0.0,
    ESCALATE: 0.0,
}

REWORK_BASE = 0.6              # base rework intensity multiplier
AI_SPEED_FACTOR = 1.3          # assumed AI speed on its share of the work
REVIEW_BOTTLENECK_FRACTION = 0.35  # review hrs > this * human capacity = bottleneck


# Per-skill baseline suitability profiles (1-5). Unknown skills get no
# profile and route to ESCALATE unless scores are supplied explicitly.
SKILL_PROFILES: Dict[str, Dict[str, int]] = {
    # skill: ai_fit, judgment, verify, error, context, repetition, speed, learning, collab
    "research":      dict(ai_capability_fit=4, human_judgment_need=3, verification_ease=3, error_cost=2, context_sensitivity=3, repetition_level=3, speed_value=4, human_learning_value=3, collaboration_value=4),
    "market":        dict(ai_capability_fit=4, human_judgment_need=3, verification_ease=3, error_cost=2, context_sensitivity=3, repetition_level=3, speed_value=4, human_learning_value=3, collaboration_value=4),
    "data":          dict(ai_capability_fit=4, human_judgment_need=3, verification_ease=3, error_cost=3, context_sensitivity=3, repetition_level=4, speed_value=4, human_learning_value=2, collaboration_value=3),
    "writing":       dict(ai_capability_fit=5, human_judgment_need=2, verification_ease=4, error_cost=2, context_sensitivity=2, repetition_level=4, speed_value=4, human_learning_value=1, collaboration_value=3),
    "documentation": dict(ai_capability_fit=5, human_judgment_need=2, verification_ease=4, error_cost=2, context_sensitivity=2, repetition_level=4, speed_value=4, human_learning_value=1, collaboration_value=3),
    "qa":            dict(ai_capability_fit=4, human_judgment_need=2, verification_ease=4, error_cost=3, context_sensitivity=2, repetition_level=4, speed_value=4, human_learning_value=2, collaboration_value=3),
    "testing":       dict(ai_capability_fit=4, human_judgment_need=2, verification_ease=4, error_cost=3, context_sensitivity=2, repetition_level=4, speed_value=4, human_learning_value=2, collaboration_value=3),
    "automation":    dict(ai_capability_fit=4, human_judgment_need=2, verification_ease=4, error_cost=3, context_sensitivity=2, repetition_level=5, speed_value=4, human_learning_value=2, collaboration_value=3),
    "strategy":      dict(ai_capability_fit=2, human_judgment_need=5, verification_ease=2, error_cost=4, context_sensitivity=5, repetition_level=1, speed_value=2, human_learning_value=4, collaboration_value=3),
    "planning":      dict(ai_capability_fit=3, human_judgment_need=4, verification_ease=3, error_cost=3, context_sensitivity=4, repetition_level=2, speed_value=3, human_learning_value=3, collaboration_value=4),
    "scheduling":    dict(ai_capability_fit=4, human_judgment_need=3, verification_ease=4, error_cost=2, context_sensitivity=3, repetition_level=4, speed_value=4, human_learning_value=2, collaboration_value=3),
    "coordination":  dict(ai_capability_fit=2, human_judgment_need=4, verification_ease=3, error_cost=3, context_sensitivity=4, repetition_level=2, speed_value=3, human_learning_value=3, collaboration_value=4),
    "operations":    dict(ai_capability_fit=3, human_judgment_need=4, verification_ease=3, error_cost=3, context_sensitivity=4, repetition_level=3, speed_value=3, human_learning_value=3, collaboration_value=4),
    "ux":            dict(ai_capability_fit=2, human_judgment_need=4, verification_ease=3, error_cost=3, context_sensitivity=4, repetition_level=2, speed_value=2, human_learning_value=3, collaboration_value=4),
    "prototype":     dict(ai_capability_fit=3, human_judgment_need=4, verification_ease=3, error_cost=3, context_sensitivity=3, repetition_level=2, speed_value=3, human_learning_value=3, collaboration_value=4),
    "brand":         dict(ai_capability_fit=2, human_judgment_need=4, verification_ease=2, error_cost=3, context_sensitivity=4, repetition_level=2, speed_value=2, human_learning_value=3, collaboration_value=4),
    "react":         dict(ai_capability_fit=3, human_judgment_need=3, verification_ease=3, error_cost=4, context_sensitivity=3, repetition_level=2, speed_value=3, human_learning_value=3, collaboration_value=4),
    "api":           dict(ai_capability_fit=3, human_judgment_need=3, verification_ease=3, error_cost=4, context_sensitivity=3, repetition_level=2, speed_value=3, human_learning_value=3, collaboration_value=4),
    "database":      dict(ai_capability_fit=3, human_judgment_need=2, verification_ease=3, error_cost=3, context_sensitivity=2, repetition_level=3, speed_value=3, human_learning_value=2, collaboration_value=3),
    "python":        dict(ai_capability_fit=4, human_judgment_need=3, verification_ease=3, error_cost=3, context_sensitivity=3, repetition_level=3, speed_value=4, human_learning_value=3, collaboration_value=4),
}


# ---------------------------------------------------------------------------
# Score derivation
# ---------------------------------------------------------------------------

def _clamp_score(v: int) -> int:
    return max(1, min(5, int(round(v))))


def derive_scores(task) -> (Optional[Dict[str, int]], bool):
    """Return (scores, has_profile) for a task.

    Scores come from an explicit per-task override (``task.routing_scores`` or a
    dict key) when provided, otherwise from the skill profile table with small
    deterministic adjustments for required/optional and priority. Returns
    ``(None, False)`` when no profile or override exists - the caller routes
    such tasks to ESCALATE.
    """
    overrides = _get_attr(task, "routing_scores", None)
    skill = str(_get_attr(task, "required_skill", "")).strip().lower()
    is_required = bool(_get_attr(task, "is_required", True))
    priority = int(_get_attr(task, "priority", 1) or 1)

    if overrides:
        scores = {f: _clamp_score(overrides.get(f, 3)) for f in SCORE_FIELDS}
        return scores, True

    profile = SKILL_PROFILES.get(skill)
    if profile is None:
        return None, False

    scores = dict(profile)
    # Optional work carries less error cost; top-priority work values speed more.
    if not is_required:
        scores["error_cost"] = _clamp_score(scores["error_cost"] - 1)
    if priority == 1:
        scores["speed_value"] = _clamp_score(scores["speed_value"] + 1)
    return scores, True


def _get_attr(obj, name, default):
    """Read ``name`` from either an object attribute or a dict key."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


# ---------------------------------------------------------------------------
# Routing decision
# ---------------------------------------------------------------------------

def _composites(s: Dict[str, int]):
    """Two 1-5 axes used for the uncertainty check."""
    ai_leverage = (
        s["ai_capability_fit"] + s["repetition_level"]
        + s["verification_ease"] + s["speed_value"]
    ) / 4.0
    human_criticality = (
        s["human_judgment_need"] + s["error_cost"]
        + s["context_sensitivity"] + (6 - s["verification_ease"])
    ) / 4.0
    return ai_leverage, human_criticality


def decide_route(scores: Optional[Dict[str, int]], has_profile: bool):
    """Return ``(decision, explanation)`` for a task's scores.

    Rules are evaluated in order: ESCALATE (missing/uncertain), AI_ONLY,
    HUMAN_ONLY, AI_FIRST_HUMAN_REVIEW, then HUMAN_FIRST_AI_ASSIST as the
    default middle ground.
    """
    if not has_profile or scores is None:
        return ESCALATE, (
            "No skill profile or supplied scores for this task, so routing is "
            "uncertain - escalate for a human to set the approach."
        )

    s = scores
    ai_lev, hum_crit = _composites(s)

    # Too uncertain: everything middling and the two axes are close.
    if abs(ai_lev - hum_crit) < 0.4 and 2.5 <= ai_lev <= 3.5 and 2.5 <= hum_crit <= 3.5:
        return ESCALATE, (
            f"AI leverage ({ai_lev:.1f}) and human criticality ({hum_crit:.1f}) "
            "are both middling and close, so the routing call is too uncertain."
        )

    # AI_ONLY: strong, verifiable, low-stakes, repetitive.
    if (
        s["ai_capability_fit"] >= 4
        and s["repetition_level"] >= 4
        and s["verification_ease"] >= 4
        and s["human_judgment_need"] <= 2
        and s["error_cost"] <= 2
    ):
        return AI_ONLY, (
            "High AI capability and repetition with easy verification, low "
            "judgment need, and low error cost - AI can own this end to end."
        )

    # HUMAN_ONLY: two or more strong human-ownership signals.
    signals = []
    if s["error_cost"] >= 4:
        signals.append("high error cost")
    if s["verification_ease"] <= 2:
        signals.append("hard to verify")
    if s["context_sensitivity"] >= 4:
        signals.append("high context sensitivity")
    if s["human_judgment_need"] >= 5:
        signals.append("heavy human judgment")
    if len(signals) >= 2:
        return HUMAN_ONLY, (
            "A human must own this (" + ", ".join(signals) + ")."
        )

    # AI_FIRST_HUMAN_REVIEW: AI fit high and verifiable, but approval adds value.
    if (
        s["ai_capability_fit"] >= 4
        and s["verification_ease"] >= 3
        and s["error_cost"] <= 3
        and s["human_judgment_need"] <= 3
    ):
        return AI_FIRST_HUMAN_REVIEW, (
            "Strong AI fit with verifiable output, but a human review/approval "
            "step is still worthwhile given the error cost."
        )

    # Default: human leads, AI accelerates.
    return HUMAN_FIRST_AI_ASSIST, (
        "Human judgment leads; AI can accelerate research, drafting, analysis, "
        "QA, or formatting underneath."
    )


# ---------------------------------------------------------------------------
# Hour estimates
# ---------------------------------------------------------------------------

def estimate_review_hours(decision: str, s: Dict[str, int], effort: float) -> float:
    """Human review hours: scales with error cost and how hard it is to verify."""
    base = REVIEW_BASE.get(decision, 0.0)
    if base <= 0 or not s:
        return 0.0
    err, ver = s["error_cost"], s["verification_ease"]
    intensity = base * (0.5 + 0.5 * (err / 5.0)) * (0.5 + 0.5 * ((6 - ver) / 5.0))
    return round(effort * intensity, 2)


def estimate_rework_hours(decision: str, s: Dict[str, int], effort: float) -> float:
    """Expected rework hours from AI errors needing fixing."""
    frac = AI_INVOLVEMENT.get(decision, 0.0)
    if frac <= 0 or not s:
        return 0.0
    err, ver, fit = s["error_cost"], s["verification_ease"], s["ai_capability_fit"]
    intensity = REWORK_BASE * (err / 5.0) * ((6 - ver) / 5.0) * ((6 - fit) / 5.0)
    return round(effort * frac * intensity, 2)


def estimate_ai_time_saved(decision: str, effort: float) -> float:
    """Raw hours saved by AI doing its share faster (before review/rework)."""
    frac = AI_INVOLVEMENT.get(decision, 0.0)
    if frac <= 0:
        return 0.0
    return round(effort * frac * (1.0 - 1.0 / AI_SPEED_FACTOR), 2)


# ---------------------------------------------------------------------------
# Per-task and project-level routing
# ---------------------------------------------------------------------------

def route_task(task) -> dict:
    """Produce the full routing record for one task."""
    scores, has_profile = derive_scores(task)
    decision, explanation = decide_route(scores, has_profile)
    effort = float(_get_attr(task, "effort_hours", 0) or 0)
    review = estimate_review_hours(decision, scores or {}, effort)
    rework = estimate_rework_hours(decision, scores or {}, effort)
    saved = estimate_ai_time_saved(decision, effort)
    return {
        "task": _get_attr(task, "task", ""),
        "required_skill": _get_attr(task, "required_skill", ""),
        "effort_hours": effort,
        "routing": decision,
        "scores": scores or {f: None for f in SCORE_FIELDS},
        "explanation": explanation,
        "review_hours": review,
        "expected_rework_hours": rework,
        "ai_time_saved": saved,
        "ai_involvement_fraction": AI_INVOLVEMENT.get(decision, 0.0),
    }


def route_tasks(tasks) -> List[dict]:
    """Routing records for every task, preserving order."""
    return [route_task(t) for t in tasks]


def summarize_routing(records: List[dict]) -> dict:
    """Project-level totals and routing distribution."""
    total_review = round(sum(r["review_hours"] for r in records), 2)
    total_rework = round(sum(r["expected_rework_hours"] for r in records), 2)
    total_saved = round(sum(r["ai_time_saved"] for r in records), 2)
    net = round(total_saved - total_review - total_rework, 2)
    distribution = dict(Counter(r["routing"] for r in records))
    return {
        "total_review_hours": total_review,
        "total_expected_rework_hours": total_rework,
        "total_ai_time_saved": total_saved,
        "net_ai_time_saved": net,
        "routing_distribution": distribution,
        "ai_saves_time": net > 0,
    }


def reviewer_burden_for_team(
    records: List[dict], human_workers: List, has_ai: bool
) -> dict:
    """Review/rework burden and reviewer-bottleneck check for one team.

    When the team has no AI agents it cannot follow AI routings, so there is no
    AI review burden (humans do the work directly). When it does have AI, the
    project's review/rework totals apply and we check them against the team's
    human reviewing capacity.
    """
    if not has_ai:
        return {
            "review_burden_hours": 0.0,
            "expected_rework_hours": 0.0,
            "ai_time_saved": 0.0,
            "net_time_saved": 0.0,
            "reviewer_bottleneck": {
                "is_bottleneck": False,
                "review_hours": 0.0,
                "human_capacity_hours": round(
                    sum(w.available_hours for w in human_workers), 2
                ),
                "message": (
                    "No AI agents on this team, so there is no AI review "
                    "burden - humans do the work directly."
                ),
            },
        }

    summary = summarize_routing(records)
    review = summary["total_review_hours"]
    rework = summary["total_expected_rework_hours"]
    saved = summary["total_ai_time_saved"]
    capacity = round(sum(w.available_hours for w in human_workers), 2)
    n_humans = len(human_workers)
    per_reviewer = round(review / n_humans, 2) if n_humans else review
    is_bottleneck = capacity > 0 and review > REVIEW_BOTTLENECK_FRACTION * capacity

    if n_humans == 0:
        message = (
            f"This team has AI but no humans to review {review:.1f}h of AI "
            "output - reviewers are a hard bottleneck."
        )
        is_bottleneck = True
    elif is_bottleneck:
        message = (
            f"Review burden ({review:.1f}h, ~{per_reviewer:.1f}h per reviewer) "
            f"exceeds {int(REVIEW_BOTTLENECK_FRACTION * 100)}% of the team's "
            f"{capacity:.0f}h human capacity - reviewers are a bottleneck."
        )
    else:
        message = (
            f"Review burden ({review:.1f}h) fits within the team's "
            f"{capacity:.0f}h human capacity."
        )

    return {
        "review_burden_hours": review,
        "expected_rework_hours": rework,
        "ai_time_saved": saved,
        "net_time_saved": round(saved - review - rework, 2),
        "reviewer_bottleneck": {
            "is_bottleneck": is_bottleneck,
            "review_hours": review,
            "human_capacity_hours": capacity,
            "per_reviewer_hours": per_reviewer,
            "message": message,
        },
    }
