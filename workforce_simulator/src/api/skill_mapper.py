"""Match task skills to the roster's own skill names, by meaning.

Briefs and hand-entered tasks name skills their own way ("Campaign Strategy",
"Dashboarding", "Stakeholder Management") while the engine staffs a task only
when someone has that exact skill. This module proposes, for each task skill
nobody has, the closest skill your people (or AI agents) DO have - or says
plainly that nobody has it, so the work is planned as outside help.

Suggestions only: the user confirms or changes every match before the run.

* With an Anthropic key, the AI matches by meaning. Its answer must be one of
  the roster's skills (checked in code) or nothing.
* Without a key, or if the AI call fails, a deterministic word match
  (``skill_matching``) is used, and the response says which method ran.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

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


class _ModelOutput(BaseModel):
    matches: List[_Match] = Field(default_factory=list)


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
    "- roster_skill must be copied exactly from the list. Never invent one."
)


def _build_user_message(
    skills: List[str], people_skills: List[str], ai_only: List[str]
) -> str:
    return (
        f"PEOPLE'S SKILLS: {', '.join(people_skills) or '(none)'}\n"
        f"AI-AGENT-ONLY CAPABILITIES: {', '.join(ai_only) or '(none)'}\n\n"
        "TASK SKILLS (match every one):\n"
        + "\n".join(f"- {s}" for s in skills)
    )


def _ai_matches(skills, people_skills, ai_only) -> Dict[str, dict]:
    """Ask the model; returns {task skill lower: {roster_skill, reason}}."""
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
                "content": _build_user_message(skills, people_skills, ai_only),
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
    return out


def map_skills(
    skills: List[str], people_skills: List[str], available_skills: List[str]
) -> dict:
    """Suggest a roster skill for every task skill nobody has.

    Returns ``{"method": "ai"|"words", "items": [...]}``; each item has
    ``skill``, ``suggestion`` (a roster skill or None), ``ai_only`` (only an
    AI agent has the suggested skill), and ``reason``. Skills someone already
    has are not listed.
    """
    have = {s.lower() for s in available_skills}
    people = {s.lower() for s in people_skills}
    ai_only = [s for s in available_skills if s.lower() not in people]

    todo: List[str] = []
    for s in skills:
        s = (s or "").strip()
        if s and s.lower() not in have and s.lower() not in {t.lower() for t in todo}:
            todo.append(s)
    if not todo:
        return {"method": "none_needed", "items": []}

    method = "ai"
    try:
        ai = _ai_matches(todo, people_skills, ai_only)
    except (BriefParserUnavailable, BriefParserError):
        ai, method = None, "words"

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
    return {"method": method, "items": items}
