"""Match task skills to the roster's own skill names, by meaning.

Briefs and hand-entered tasks name skills their own way ("Campaign Strategy",
"Dashboarding", "Stakeholder Management") while the engine staffs a task only
when someone has that exact skill. This module proposes, for each task skill
nobody has, the closest skill your people (or AI agents) DO have - or says
plainly that nobody has it, so the work is planned as outside help.

It also checks **stretched labels**: a task tagged with a roster skill that
doesn't really cover the work (ad creative production labelled "Prototype",
a software skill). Those pass every exact-match check, so only a by-meaning
review can catch them. This needs AI; without it, no stretch check runs and
the response says so.

Suggestions only: the user confirms or changes every match before the run.

* With an Anthropic key, the AI matches by meaning. Its answer must be one of
  the roster's skills (checked in code) or nothing.
* Without a key, or if the AI call fails, a deterministic word match
  (``skill_matching``) is used, and the response says which method ran.
"""

from __future__ import annotations

import os
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

import skill_matching

from .brief_parser import (
    MAX_TOKENS,
    BriefParserError,
    BriefParserUnavailable,
    _model_name,
)


class _Match(BaseModel):
    skill: str = Field(description="The task skill exactly as given in TASK SKILLS.")
    roster_skill: Optional[str] = Field(
        default=None,
        description=(
            "The ONE skill from ROSTER SKILLS that someone needs in order to do "
            "this work, or null when none genuinely covers it."
        ),
    )
    reason: Optional[str] = Field(
        default=None, description="One short sentence explaining the match (or why none fits)."
    )


class _Fit(BaseModel):
    task: str = Field(description="The task name exactly as given in TASKS.")
    fit: Literal["good", "stretch"] = Field(
        description=(
            "good = someone with the labelled skill would normally do this "
            "work well. stretch = the label is only loosely related and a "
            "person with that skill would not normally be able to do it well."
        )
    )
    needed_skill: Optional[str] = Field(
        default=None,
        description="For a stretch: a short name for the skill the work "
        "really needs (e.g. 'Ad creative production').",
    )
    reason: Optional[str] = Field(default=None, description="One short sentence.")


class _ModelOutput(BaseModel):
    matches: List[_Match] = Field(default_factory=list)
    fits: List[_Fit] = Field(default_factory=list)


_SYSTEM_PROMPT = (
    "You match the skills a project's tasks need to the skills a team "
    "actually has, so the right people get staffed. You only SUGGEST "
    "matches; the manager confirms each one.\n\n"
    "Rules:\n"
    "- For each TASK SKILL, pick the single ROSTER SKILL whose holder could "
    "do that work competently (e.g. 'Campaign Strategy' -> 'Strategy', "
    "'Dashboarding' -> 'Data').\n"
    "- Prefer PEOPLE'S SKILLS. Use an AI-AGENT-ONLY capability only when no "
    "person's skill fits and the work suits an AI agent.\n"
    "- Return null when no roster skill genuinely covers the work (e.g. "
    "'Paid media buying' when nobody does advertising). Do not stretch: a "
    "wrong match staffs the wrong person, while null correctly flags that "
    "outside help is needed.\n"
    "- roster_skill must be copied exactly from the list. Never invent one.\n"
    "- Also review each of the TASKS, which are already labelled with a "
    "roster skill. Mark fit 'stretch' only when a person with that skill "
    "would NOT normally be able to do the work well - e.g. ad creative "
    "production labelled 'Prototype' (a software skill), or paid media "
    "buying labelled 'Operations'. Adjacent-but-competent labels are 'good'. "
    "For a stretch, name the skill the work really needs."
)


def _build_user_message(
    skills: List[str], people_skills: List[str], ai_only: List[str],
    tasks: Optional[List[Dict[str, str]]] = None,
) -> str:
    msg = (
        f"PEOPLE'S SKILLS: {', '.join(people_skills) or '(none)'}\n"
        f"AI-AGENT-ONLY CAPABILITIES: {', '.join(ai_only) or '(none)'}\n\n"
        "TASK SKILLS (match every one):\n"
        + ("\n".join(f"- {s}" for s in skills) or "(none)")
    )
    if tasks:
        msg += "\n\nTASKS (review each label):\n" + "\n".join(
            f"- {t['task']} | labelled: {t['required_skill']}" for t in tasks
        )
    return msg


def _ai_review(skills, people_skills, ai_only, tasks=None):
    """Ask the model; returns (matches, fits).

    matches: {task skill lower: {roster_skill, reason}}
    fits:    {task name: {needed_skill, reason}} - stretches only
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise BriefParserUnavailable("AI matching isn't configured on this server.")
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise BriefParserUnavailable("The Anthropic SDK isn't installed.") from exc

    client = anthropic.Anthropic()
    try:
        response = client.messages.parse(
            model=_model_name(),
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": _build_user_message(skills, people_skills, ai_only, tasks),
            }],
            output_format=_ModelOutput,
        )
    except (anthropic.APIError, ValidationError) as exc:
        raise BriefParserError(502, "AI matching failed.") from exc
    if getattr(response, "stop_reason", None) == "refusal" or response.parsed_output is None:
        raise BriefParserError(502, "AI matching returned nothing usable.")

    vocab = {s.lower(): s for s in list(people_skills) + list(ai_only)}
    out: Dict[str, dict] = {}
    for m in response.parsed_output.matches:
        key = m.skill.strip().lower()
        if key in out:
            continue
        rs = (m.roster_skill or "").strip().lower()
        # Never trust the model to stay in the vocabulary.
        out[key] = {"roster_skill": vocab.get(rs), "reason": m.reason}
    asked = {t["task"] for t in (tasks or [])}
    fits: Dict[str, dict] = {}
    for f in response.parsed_output.fits:
        if f.task in asked and f.fit == "stretch" and f.task not in fits:
            fits[f.task] = {"needed_skill": (f.needed_skill or "").strip() or None,
                            "reason": f.reason}
    return out, fits


def map_skills(
    skills: List[str], people_skills: List[str], available_skills: List[str],
    tasks: Optional[List[Dict[str, str]]] = None,
) -> dict:
    """Suggest a roster skill for every task skill nobody has.

    Returns ``{"method", "items", "stretches", "stretch_check"}``. Each item
    has ``skill``, ``suggestion`` (a roster skill or None), ``ai_only`` (only
    an AI agent has the suggested skill), and ``reason``; skills someone
    already has are not listed. ``tasks`` (optional) are reviewed for
    stretched labels; each stretch has ``task``, ``required_skill``,
    ``needed_skill``, ``suggestion`` (a better roster skill, or None =
    outside help) and ``reason``. ``stretch_check`` is "ai" when that review
    ran, else "unavailable".
    """
    have = {s.lower() for s in available_skills}
    people = {s.lower() for s in people_skills}
    ai_only = [s for s in available_skills if s.lower() not in people]

    todo: List[str] = []
    for s in skills:
        s = (s or "").strip()
        if s and s.lower() not in have and s.lower() not in {t.lower() for t in todo}:
            todo.append(s)
    # Only tasks labelled with a skill someone has can be "stretched".
    review = [
        {"task": str(t.get("task", "")).strip(),
         "required_skill": str(t.get("required_skill", "")).strip()}
        for t in (tasks or [])
        if str(t.get("required_skill", "")).strip().lower() in have
        and str(t.get("task", "")).strip()
    ]
    if not todo and not review:
        return {"method": "none_needed", "items": [], "stretches": [],
                "stretch_check": "ai"}

    method = "ai"
    try:
        ai, fits = _ai_review(todo, people_skills, ai_only, review)
    except (BriefParserUnavailable, BriefParserError):
        ai, fits, method = None, None, "words"

    canon = {s.lower(): s for s in available_skills}
    items = []
    for s in todo:
        if ai is not None:
            hit = ai.get(s.lower()) or {}
            suggestion, reason = hit.get("roster_skill"), hit.get("reason")
        else:
            key, how = skill_matching.match(s, list(people_skills) or available_skills)
            if key is None and people_skills:
                key, how = skill_matching.match(s, available_skills)
            suggestion = canon.get(key) if key else None
            reason = (
                f"Shares the word '{suggestion}'." if suggestion and how == "token"
                else f"Similar word to '{suggestion}'." if suggestion
                else None
            )
        if not suggestion and not reason:
            reason = "Nobody on your roster has a matching skill."
        items.append({
            "skill": s,
            "suggestion": suggestion,
            "ai_only": bool(suggestion) and suggestion.lower() not in people,
            "reason": reason,
        })
    canon_lower = {s.lower(): s for s in available_skills}
    stretches = []
    for t in review:
        hit = (fits or {}).get(t["task"])
        if not hit:
            continue
        needed = hit["needed_skill"]
        # The skill it really needs may be one someone on the roster has.
        better = canon_lower.get((needed or "").lower())
        if better and better.lower() == t["required_skill"].lower():
            continue  # the model contradicted itself; keep the label
        stretches.append({
            "task": t["task"],
            "required_skill": t["required_skill"],
            "needed_skill": needed,
            "suggestion": better,
            "reason": hit["reason"],
        })
    return {
        "method": method if todo else "none_needed",
        "items": items,
        "stretches": stretches,
        "stretch_check": "ai" if fits is not None else "unavailable",
    }
