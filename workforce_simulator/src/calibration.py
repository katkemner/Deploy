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


# ===========================================================================
# Manual apply flow (opt-in; updates a dedicated calibration config only)
# ===========================================================================
#
# Applying a proposal updates the six calibration multipliers in a *separate*
# calibration config file (not scoring_weights.json) and records provenance.
# The engine does not yet consume these multipliers, so applying changes
# *config values* (traceably) but does not change simulation behaviour. Nothing
# is ever applied automatically - the user must select and apply each proposal.

CALIBRATION_APPLY_SOURCE = "CALIBRATION_APPLY_FLOW"

# The six calibration multipliers and their neutral defaults.
DEFAULT_CALIBRATION_MULTIPLIERS = {
    "task_duration_multiplier": 1.0,
    "review_time_multiplier": 1.0,
    "rework_multiplier": 1.0,
    "dependency_buffer_multiplier": 1.0,
    "skill_gap_penalty": 0.0,
    "context_switching_penalty": 0.0,
}

# (multiplier_name, source metric label, suggestion attr, error field).
PROPOSAL_SPECS = [
    ("task_duration_multiplier", "duration", "task_duration_multiplier", "duration_error_pct"),
    ("review_time_multiplier", "review_hours", "review_time_multiplier", "review_hours_error_pct"),
    ("rework_multiplier", "rework_hours", "rework_multiplier", "rework_hours_error_pct"),
    ("dependency_buffer_multiplier", "duration", "dependency_buffer_multiplier", "duration_error_pct"),
    ("context_switching_penalty", "human_hours", "context_switching_penalty", "human_hours_error_pct"),
    ("skill_gap_penalty", "bottleneck", "skill_gap_penalty", None),
]


@dataclass
class CalibrationUpdateProposal:
    proposal_id: str
    project_id: str
    metric_name: str
    current_multiplier_name: str
    current_value: float
    suggested_value: float
    reason: str
    error_pct: Optional[float]
    confidence: str
    applied: bool = False
    rejected: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _confidence_for(error_pct: Optional[float], bottleneck_correct: bool, metric: str) -> str:
    """Deterministic confidence that a multiplier needs changing."""
    if metric == "bottleneck":
        return "HIGH" if not bottleneck_correct else "LOW"
    if error_pct is None:
        return "LOW"
    mag = abs(error_pct)
    if mag >= 25:
        return "HIGH"
    if mag >= 10:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Calibration config store (separate from scoring_weights.json)
# ---------------------------------------------------------------------------

def load_calibration_config(path: str) -> dict:
    """Load applied calibration multipliers + provenance (neutral if absent)."""
    multipliers = dict(DEFAULT_CALIBRATION_MULTIPLIERS)
    provenance_log: List[dict] = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            multipliers.update(
                {k: float(v) for k, v in (data.get("multipliers") or {}).items()
                 if k in DEFAULT_CALIBRATION_MULTIPLIERS}
            )
            provenance_log = data.get("provenance") or []
        except (json.JSONDecodeError, OSError, ValueError, TypeError):
            pass
    return {"multipliers": multipliers, "provenance": provenance_log}


def save_calibration_config(path: str, config: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)


def _load_state(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


# ---------------------------------------------------------------------------
# Proposal generation
# ---------------------------------------------------------------------------

def proposals_for_actual(actual: dict, multipliers: dict, state: dict) -> List[CalibrationUpdateProposal]:
    """Generate the (up to six) update proposals for one actuals record."""
    comparison = compare(actual)
    suggested = comparison.suggested_multiplier_updates
    project_id = str(actual.get("project_id", ""))
    errors = {
        "duration_error_pct": comparison.duration_error_pct,
        "review_hours_error_pct": comparison.review_hours_error_pct,
        "rework_hours_error_pct": comparison.rework_hours_error_pct,
        "human_hours_error_pct": comparison.human_hours_error_pct,
    }
    proposals = []
    for mult_name, metric, suggest_attr, error_field in PROPOSAL_SPECS:
        pid = f"{project_id}::{mult_name}"
        st = state.get(pid, {})
        error_pct = errors.get(error_field) if error_field else None
        proposals.append(CalibrationUpdateProposal(
            proposal_id=pid,
            project_id=project_id,
            metric_name=metric,
            current_multiplier_name=mult_name,
            current_value=float(multipliers.get(mult_name, DEFAULT_CALIBRATION_MULTIPLIERS[mult_name])),
            suggested_value=float(getattr(suggested, suggest_attr)),
            reason=comparison.explanation,
            error_pct=error_pct,
            confidence=_confidence_for(error_pct, comparison.bottleneck_correct, metric),
            applied=bool(st.get("applied", False)),
            rejected=bool(st.get("rejected", False)),
        ))
    return proposals


def all_proposals(actuals_store: str, calib_config: str, state_path: str) -> List[dict]:
    """All proposals across all stored actuals, with current applied/rejected state."""
    cfg = load_calibration_config(calib_config)
    state = _load_state(state_path)
    out = []
    for actual in load_actuals(actuals_store):
        out.extend(
            p.to_dict() for p in proposals_for_actual(actual, cfg["multipliers"], state)
        )
    return out


def _proposal_index(actuals_store: str) -> dict:
    """Map proposal_id -> (actual, multiplier_name, suggested_value, reason)."""
    index = {}
    for actual in load_actuals(actuals_store):
        comparison = compare(actual)
        suggested = comparison.suggested_multiplier_updates
        pid_base = str(actual.get("project_id", ""))
        for mult_name, _metric, suggest_attr, _ef in PROPOSAL_SPECS:
            pid = f"{pid_base}::{mult_name}"
            index[pid] = {
                "project_id": pid_base,
                "multiplier_name": mult_name,
                "suggested_value": float(getattr(suggested, suggest_attr)),
                "reason": comparison.explanation,
            }
    return index


# ---------------------------------------------------------------------------
# Apply / reject
# ---------------------------------------------------------------------------

def apply_proposals(proposal_ids, apply_notes, actuals_store, calib_config, state_path) -> dict:
    """Apply only the selected proposals to the calibration config (traceably)."""
    index = _proposal_index(actuals_store)
    state = _load_state(state_path)
    cfg = load_calibration_config(calib_config)
    multipliers = cfg["multipliers"]
    provenance_log = cfg["provenance"]

    applied, skipped = [], []
    for pid in proposal_ids:
        info = index.get(pid)
        if info is None:
            skipped.append({"proposal_id": pid, "reason": "unknown proposal id"})
            continue
        if state.get(pid, {}).get("rejected"):
            skipped.append({"proposal_id": pid, "reason": "previously rejected"})
            continue
        mult_name = info["multiplier_name"]
        previous = float(multipliers.get(mult_name, DEFAULT_CALIBRATION_MULTIPLIERS[mult_name]))
        new_value = info["suggested_value"]
        multipliers[mult_name] = new_value
        provenance_log.append({
            "updated_by": CALIBRATION_APPLY_SOURCE,
            "source_project_id": info["project_id"],
            "multiplier_name": mult_name,
            "previous_value": previous,
            "new_value": new_value,
            "reason": info["reason"],
            "apply_notes": apply_notes or "",
        })
        state[pid] = {"applied": True, "rejected": False}
        applied.append({
            "proposal_id": pid, "multiplier_name": mult_name,
            "previous_value": previous, "new_value": new_value,
        })

    save_calibration_config(calib_config, {"multipliers": multipliers, "provenance": provenance_log})
    _save_state(state_path, state)

    explanation = (
        f"Applied {len(applied)} proposal(s); skipped {len(skipped)}. "
        "Updates were written to the calibration config with provenance; "
        "simulation formulas are unchanged until a future slice consumes them."
    )
    return {
        "applied_proposals": applied,
        "rejected_or_skipped_proposals": skipped,
        "updated_config": multipliers,
        "explanation": explanation,
    }


def reject_proposals(proposal_ids, actuals_store, state_path) -> dict:
    """Mark proposals rejected (no config change)."""
    index = _proposal_index(actuals_store)
    state = _load_state(state_path)
    rejected, skipped = [], []
    for pid in proposal_ids:
        if pid not in index:
            skipped.append({"proposal_id": pid, "reason": "unknown proposal id"})
            continue
        state[pid] = {"applied": False, "rejected": True}
        rejected.append(pid)
    _save_state(state_path, state)
    return {
        "rejected_proposals": rejected,
        "skipped_proposals": skipped,
        "explanation": f"Rejected {len(rejected)} proposal(s); no config changed.",
    }
