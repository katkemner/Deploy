"""Public evidence priors - foundation data structures + validating loader.

This module adds the **data foundation** for grounding task routing in public
evidence (WORKBank-style automation data, human+AI meta-analyses, BLS ORS-style
task structure, software-workflow priors, AI-agent benchmarks). It loads a
local seed file, validates it, and returns structured priors.

IMPORTANT: the shipped seed values are *representative* placeholders, not exact
figures from the cited sources, and they are **not yet connected to routing or
scoring** - this slice only establishes the structures, loader, and API. No
behaviour of the simulator or router changes.

Deterministic; no LLM, external APIs, or database.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import List


class PriorsError(ValueError):
    """Raised when the priors seed file is missing fields or out of range."""


# The five recognised seed source categories.
SOURCE_CATEGORIES = (
    "WORKBank_STYLE",
    "NATURE_HUMAN_AI_META_ANALYSIS",
    "BLS_ORS_STYLE",
    "SOFTWARE_WORKFLOW_PRIOR",
    "AI_AGENT_BENCHMARK_PRIOR",
)

# TaskRoutingPrior fields that are 0-100 prior scores.
TASK_ROUTING_SCORE_FIELDS = (
    "ai_capability_fit_prior",
    "human_judgment_need_prior",
    "verification_ease_prior",
    "error_cost_prior",
    "context_sensitivity_prior",
    "repetition_prior",
    "speed_value_prior",
    "collaboration_value_prior",
    "human_agency_prior",
)

# HybridGuardrailPrior fields that are 0-100 prior scores.
HYBRID_SCORE_FIELDS = (
    "human_ai_synergy_prior",
    "human_augmentation_prior",
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PriorSourceWeight:
    source_name: str
    source_weight: float       # 0..1
    source_confidence: float   # 0..1
    notes: str = ""


@dataclass
class EvidencePrior:
    prior_id: str
    source_name: str
    source_type: str
    source_weight: float       # 0..1
    source_confidence: float   # 0..1
    task_type: str
    skill: str
    occupation: str
    metric_name: str
    metric_value: float
    notes: str = ""


@dataclass
class TaskRoutingPrior:
    prior_id: str
    task_type: str
    skill: str
    ai_capability_fit_prior: float       # 0..100
    human_judgment_need_prior: float     # 0..100
    verification_ease_prior: float       # 0..100
    error_cost_prior: float              # 0..100
    context_sensitivity_prior: float     # 0..100
    repetition_prior: float              # 0..100
    speed_value_prior: float             # 0..100
    collaboration_value_prior: float     # 0..100
    human_agency_prior: float            # 0..100
    source_refs: List[str] = field(default_factory=list)


@dataclass
class HybridGuardrailPrior:
    prior_id: str
    task_type: str
    hybrid_bonus_or_penalty: float       # signed adjustment, -100..100
    human_ai_synergy_prior: float        # 0..100
    human_augmentation_prior: float      # 0..100
    reason: str = ""
    source_refs: List[str] = field(default_factory=list)


@dataclass
class PriorsBundle:
    """All loaded priors, plus the representative-seed flag."""

    representative_seed: bool
    source_weights: List[PriorSourceWeight]
    evidence_priors: List[EvidencePrior]
    task_routing_priors: List[TaskRoutingPrior]
    hybrid_guardrail_priors: List[HybridGuardrailPrior]

    def to_dict(self) -> dict:
        return {
            "representative_seed": self.representative_seed,
            "source_weights": [asdict(s) for s in self.source_weights],
            "evidence_priors": [asdict(e) for e in self.evidence_priors],
            "task_routing_priors": [asdict(t) for t in self.task_routing_priors],
            "hybrid_guardrail_priors": [asdict(h) for h in self.hybrid_guardrail_priors],
        }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _require(item: dict, fields, ctx: str) -> None:
    if not isinstance(item, dict):
        raise PriorsError(f"{ctx}: expected an object, got {type(item).__name__}")
    missing = [f for f in fields if f not in item]
    if missing:
        raise PriorsError(f"{ctx}: missing required field(s): {missing}")


def _num(value, field_name: str, ctx: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PriorsError(f"{ctx}: field '{field_name}' must be numeric (got {value!r})")
    return float(value)


def _check_range(value, lo: float, hi: float, field_name: str, ctx: str) -> float:
    v = _num(value, field_name, ctx)
    if not (lo <= v <= hi):
        raise PriorsError(
            f"{ctx}: field '{field_name}'={v} is out of range [{lo}, {hi}]"
        )
    return v


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _build_source_weight(d: dict, i: int) -> PriorSourceWeight:
    ctx = f"source_weights[{i}]"
    _require(d, ["source_name", "source_weight", "source_confidence"], ctx)
    return PriorSourceWeight(
        source_name=str(d["source_name"]),
        source_weight=_check_range(d["source_weight"], 0.0, 1.0, "source_weight", ctx),
        source_confidence=_check_range(
            d["source_confidence"], 0.0, 1.0, "source_confidence", ctx
        ),
        notes=str(d.get("notes", "")),
    )


def _build_evidence_prior(d: dict, i: int) -> EvidencePrior:
    ctx = f"evidence_priors[{i}]"
    _require(
        d,
        ["prior_id", "source_name", "source_type", "source_weight",
         "source_confidence", "task_type", "skill", "occupation",
         "metric_name", "metric_value"],
        ctx,
    )
    return EvidencePrior(
        prior_id=str(d["prior_id"]),
        source_name=str(d["source_name"]),
        source_type=str(d["source_type"]),
        source_weight=_check_range(d["source_weight"], 0.0, 1.0, "source_weight", ctx),
        source_confidence=_check_range(
            d["source_confidence"], 0.0, 1.0, "source_confidence", ctx
        ),
        task_type=str(d["task_type"]),
        skill=str(d["skill"]),
        occupation=str(d["occupation"]),
        metric_name=str(d["metric_name"]),
        metric_value=_num(d["metric_value"], "metric_value", ctx),
        notes=str(d.get("notes", "")),
    )


def _build_task_routing_prior(d: dict, i: int) -> TaskRoutingPrior:
    ctx = f"task_routing_priors[{i}]"
    _require(d, ["prior_id", "task_type", "skill", *TASK_ROUTING_SCORE_FIELDS], ctx)
    scores = {
        f: _check_range(d[f], 0.0, 100.0, f, ctx) for f in TASK_ROUTING_SCORE_FIELDS
    }
    return TaskRoutingPrior(
        prior_id=str(d["prior_id"]),
        task_type=str(d["task_type"]),
        skill=str(d["skill"]),
        source_refs=list(d.get("source_refs", [])),
        **scores,
    )


def _build_hybrid_guardrail_prior(d: dict, i: int) -> HybridGuardrailPrior:
    ctx = f"hybrid_guardrail_priors[{i}]"
    _require(
        d,
        ["prior_id", "task_type", "hybrid_bonus_or_penalty", *HYBRID_SCORE_FIELDS],
        ctx,
    )
    return HybridGuardrailPrior(
        prior_id=str(d["prior_id"]),
        task_type=str(d["task_type"]),
        hybrid_bonus_or_penalty=_check_range(
            d["hybrid_bonus_or_penalty"], -100.0, 100.0, "hybrid_bonus_or_penalty", ctx
        ),
        human_ai_synergy_prior=_check_range(
            d["human_ai_synergy_prior"], 0.0, 100.0, "human_ai_synergy_prior", ctx
        ),
        human_augmentation_prior=_check_range(
            d["human_augmentation_prior"], 0.0, 100.0, "human_augmentation_prior", ctx
        ),
        reason=str(d.get("reason", "")),
        source_refs=list(d.get("source_refs", [])),
    )


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_priors(path: str) -> PriorsBundle:
    """Load and validate the public priors seed file.

    Raises ``PriorsError`` for malformed JSON, missing required fields, or
    values out of range (source weights/confidences in 0-1, prior scores in
    0-100). Returns a structured :class:`PriorsBundle`.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise PriorsError(f"Priors seed file not found: {path}")
    except json.JSONDecodeError as exc:
        raise PriorsError(f"Priors seed file is not valid JSON: {exc}")

    if not isinstance(data, dict):
        raise PriorsError("Priors seed root must be a JSON object.")

    for section in (
        "source_weights", "evidence_priors",
        "task_routing_priors", "hybrid_guardrail_priors",
    ):
        if not isinstance(data.get(section), list):
            raise PriorsError(f"Priors seed must contain a '{section}' list.")

    return PriorsBundle(
        representative_seed=bool(data.get("representative_seed", False)),
        source_weights=[
            _build_source_weight(d, i) for i, d in enumerate(data["source_weights"])
        ],
        evidence_priors=[
            _build_evidence_prior(d, i) for i, d in enumerate(data["evidence_priors"])
        ],
        task_routing_priors=[
            _build_task_routing_prior(d, i)
            for i, d in enumerate(data["task_routing_priors"])
        ],
        hybrid_guardrail_priors=[
            _build_hybrid_guardrail_prior(d, i)
            for i, d in enumerate(data["hybrid_guardrail_priors"])
        ],
    )
