"""Deterministic task-to-prior matching (PREVIEW ONLY).

Matches each project task to the closest public evidence prior using simple,
deterministic text similarity - no LLM, randomness, or external calls. The
result is **informational only**: it is surfaced in the API and UI but is NOT
used by routing, scoring, review/rework, Monte Carlo, the optimizer, or Project
Mode. Nothing about a recommendation changes because of a match.

Matching combines three deterministic signals:

* **skill match**  - exact (normalised) equality of the task's required skill
  and the prior's skill, else token overlap (Jaccard) of the skill tokens.
* **text score**   - blend of token Jaccard and ``difflib`` sequence ratio over
  the normalised task text vs the prior's descriptive text.
* **task-type match** - exact/partial overlap of an (optional) task type.

The blended score maps to confidence: HIGH >= 0.70, MEDIUM >= 0.45, else LOW.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

# A small, standard English stopword set. Kept intentionally minimal so domain
# words ("build", "design", "api", ...) survive normalisation.
STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "for", "with", "in", "on", "at",
    "by", "is", "are", "be", "this", "that", "it", "as", "from",
})

# Confidence thresholds.
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"
HIGH_THRESHOLD = 0.70
MEDIUM_THRESHOLD = 0.45

MATCH_METHOD = "skill+text(jaccard+difflib)+task_type"


@dataclass
class PriorMatch:
    project_task_id: str
    matched_prior_id: Optional[str]
    matched_prior_type: Optional[str]
    matched_task_type: Optional[str]
    matched_skill: Optional[str]
    match_score: float
    match_confidence: str
    match_method: str
    explanation: str
    candidates: List[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Text normalisation + similarity primitives
# ---------------------------------------------------------------------------

def normalize(text: str) -> List[str]:
    """Lowercase, strip punctuation, drop stopwords, and tokenize."""
    if not text:
        return []
    lowered = str(text).lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", lowered)
    return [tok for tok in cleaned.split() if tok and tok not in STOPWORDS]


def jaccard(a: List[str], b: List[str]) -> float:
    """Token Jaccard similarity of two token lists."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


def sequence_ratio(a_tokens: List[str], b_tokens: List[str]) -> float:
    """difflib sequence similarity over the normalised joined strings."""
    return SequenceMatcher(None, " ".join(a_tokens), " ".join(b_tokens)).ratio()


def text_score(task_tokens: List[str], cand_tokens: List[str]) -> float:
    """Blend token Jaccard and difflib ratio for the descriptive text."""
    return 0.5 * jaccard(task_tokens, cand_tokens) + 0.5 * sequence_ratio(
        task_tokens, cand_tokens
    )


def confidence_for(score: float) -> str:
    if score >= HIGH_THRESHOLD:
        return HIGH
    if score >= MEDIUM_THRESHOLD:
        return MEDIUM
    return LOW


# ---------------------------------------------------------------------------
# Candidate construction (from a loaded PriorsBundle)
# ---------------------------------------------------------------------------

def _candidate(prior_id, prior_type, task_type, skill, text) -> dict:
    return {
        "prior_id": prior_id,
        "prior_type": prior_type,
        "task_type": task_type or "",
        "skill": skill or "",
        "tokens": normalize(text),
    }


def build_candidates(bundle) -> List[dict]:
    """Flatten task-routing, evidence, and hybrid priors into match candidates.

    Each candidate carries an id, type, its task_type/skill, and the normalised
    tokens of its descriptive text.
    """
    candidates: List[dict] = []
    for p in bundle.task_routing_priors:
        candidates.append(
            _candidate(p.prior_id, "task_routing_prior", p.task_type, p.skill,
                       f"{p.task_type} {p.skill}")
        )
    for p in bundle.evidence_priors:
        candidates.append(
            _candidate(
                p.prior_id, "evidence_prior", p.task_type, p.skill,
                f"{p.task_type} {p.skill} {p.occupation} {p.metric_name}",
            )
        )
    for p in bundle.hybrid_guardrail_priors:
        candidates.append(
            _candidate(p.prior_id, "hybrid_guardrail_prior", p.task_type, "",
                       f"{p.task_type} {p.reason}")
        )
    return candidates


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _task_fields(task) -> Tuple[str, List[str], str, str]:
    """Extract (name, text_tokens, required_skill, task_type) from a task.

    Accepts a dict or an object. Uses optional ``description``,
    ``expected_output``, ``required_skills``, and ``task_type`` when present.
    """
    def get(name, default=None):
        if isinstance(task, dict):
            return task.get(name, default)
        return getattr(task, name, default)

    name = str(get("task", "") or "")
    required_skill = str(get("required_skill", "") or "")
    required_skills = get("required_skills", None)
    if isinstance(required_skills, (list, tuple)):
        skills_text = " ".join(str(s) for s in required_skills)
    else:
        skills_text = required_skill
    description = str(get("description", "") or "")
    expected_output = str(get("expected_output", "") or "")
    task_type = str(get("task_type", "") or "")

    text = " ".join([name, description, expected_output, skills_text, task_type])
    return name, normalize(text), (required_skill or skills_text), task_type


def _skill_match(required_skill: str, candidate_skill: str) -> float:
    rs = normalize(required_skill)
    cs = normalize(candidate_skill)
    if not rs or not cs:
        return 0.0
    if rs == cs:
        return 1.0
    return jaccard(rs, cs)


def _task_type_match(task_type: str, candidate_task_type: str) -> float:
    tt = normalize(task_type)
    ct = normalize(candidate_task_type)
    if not tt:
        return 0.0
    if not ct:
        return 0.0
    if tt == ct:
        return 1.0
    return jaccard(tt, ct)


def _score_candidate(task_tokens, required_skill, task_type, cand) -> float:
    skill = _skill_match(required_skill, cand["skill"])
    text = text_score(task_tokens, cand["tokens"])
    ttype = _task_type_match(task_type, cand["task_type"])
    # Deterministic blend. Skill equality is the strongest routing signal.
    return round(0.5 * skill + 0.3 * text + 0.2 * ttype, 4)


def match_task(task, candidates: List[dict], top_n: int = 3) -> PriorMatch:
    """Match a single task to its closest prior, with up to ``top_n`` candidates."""
    name, task_tokens, required_skill, task_type = _task_fields(task)

    scored = []
    for cand in candidates:
        score = _score_candidate(task_tokens, required_skill, task_type, cand)
        scored.append((score, cand))
    # Deterministic ordering: highest score first, then prior_id for ties.
    scored.sort(key=lambda sc: (-sc[0], sc[1]["prior_id"]))

    if not scored:
        return PriorMatch(
            project_task_id=name, matched_prior_id=None, matched_prior_type=None,
            matched_task_type=None, matched_skill=None, match_score=0.0,
            match_confidence=LOW, match_method=MATCH_METHOD,
            explanation="No priors available to match against.",
        )

    best_score, best = scored[0]
    conf = confidence_for(best_score)
    explanation = (
        f"Closest prior is {best['prior_id']} "
        f"({best['prior_type']}, task_type='{best['task_type']}', "
        f"skill='{best['skill']}') with match score {best_score} -> {conf}. "
        "Preview only; not used for scoring."
    )
    candidates_out = [
        {
            "matched_prior_id": c["prior_id"],
            "matched_prior_type": c["prior_type"],
            "matched_task_type": c["task_type"],
            "matched_skill": c["skill"],
            "match_score": s,
            "match_confidence": confidence_for(s),
        }
        for s, c in scored[:top_n]
    ]
    return PriorMatch(
        project_task_id=name,
        matched_prior_id=best["prior_id"],
        matched_prior_type=best["prior_type"],
        matched_task_type=best["task_type"],
        matched_skill=best["skill"],
        match_score=best_score,
        match_confidence=conf,
        match_method=MATCH_METHOD,
        explanation=explanation,
        candidates=candidates_out,
    )


def match_tasks(tasks, bundle, top_n: int = 3) -> List[dict]:
    """Match every task to its closest prior. Returns a list of dicts."""
    candidates = build_candidates(bundle)
    return [match_task(t, candidates, top_n).as_dict() for t in tasks]


# ---------------------------------------------------------------------------
# Score bindings (used only by opt-in prior-backed scoring)
# ---------------------------------------------------------------------------

# Routing score field -> TaskRoutingPrior attribute (0-100). Eight of the nine
# routing scores have a prior; human_learning_value does not.
PRIOR_FIELD_MAP = {
    "ai_capability_fit": "ai_capability_fit_prior",
    "human_judgment_need": "human_judgment_need_prior",
    "verification_ease": "verification_ease_prior",
    "error_cost": "error_cost_prior",
    "context_sensitivity": "context_sensitivity_prior",
    "repetition_level": "repetition_prior",
    "speed_value": "speed_value_prior",
    "collaboration_value": "collaboration_value_prior",
}


def best_task_routing_prior(task, bundle) -> Optional[dict]:
    """Find the closest ``TaskRoutingPrior`` for a task (for score binding).

    Restricts matching to task-routing priors (the only ones with the eight
    suitability prior fields). Returns ``None`` if there are no such priors.
    """
    trp_by_id = {t.prior_id: t for t in bundle.task_routing_priors}
    cands = [c for c in build_candidates(bundle) if c["prior_type"] == "task_routing_prior"]
    if not cands:
        return None
    _name, task_tokens, required_skill, task_type = _task_fields(task)
    scored = [
        (_score_candidate(task_tokens, required_skill, task_type, c), c) for c in cands
    ]
    scored.sort(key=lambda sc: (-sc[0], sc[1]["prior_id"]))
    best_score, best = scored[0]
    return {
        "matched_prior_id": best["prior_id"],
        "match_score": best_score,
        "match_confidence": confidence_for(best_score),
        "prior": trp_by_id[best["prior_id"]],
    }


def build_score_bindings(tasks, bundle) -> Dict[str, dict]:
    """Map each task name to its prior-score binding for prior-backed scoring.

    Each binding carries the matched prior id, match confidence/score, and the
    eight 0-100 prior values keyed by routing-score field name.
    """
    bindings: Dict[str, dict] = {}
    for t in tasks:
        m = best_task_routing_prior(t, bundle)
        if not m:
            continue
        trp = m["prior"]
        prior_fields = {
            field: float(getattr(trp, attr))
            for field, attr in PRIOR_FIELD_MAP.items()
        }
        name = t.get("task") if isinstance(t, dict) else getattr(t, "task", "")
        bindings[name] = {
            "matched_prior_id": m["matched_prior_id"],
            "match_confidence": m["match_confidence"],
            "match_score": m["match_score"],
            "prior_fields": prior_fields,
        }
    return bindings
