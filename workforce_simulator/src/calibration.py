"""Historical calibration scaffold.

Lets a user record the *actual* outcomes of a completed project and compare
them against what the simulator predicted. It computes error percentages,
flags the biggest misses, and **suggests** (never applies) multiplier updates
that a future calibration slice could use.

This is informational only: nothing here changes scoring, routing, or any
simulation, and no suggested multiplier is ever applied automatically. No ML,
LLM, external API, or database - actuals are kept in a small local JSON file.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import List, Optional


class CalibrationError(ValueError):
    """Raised for invalid actuals input (missing/negative required values)."""


# Numeric fields that must be present and non-negative on submitted actuals.
REQUIRED_NUMERIC_FIELDS = (
    "predicted_duration", "actual_duration",
    "predicted_cost", "actual_cost",
    "predicted_human_hours", "actual_human_hours",
    "predicted_review_hours", "actual_review_hours",
    "predicted_rework_hours", "actual_rework_hours",
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class HistoricalProjectActual:
    project_id: str
    project_name: str
    project_type: str
    predicted_duration: float
    actual_duration: float
    predicted_cost: float
    actual_cost: float
    predicted_human_hours: float
    actual_human_hours: float
    predicted_review_hours: float
    actual_review_hours: float
    predicted_rework_hours: float
    actual_rework_hours: float
    predicted_bottleneck: str = ""
    actual_bottleneck: str = ""
    original_simulation_id: Optional[str] = None
    predicted_quality_score: Optional[float] = None
    actual_quality_score: Optional[float] = None
    notes: str = ""


@dataclass
class SuggestedMultiplierUpdates:
    task_duration_multiplier: float
    review_time_multiplier: float
    rework_multiplier: float
    dependency_buffer_multiplier: float
    skill_gap_penalty: float
    context_switching_penalty: float


@dataclass
class CalibrationComparison:
    project_id: str
    duration_error_pct: Optional[float]
    cost_error_pct: Optional[float]
    human_hours_error_pct: Optional[float]
    review_hours_error_pct: Optional[float]
    rework_hours_error_pct: Optional[float]
    bottleneck_correct: bool
    suggested_multiplier_updates: SuggestedMultiplierUpdates
    explanation: str
    quality_error: Optional[float] = None
    applied: bool = False  # always False - suggestions are never auto-applied

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# Validation + helpers
# ---------------------------------------------------------------------------

def validate_actual(data: dict) -> None:
    """Validate a submitted actuals payload. Raises ``CalibrationError``."""
    if not isinstance(data, dict):
        raise CalibrationError("Actuals payload must be an object.")
    for key in ("project_id", "project_name", "project_type"):
        if not str(data.get(key, "")).strip():
            raise CalibrationError(f"Missing required field: {key}")
    for key in REQUIRED_NUMERIC_FIELDS:
        if key not in data or data[key] is None:
            raise CalibrationError(f"Missing required numeric field: {key}")
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CalibrationError(f"Field '{key}' must be numeric (got {value!r})")
        if value < 0:
            raise CalibrationError(f"Field '{key}' must be non-negative (got {value})")


def error_pct(predicted: float, actual: float) -> Optional[float]:
    """Signed percentage error of actual vs predicted, or None if predicted=0.

    Positive means the actual overran the prediction.
    """
    if predicted is None or actual is None or predicted == 0:
        return None
    return round((actual - predicted) / predicted * 100.0, 2)


def _ratio(predicted, actual, lo=0.25, hi=4.0, default=1.0) -> float:
    if not predicted or predicted <= 0:
        return default
    return round(min(hi, max(lo, actual / predicted)), 2)


def compute_suggested_multipliers(a: dict, bottleneck_correct: bool) -> SuggestedMultiplierUpdates:
    """Deterministically suggest (never apply) multiplier updates from errors."""
    task_duration = _ratio(a["predicted_duration"], a["actual_duration"])
    review = _ratio(a["predicted_review_hours"], a["actual_review_hours"])
    rework = _ratio(a["predicted_rework_hours"], a["actual_rework_hours"])
    # Suggest a dependency buffer only when the project overran.
    dependency_buffer = round(max(1.0, task_duration), 2)
    # A wrong bottleneck hints at an unmodelled skill gap.
    skill_gap_penalty = 0.1 if not bottleneck_correct else 0.0
    # Human-hour overrun hints at context-switching overhead.
    hh_err = error_pct(a["predicted_human_hours"], a["actual_human_hours"]) or 0.0
    context_switching_penalty = round(min(0.3, max(0.0, hh_err / 100.0) * 0.3), 3)
    return SuggestedMultiplierUpdates(
        task_duration_multiplier=task_duration,
        review_time_multiplier=review,
        rework_multiplier=rework,
        dependency_buffer_multiplier=dependency_buffer,
        skill_gap_penalty=skill_gap_penalty,
        context_switching_penalty=context_switching_penalty,
    )


def _bottleneck_correct(a: dict) -> bool:
    pred = str(a.get("predicted_bottleneck", "") or "").strip().lower()
    act = str(a.get("actual_bottleneck", "") or "").strip().lower()
    if not pred and not act:
        return False  # nothing to compare
    return pred == act


def compare(a: dict) -> CalibrationComparison:
    """Compare one actuals record to its predictions."""
    bottleneck_correct = _bottleneck_correct(a)
    quality_error = None
    if a.get("predicted_quality_score") is not None and a.get("actual_quality_score") is not None:
        quality_error = round(
            float(a["actual_quality_score"]) - float(a["predicted_quality_score"]), 2
        )

    errors = {
        "duration_error_pct": error_pct(a["predicted_duration"], a["actual_duration"]),
        "cost_error_pct": error_pct(a["predicted_cost"], a["actual_cost"]),
        "human_hours_error_pct": error_pct(
            a["predicted_human_hours"], a["actual_human_hours"]),
        "review_hours_error_pct": error_pct(
            a["predicted_review_hours"], a["actual_review_hours"]),
        "rework_hours_error_pct": error_pct(
            a["predicted_rework_hours"], a["actual_rework_hours"]),
    }
    suggested = compute_suggested_multipliers(a, bottleneck_correct)
    explanation = _explain(a, errors, bottleneck_correct, suggested)

    return CalibrationComparison(
        project_id=str(a.get("project_id", "")),
        bottleneck_correct=bottleneck_correct,
        quality_error=quality_error,
        suggested_multiplier_updates=suggested,
        explanation=explanation,
        **errors,
    )


def _explain(a, errors, bottleneck_correct, suggested) -> str:
    named = [(k, v) for k, v in errors.items() if v is not None]
    parts = []
    if named:
        worst_key, worst_val = max(named, key=lambda kv: abs(kv[1]))
        label = worst_key.replace("_error_pct", "").replace("_", " ")
        direction = "over" if worst_val > 0 else "under"
        parts.append(
            f"Biggest miss: {label} was {direction} by {abs(worst_val):.1f}%.")
    parts.append(
        "Bottleneck prediction was "
        + ("correct." if bottleneck_correct else "incorrect."))
    parts.append(
        "Suggested (informational only, NOT applied): "
        f"task_duration x{suggested.task_duration_multiplier}, "
        f"review x{suggested.review_time_multiplier}, "
        f"rework x{suggested.rework_multiplier}.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Local JSON store (no database)
# ---------------------------------------------------------------------------

def load_actuals(store_path: str) -> List[dict]:
    if not os.path.exists(store_path):
        return []
    try:
        with open(store_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def save_actual(store_path: str, actual: dict) -> None:
    """Append (or replace by project_id) an actuals record to the store."""
    os.makedirs(os.path.dirname(store_path), exist_ok=True)
    records = load_actuals(store_path)
    records = [r for r in records if r.get("project_id") != actual.get("project_id")]
    records.append(actual)
    with open(store_path, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)


def summarize(store_path: str) -> dict:
    """Aggregate comparisons across all stored actuals + biggest misses."""
    records = load_actuals(store_path)
    comparisons = [compare(r).to_dict() for r in records]

    metrics = (
        "duration_error_pct", "cost_error_pct", "human_hours_error_pct",
        "review_hours_error_pct", "rework_hours_error_pct",
    )
    mean_abs = {}
    for m in metrics:
        vals = [abs(c[m]) for c in comparisons if c.get(m) is not None]
        mean_abs[m] = round(sum(vals) / len(vals), 2) if vals else None

    # Biggest single misses across all projects.
    misses = []
    for c in comparisons:
        for m in metrics:
            if c.get(m) is not None:
                misses.append({
                    "project_id": c["project_id"], "metric": m, "error_pct": c[m],
                })
    misses.sort(key=lambda x: abs(x["error_pct"]), reverse=True)

    bottleneck_hits = sum(1 for c in comparisons if c["bottleneck_correct"])
    return {
        "project_count": len(records),
        "mean_absolute_error_pct": mean_abs,
        "bottleneck_accuracy": (
            round(bottleneck_hits / len(comparisons), 2) if comparisons else None
        ),
        "biggest_misses": misses[:5],
        "comparisons": comparisons,
        "note": "Calibration suggestions are informational and never applied automatically.",
    }
