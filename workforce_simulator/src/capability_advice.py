"""Relative-capability advice: person vs AI, compared on first-pass rate.

Advice only - nothing here changes routing decisions, scores, hours, costs,
or which team is recommended. It annotates the recommended plan with
task-level suggestions, following the strongest moderator in Vaccaro et al.
(Nature Human Behaviour 2024): human-AI combinations beat either alone when
the human is the stronger party, and do worse than AI alone when the AI is.

Both sides are compared in ONE unit - the chance the work passes its
acceptance check the first time:

* Person: the manager's one-time answer for this run ("how often does their
  work on this skill get approved without changes?"), mapped to a rate.
* AI: estimated from the task's routing ``ai_capability_fit`` score (after
  stage/irreversibility nudges). Labeled an estimate - no reliable published
  first-pass benchmarks exist per task type.

Design constraints (EU AI Act Annex III 4(b) / Art. 6(3) profiling line):
answers are a one-time planning input for this run - never stored per person
- and advice is worded about the TASK, never as a person-vs-machine ranking.
Person-level detail appears only in ``details`` (the UI's Why view).
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Tuple

# Pass-rate buckets: the answer scale shown to users (frequency words about
# observed outcomes, not skill grades) and the rate each maps to.
BUCKETS: Dict[str, float] = {
    "almost_always": 0.90,
    "usually": 0.75,
    "sometimes": 0.50,
    "rarely": 0.25,
}
BUCKET_LABELS = {
    "almost_always": "Almost always",
    "usually": "Usually",
    "sometimes": "Sometimes",
    "rarely": "Rarely",
}
UNKNOWN = "unknown"

# AI first-pass estimate by ai_capability_fit (1-5). Our conservative
# defaults, replaced by measured rates once review outcomes are recorded.
AI_PASS_ESTIMATE: Dict[int, float] = {1: 0.25, 2: 0.40, 3: 0.55, 4: 0.70, 5: 0.85}

# "Clearly" stronger: a gap of at least 20 percentage points (our judgment
# call; the evidence gives direction, not a threshold).
CLEAR_GAP = 0.20

_LEVEL_WORDS = [
    # Order matters: longer phrases first.
    ("almost_always", ("almost always", "always", "expert", "advanced",
                       "excellent", "exceptional", "outstanding", "master")),
    ("usually", ("usually", "strong", "proficient", "good", "very good",
                 "skilled", "high")),
    ("sometimes", ("sometimes", "capable", "intermediate", "competent",
                   "average", "moderate", "ok", "okay", "medium", "fair")),
    ("rarely", ("rarely", "never", "learning", "beginner", "novice", "junior",
                "basic", "low", "weak", "developing", "limited")),
]


def parse_level(raw) -> Optional[str]:
    """Map a free-form level ('Expert', '4', 'usually', '8/10') to a bucket."""
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    if text.replace(" ", "_") in BUCKETS:
        return text.replace(" ", "_")
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(?:/\s*(\d+))?$", text)
    if m:
        value = float(m.group(1))
        scale = float(m.group(2)) if m.group(2) else (10.0 if value > 5 else 5.0)
        if scale <= 0 or value < 0:
            return None
        on5 = value / scale * 5.0
        if on5 >= 4.5:
            return "almost_always"
        if on5 >= 3.5:
            return "usually"
        if on5 >= 2.5:
            return "sometimes"
        return "rarely"
    for bucket, words in _LEVEL_WORDS:
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", text):
                return bucket
    return None


def parse_proficiency_cell(raw) -> Dict[str, str]:
    """Parse a roster cell like 'Copywriting: expert; SQL: 2' into
    {lower-cased skill: bucket}. Unparseable pieces are skipped."""
    if raw is None:
        return {}
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return {}
    out: Dict[str, str] = {}
    for piece in re.split(r"[;|\n]|,(?=[^,:=]*[:=])", text):
        if ":" in piece:
            skill, level = piece.split(":", 1)
        elif "=" in piece:
            skill, level = piece.split("=", 1)
        else:
            continue
        skill = skill.strip().lower()
        bucket = parse_level(level)
        if skill and bucket:
            out[skill] = bucket
    return out


def ai_pass_estimate(fit) -> Optional[float]:
    try:
        return AI_PASS_ESTIMATE[int(fit)]
    except (TypeError, ValueError, KeyError):
        return None


def _key(person: str, skill: str) -> Tuple[str, str]:
    return (str(person).strip().lower(), str(skill).strip().lower())


def answers_map(answers: Iterable) -> Dict[Tuple[str, str], str]:
    """{(person, skill): bucket} from request answers; unknowns dropped."""
    out = {}
    for a in answers or []:
        get = a.get if isinstance(a, dict) else (lambda k, _a=a: getattr(_a, k, None))
        bucket = str(get("answer") or "").strip().lower()
        if bucket in BUCKETS:
            out[_key(get("person"), get("skill"))] = bucket
    return out


def _pct(rate: float) -> str:
    return f"~{round(rate * 100)}%"


def build_advice(routing_records: List[dict], assignments, answers) -> dict:
    """Task-level advice for the recommended option's human-assigned tasks.

    ``assignments`` are the option's Assignment objects; ``answers`` the
    request's one-time proficiency answers. Returns ``{"items": [...],
    "unknown_tasks": int, "answered_tasks": int, "note": str}``.
    """
    amap = answers_map(answers)
    rec_by_task = {r.get("task"): r for r in routing_records}
    items: List[dict] = []
    unknown = 0
    answered = 0

    for a in assignments:
        if getattr(a, "assigned_type", None) != "human" or not a.assigned_to:
            continue
        rec = rec_by_task.get(a.task)
        if not rec:
            continue
        bucket = amap.get(_key(a.assigned_to, a.required_skill))
        if bucket is None:
            unknown += 1
            continue
        answered += 1
        scores = rec.get("scores") or {}
        ai_rate = ai_pass_estimate(scores.get("ai_capability_fit"))
        if ai_rate is None:
            continue  # no AI profile -> nothing to compare against
        person_rate = BUCKETS[bucket]
        gap = person_rate - ai_rate
        details = {
            "person": a.assigned_to,
            "skill": a.required_skill,
            "person_answer": BUCKET_LABELS[bucket],
            "person_pass_rate": _pct(person_rate),
            "ai_pass_rate_estimate": _pct(ai_rate),
            "basis": "your answer for this run (AI side estimated)",
        }
        routing = rec.get("routing")

        if gap >= CLEAR_GAP:
            already = routing in ("HUMAN_ONLY", "HUMAN_FIRST_AI_ASSIST")
            items.append({
                "task": a.task,
                "kind": "person_leads",
                "advice": (
                    "The assigned person should lead this task, with AI "
                    "assisting on drafts, variations, and research."
                    + (" This matches the current routing." if already else
                       f" (Current routing is {routing}; consider switching "
                       "to human-led.)")
                ),
                "details": details,
            })
        elif gap <= -CLEAR_GAP:
            learning = scores.get("human_learning_value") or 0
            if bucket in ("rarely", "sometimes") and learning >= 4:
                items.append({
                    "task": a.task,
                    "kind": "keep_for_growth",
                    "advice": (
                        "AI is estimated to get this right more often, but "
                        "doing it builds real skill - keep the assigned person "
                        "on it and review normally."
                    ),
                    "details": details,
                })
                continue
            failed = []
            if (scores.get("verification_ease") or 0) < 4:
                failed.append("the output isn't quick to check")
            if (scores.get("error_cost") or 5) > 2:
                failed.append("mistakes aren't cheap")
            if rec.get("irreversible"):
                failed.append("it's hard to undo")
            if rec.get("stage") == "choice":
                failed.append("it's a decision task")
            if not failed:
                items.append({
                    "task": a.task,
                    "kind": "spot_check",
                    "advice": (
                        "A spot-check against the acceptance criteria is "
                        "enough here: AI is estimated to get this right more "
                        "often, the output is easy to check, and mistakes "
                        "are cheap."
                    ),
                    "details": details,
                })
            else:
                items.append({
                    "task": a.task,
                    "kind": "keep_review",
                    "advice": (
                        "AI is estimated to get this right more often, but "
                        "keep the full review: " + ", ".join(failed) + "."
                    ),
                    "details": details,
                })
        # Within the gap: no advice - today's routing stands.

    note = (
        "Advice only - routing, hours, and costs are unchanged. Based on your "
        "answers for this run, which are not stored."
    )
    if unknown:
        note += (
            f" Strength unknown for {unknown} task(s), so advice for those "
            "isn't personalized."
        )
    return {
        "items": items,
        "answered_tasks": answered,
        "unknown_tasks": unknown,
        "note": note,
    }
