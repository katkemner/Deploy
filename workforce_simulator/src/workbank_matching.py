"""Deterministic project-task -> WORKBank-task matching (PREVIEW ONLY).

Matches each project task to the closest imported WORKBank task using simple,
deterministic text similarity - no LLM, randomness, or external calls. The
result is **informational only**: it is surfaced in the API and UI but is NOT
used by routing, scoring, review/rework, calibration, Pareto, Monte Carlo, the
optimizer, or recommendations. Nothing about a recommendation changes because of
a WORKBank match.

It reuses the same normalisation/similarity primitives and confidence thresholds
as ``prior_matching`` (HIGH >= 0.70, MEDIUM >= 0.45, else LOW) so behaviour is
consistent across the two preview matchers.

Match signals (combined into one deterministic score):

* **primary text**  - blend of token Jaccard and ``difflib`` sequence ratio over
  the project task's descriptive text vs the WORKBank ``task_text``.
* **task-type**     - exact/partial overlap of the (optional) task types.
* **skill/occupation** - overlap of the project's required skills with the
  WORKBank task text + occupation title.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Optional

import prior_matching
from prior_matching import (
    confidence_for,
    jaccard,
    normalize,
    text_score,
)

MATCH_METHOD = "text(jaccard+difflib)+task_type+skill/occupation"

# Score weights (sum of the maxima is 1.0). Primary text dominates so an exact
# task_text match always clears the HIGH threshold; type and skill/occupation
# add deterministic, non-negative bonuses.
W_TEXT = 0.75
W_TYPE = 0.15
W_SKILL = 0.10


@dataclass
class WorkbankTaskMatch:
    project_task_id: str
    project_task_name: str
    matched_workbank_task_id: Optional[str]
    matched_task_text: Optional[str]
    matched_occupation_title: Optional[str]
    matched_task_type: Optional[str]
    match_score: float
    match_confidence: str
    match_method: str
    explanation: str
    candidate_matches: List[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

def _get(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _project_fields(task):
    """Return (name, descriptive_tokens, skill_tokens, task_type_tokens)."""
    name = str(_get(task, "task", "") or "")
    description = str(_get(task, "description", "") or "")
    expected_output = str(_get(task, "expected_output", "") or "")
    task_type = str(_get(task, "task_type", "") or "")

    required_skill = str(_get(task, "required_skill", "") or "")
    required_skills = _get(task, "required_skills", None)
    if isinstance(required_skills, (list, tuple)):
        skills_text = " ".join(str(s) for s in required_skills)
    else:
        skills_text = required_skill

    descriptive_tokens = normalize(" ".join([name, description, expected_output]))
    skill_tokens = normalize(skills_text)
    type_tokens = normalize(task_type)
    return name, descriptive_tokens, skill_tokens, type_tokens


# ---------------------------------------------------------------------------
# Candidate construction (from normalized WORKBank data)
# ---------------------------------------------------------------------------

def build_candidates(normalized: dict) -> List[dict]:
    """Flatten ``normalized_priors`` into match candidates with cached tokens."""
    candidates: List[dict] = []
    for rec in (normalized or {}).get("normalized_priors", []) or []:
        task_text = str(rec.get("task_text", "") or "")
        occupation = str(rec.get("occupation_title", "") or "")
        task_type = str(rec.get("task_type", "") or "")
        candidates.append({
            "workbank_task_id": str(rec.get("workbank_task_id", "") or ""),
            "task_text": task_text,
            "occupation_title": occupation,
            "task_type": task_type,
            "notes": str(rec.get("notes", "") or ""),
            "text_tokens": normalize(task_text),
            "occupation_tokens": normalize(occupation),
            "type_tokens": normalize(task_type),
        })
    return candidates


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _type_match(ptype_tokens: List[str], ctype_tokens: List[str]) -> float:
    if not ptype_tokens or not ctype_tokens:
        return 0.0
    if ptype_tokens == ctype_tokens:
        return 1.0
    return jaccard(ptype_tokens, ctype_tokens)


def _score(desc_tokens, skill_tokens, type_tokens, cand) -> float:
    """Deterministic combined match score in [0, 1]."""
    primary = text_score(desc_tokens, cand["text_tokens"])
    type_bonus = _type_match(type_tokens, cand["type_tokens"])
    # Do the project's required skills show up in the WORKBank task text or its
    # occupation title?
    skill_target = cand["text_tokens"] + cand["occupation_tokens"]
    skill_bonus = jaccard(skill_tokens, skill_target) if skill_tokens else 0.0
    score = W_TEXT * primary + W_TYPE * type_bonus + W_SKILL * skill_bonus
    return round(min(1.0, score), 4)


def match_task(task, candidates: List[dict], top_n: int = 3) -> WorkbankTaskMatch:
    """Match a single project task to its closest WORKBank task."""
    name, desc_tokens, skill_tokens, type_tokens = _project_fields(task)

    if not candidates:
        return WorkbankTaskMatch(
            project_task_id=name, project_task_name=name,
            matched_workbank_task_id=None, matched_task_text=None,
            matched_occupation_title=None, matched_task_type=None,
            match_score=0.0, match_confidence=prior_matching.LOW,
            match_method=MATCH_METHOD,
            explanation="No imported WORKBank tasks to match against.",
        )

    scored = []
    for cand in candidates:
        score = _score(desc_tokens, skill_tokens, type_tokens, cand)
        scored.append((score, cand))
    # Deterministic ordering: highest score first, then workbank id for ties.
    scored.sort(key=lambda sc: (-sc[0], sc[1]["workbank_task_id"]))

    best_score, best = scored[0]
    conf = confidence_for(best_score)
    explanation = (
        f"Closest WORKBank task is {best['workbank_task_id'] or '(unidentified)'} "
        f"('{best['task_text']}', occupation '{best['occupation_title']}', "
        f"type '{best['task_type']}') with match score {best_score} -> {conf}. "
        "Preview only; not used for scoring."
    )
    candidate_matches = [
        {
            "matched_workbank_task_id": c["workbank_task_id"],
            "matched_task_text": c["task_text"],
            "matched_occupation_title": c["occupation_title"],
            "matched_task_type": c["task_type"],
            "match_score": s,
            "match_confidence": confidence_for(s),
        }
        for s, c in scored[:top_n]
    ]
    return WorkbankTaskMatch(
        project_task_id=name,
        project_task_name=name,
        matched_workbank_task_id=best["workbank_task_id"],
        matched_task_text=best["task_text"],
        matched_occupation_title=best["occupation_title"],
        matched_task_type=best["task_type"],
        match_score=best_score,
        match_confidence=conf,
        match_method=MATCH_METHOD,
        explanation=explanation,
        candidate_matches=candidate_matches,
    )


def match_tasks(tasks, normalized: dict, top_n: int = 3) -> List[dict]:
    """Match every project task to its closest WORKBank task. Returns dicts."""
    candidates = build_candidates(normalized)
    return [match_task(t, candidates, top_n).as_dict() for t in tasks]


# ---------------------------------------------------------------------------
# WORKBank-backed scoring inputs (used only when use_workbank_for_scoring=True)
# ---------------------------------------------------------------------------
#
# Maps a normalized WORKBank record's fields onto the routing 1-5 suitability
# scores. This is consumed by ``routing.derive_scores`` behind the toggle - it
# never changes scores on its own. Only fields the record can support are
# returned; absent inputs are simply not filled (the heuristic stands).

# Deterministic repetition level (1-5) by WORKBank task_type. Unknown types are
# intentionally absent so repetition_level is *not* filled from WORKBank.
REPETITION_BY_TASK_TYPE = {
    "automation": 5,
    "coding": 4,
    "data": 4,
    "qa": 4,
    "testing": 4,
    "documentation": 4,
    "writing": 4,
    "finance": 4,
    "operations": 3,
    "research": 3,
    "planning": 2,
    "care": 2,
    "strategy": 1,
}


def _clamp_1to5(v) -> int:
    return max(1, min(5, int(round(v))))


def _unit_to_1to5(value: float) -> int:
    """Map a 0..1 normalized value to the routing 1-5 scale (0 -> 1, 1 -> 5)."""
    return _clamp_1to5(value * 4 + 1)


def _inverse_unit_to_1to5(value: float) -> int:
    return _unit_to_1to5(1.0 - value)


def _num(record: dict, key: str):
    v = record.get(key)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def workbank_scores(record: dict) -> dict:
    """Derive routing 1-5 suitability scores from one normalized WORKBank record.

    Only the fields the record can support are returned (others fall back to the
    heuristic). Mapping (see the WORKBank-backed scoring spec):

    * ai_capability_fit   <- avg_expert_ai_capability
    * human_judgment_need <- mean(avg_worker_desired_has, avg_expert_feasible_has)
    * verification_ease   <- inverse(uncertainty_or_high_stakes_requirement)
    * error_cost          <- uncertainty_or_high_stakes_requirement
    * context_sensitivity <- domain_expertise_requirement
    * repetition_level    <- task_type (only when recognised)
    * speed_value         <- avg_worker_automation_desire
    * collaboration_value <- HAS values, highest at mid agency (H3/H4)
    """
    out: dict = {}

    cap = _num(record, "avg_expert_ai_capability")
    if cap is not None:
        out["ai_capability_fit"] = _unit_to_1to5(cap)

    desired = _num(record, "avg_worker_desired_has")
    feasible = _num(record, "avg_expert_feasible_has")
    has_vals = [v for v in (desired, feasible) if v is not None]
    if has_vals:
        mean_has = sum(has_vals) / len(has_vals)
        out["human_judgment_need"] = _unit_to_1to5(mean_has)
        # Collaboration peaks at mid agency (HAS H3/H4 ~ 0.625 on a 0..1 scale).
        peak = 0.625
        collab_unit = max(0.0, 1.0 - abs(mean_has - peak) / 0.625)
        out["collaboration_value"] = _unit_to_1to5(collab_unit)

    unc = _num(record, "uncertainty_or_high_stakes_requirement")
    if unc is not None:
        out["verification_ease"] = _inverse_unit_to_1to5(unc)
        out["error_cost"] = _unit_to_1to5(unc)

    dom = _num(record, "domain_expertise_requirement")
    if dom is not None:
        out["context_sensitivity"] = _unit_to_1to5(dom)

    rep = REPETITION_BY_TASK_TYPE.get(str(record.get("task_type", "") or "").strip().lower())
    if rep is not None:
        out["repetition_level"] = rep

    auto = _num(record, "avg_worker_automation_desire")
    if auto is not None:
        out["speed_value"] = _unit_to_1to5(auto)

    return out


def build_score_bindings(tasks, normalized: dict) -> dict:
    """Map each task name to its WORKBank score binding for backed scoring.

    Each binding carries the matched WORKBank task id, occupation, match
    confidence/score, and the WORKBank-derived 1-5 score inputs (``wb_fields``).
    Tasks whose closest match is LOW (or with no imported data) still get a
    binding, but with empty/low fields so the consumer ignores them.
    """
    candidates = build_candidates(normalized)
    by_id = {
        str(rec.get("workbank_task_id", "") or ""): rec
        for rec in (normalized or {}).get("normalized_priors", []) or []
    }
    bindings: dict = {}
    for t in tasks:
        m = match_task(t, candidates)
        name = _get(t, "task", "") or ""
        rec = by_id.get(m.matched_workbank_task_id or "")
        bindings[name] = {
            "matched_workbank_task_id": m.matched_workbank_task_id,
            "matched_occupation_title": m.matched_occupation_title,
            "match_confidence": m.match_confidence,
            "match_score": m.match_score,
            "wb_fields": workbank_scores(rec) if rec else {},
        }
    return bindings
