"""Pareto-front preview over the Project Mode staffing options.

Given the staffing options Project Mode already produces (Current Team,
AI-Assisted, Recommended Balanced, Fastest, Lowest-Cost), this module marks
which options are **non-dominated** ("Pareto-optimal") across ten objectives.

An option *A dominates* option *B* when A is at least as good as B on **every**
objective and strictly better on **at least one**. An option is Pareto-optimal
when nothing dominates it - i.e. you cannot improve any objective without giving
up another. This is a read-only, explanatory view: it does NOT re-rank options,
change the recommendation, or touch scoring/routing. Everything here is
deterministic - pure comparisons over numbers already computed elsewhere.

The ten objectives (and their direction):

* minimize:  duration, cost, human hours, review hours, expected rework hours,
  risk
* maximize:  skill coverage, productivity, workload balance, delivery confidence
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


# (key, direction, human label, tradeoff phrase used when this option is best).
# ``direction`` is "min" (lower is better) or "max" (higher is better).
OBJECTIVES = [
    ("duration", "min", "duration", "fastest"),
    ("cost", "min", "cost", "lowest cost"),
    ("human_hours", "min", "human hours", "least human effort"),
    ("review_hours", "min", "review hours", "least review burden"),
    ("rework_hours", "min", "expected rework hours", "least rework"),
    ("risk", "min", "risk", "lowest risk"),
    ("skill_coverage", "max", "skill coverage", "best skill coverage"),
    ("productivity", "max", "productivity", "most productive"),
    ("workload_balance", "max", "workload balance", "most balanced"),
    ("confidence", "max", "delivery confidence", "highest delivery confidence"),
]

_DIRECTION = {key: direction for key, direction, _l, _p in OBJECTIVES}
_LABEL = {key: label for key, _d, label, _p in OBJECTIVES}
_PHRASE = {key: phrase for key, _d, _l, phrase in OBJECTIVES}


@dataclass
class ParetoOption:
    """One staffing option's place on (or off) the Pareto frontier."""

    option_id: str
    option_name: str
    is_pareto_optimal: bool
    dominated_by: List[str]
    dominates: List[str]
    tradeoff_summary: str
    objective_values: Dict[str, float]
    strengths: List[str]
    weaknesses: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


def objective_values(result, burden: dict) -> Dict[str, float]:
    """Extract the ten objective values for one option from existing outputs.

    ``result`` is a ``SimulationResult``; ``burden`` is the reviewer-burden dict
    Project Mode already computes for that option. No new simulation is run.
    """
    human_names = {w.name for w in result.team.humans}
    human_hours = round(
        sum(v for name, v in result.member_hours.items() if name in human_names), 2
    )
    return {
        "duration": float(result.estimated_duration),
        "cost": float(result.estimated_cost),
        "human_hours": float(human_hours),
        "review_hours": float(burden.get("review_burden_hours", 0.0)),
        "rework_hours": float(burden.get("expected_rework_hours", 0.0)),
        "risk": float(result.risk_score),
        "skill_coverage": float(result.required_skill_coverage_score),
        "productivity": float(result.productivity_score),
        "workload_balance": float(result.workload_balance_score),
        "confidence": float(result.confidence_score),
    }


def _better_or_equal(a: float, b: float, direction: str) -> bool:
    return a <= b if direction == "min" else a >= b


def _strictly_better(a: float, b: float, direction: str) -> bool:
    return a < b if direction == "min" else a > b


def dominates(a: Dict[str, float], b: Dict[str, float]) -> bool:
    """True when option values ``a`` dominate ``b``.

    Better-or-equal on every objective and strictly better on at least one.
    """
    strictly = False
    for key, direction, _l, _p in OBJECTIVES:
        if not _better_or_equal(a[key], b[key], direction):
            return False
        if _strictly_better(a[key], b[key], direction):
            strictly = True
    return strictly


def _extremes(all_values: List[Dict[str, float]]) -> Dict[str, tuple]:
    """Best and worst value per objective across all options (for strengths)."""
    extremes = {}
    for key, direction, _l, _p in OBJECTIVES:
        vals = [v[key] for v in all_values]
        if direction == "min":
            extremes[key] = (min(vals), max(vals))  # (best, worst)
        else:
            extremes[key] = (max(vals), min(vals))
    return extremes


def _strengths_weaknesses(values, extremes) -> tuple:
    """Objectives where this option is the best / worst (only when it matters).

    An objective is only a differentiator when options actually differ on it
    (best != worst); otherwise it is skipped for both strengths and weaknesses.
    """
    strengths, weaknesses = [], []
    for key, _d, label, _p in OBJECTIVES:
        best, worst = extremes[key]
        if best == worst:
            continue  # no spread - not a differentiator
        if values[key] == best:
            strengths.append(label)
        elif values[key] == worst:
            weaknesses.append(label)
    return strengths, weaknesses


def _tradeoff_summary(values, extremes, is_optimal, dominated_by_names) -> str:
    """Deterministic phrase describing what tradeoff this option represents."""
    if not is_optimal:
        if dominated_by_names:
            return (
                "Dominated by " + ", ".join(dominated_by_names)
                + " - another option is better or equal on every objective."
            )
        return "Not on the tradeoff frontier."
    # Best-in-class objectives become the option's tradeoff identity.
    phrases = []
    for key, _d, _l, phrase in OBJECTIVES:
        best, worst = extremes[key]
        if best != worst and values[key] == best:
            phrases.append(phrase)
    if not phrases:
        return "On the frontier: balanced across objectives with no single weak spot."
    return "On the frontier: " + ", ".join(phrases) + "."


def build_pareto_front(options: Dict[str, object], burdens: Dict[str, dict],
                       labels: Dict[str, str]) -> List[ParetoOption]:
    """Build a ``ParetoOption`` for every staffing option, in ``options`` order.

    ``options`` maps option_id -> SimulationResult; ``burdens`` maps option_id ->
    reviewer-burden dict; ``labels`` maps option_id -> display name.
    """
    keys = list(options.keys())
    values = {k: objective_values(options[k], burdens[k]) for k in keys}
    extremes = _extremes([values[k] for k in keys])

    pareto: List[ParetoOption] = []
    for k in keys:
        dominated_by = [
            o for o in keys if o != k and dominates(values[o], values[k])
        ]
        dominates_list = [
            o for o in keys if o != k and dominates(values[k], values[o])
        ]
        is_optimal = not dominated_by
        strengths, weaknesses = _strengths_weaknesses(values[k], extremes)
        summary = _tradeoff_summary(
            values[k], extremes, is_optimal,
            [labels[o] for o in dominated_by],
        )
        pareto.append(ParetoOption(
            option_id=k,
            option_name=labels[k],
            is_pareto_optimal=is_optimal,
            dominated_by=dominated_by,
            dominates=dominates_list,
            tradeoff_summary=summary,
            objective_values=values[k],
            strengths=strengths,
            weaknesses=weaknesses,
        ))
    return pareto


def explain(pareto: List[ParetoOption], recommended_option_id: str,
            labels: Dict[str, str]) -> str:
    """Deterministic paragraph describing the frontier (+ recommendation note)."""
    optimal = [p for p in pareto if p.is_pareto_optimal]
    optimal_names = ", ".join(p.option_name for p in optimal) or "none"
    parts = [
        f"{len(optimal)} of {len(pareto)} staffing options are Pareto-optimal "
        f"(non-dominated across {len(OBJECTIVES)} objectives): {optimal_names}."
    ]
    rec = next((p for p in pareto if p.option_id == recommended_option_id), None)
    if rec is not None:
        rec_name = labels.get(recommended_option_id, recommended_option_id)
        if rec.is_pareto_optimal:
            parts.append(
                f"The recommended option ({rec_name}) is on the frontier, so it "
                "is not dominated by any alternative."
            )
        else:
            dom = ", ".join(labels.get(o, o) for o in rec.dominated_by)
            parts.append(
                f"WARNING: the recommended option ({rec_name}) is NOT Pareto-"
                f"optimal - it is dominated by {dom}. The recommendation is "
                "unchanged (it best fits the chosen objective), but a "
                "dominating option improves some metrics at no cost to others."
            )
    parts.append(
        "This tradeoff view is informational only and does not change the "
        "recommendation or any score."
    )
    return " ".join(parts)


def pareto_preview(options: Dict[str, object], burdens: Dict[str, dict],
                   labels: Dict[str, str], recommended_option_id: str) -> dict:
    """Return ``{"pareto_front": [...], "pareto_explanation": str}``."""
    front = build_pareto_front(options, burdens, labels)
    return {
        "pareto_front": [p.to_dict() for p in front],
        "pareto_explanation": explain(front, recommended_option_id, labels),
    }
