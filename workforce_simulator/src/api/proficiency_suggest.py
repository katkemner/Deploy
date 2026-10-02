"""LLM input-assist: suggest strength answers from roster notes (opt-in).

When an uploaded roster carries free-text notes (strengths, growth areas,
manager notes) but no proficiency column, the user may ask the AI to
*suggest* an answer per (person, skill) pair. Suggestions only prefill the
pre-run strength check; the user confirms or changes every one, and nothing
is stored. Same call pattern and error handling as the brief parser.

The model may only use what the notes say. It must return "unknown" rather
than guess, and must never infer from personality, demographics, or
anything that isn't about the work itself.
"""

from __future__ import annotations

import os
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from .brief_parser import (
    MAX_TOKENS,
    BriefParserError,
    BriefParserUnavailable,
    _model_name,
)


class _Suggestion(BaseModel):
    person: str = Field(description="Exactly as given in PAIRS.")
    skill: str = Field(description="Exactly as given in PAIRS.")
    answer: Literal["almost_always", "usually", "sometimes", "rarely", "unknown"] = Field(
        description=(
            "How often this person's work on this skill is likely approved "
            "without changes, judged ONLY from their notes. 'unknown' when "
            "the notes don't speak to this skill."
        )
    )
    reason: Optional[str] = Field(
        default=None,
        description="Short quote or paraphrase from the notes behind it.",
    )


class _ModelOutput(BaseModel):
    suggestions: List[_Suggestion] = Field(default_factory=list)


_SYSTEM_PROMPT = (
    "You help a manager fill in a quick check of how strong their team is at "
    "specific skills, using the manager's own notes about each person. You "
    "only SUGGEST answers; the manager confirms or changes every one.\n\n"
    "Rules:\n"
    "- For each (person, skill) pair, answer how often that person's work on "
    "that skill is likely approved without changes: almost_always, usually, "
    "sometimes, rarely - or unknown.\n"
    "- Use ONLY what the notes say about the work. If the notes don't speak "
    "to that skill, answer unknown. Never guess.\n"
    "- Never infer from personality, demographics, age, health, or anything "
    "not about the work itself.\n"
    "- Give a short reason quoting or paraphrasing the notes."
)


def _build_user_message(pairs: List[Dict[str, str]], notes: Dict[str, str]) -> str:
    lines = ["NOTES (per person):"]
    for person in sorted({p["person"] for p in pairs}):
        lines.append(f"- {person}: {notes.get(person, '(no notes)')}")
    lines.append("")
    lines.append("PAIRS (answer every one):")
    for p in pairs:
        lines.append(f"- person: {p['person']} | skill: {p['skill']}")
    return "\n".join(lines)


def suggest(pairs: List[Dict[str, str]], notes: Dict[str, str]) -> List[dict]:
    """Return one suggestion per pair (unknown where the notes are silent)."""
    pairs = [p for p in pairs if notes.get(p["person"])]
    if not pairs:
        return []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise BriefParserUnavailable(
            "AI suggestions aren't configured on this server "
            "(ANTHROPIC_API_KEY is not set)."
        )
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise BriefParserUnavailable(
            "The Anthropic SDK isn't installed on this server."
        ) from exc

    client = anthropic.Anthropic()
    try:
        response = client.messages.parse(
            model=_model_name(),
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_message(pairs, notes)}],
            output_format=_ModelOutput,
        )
    except anthropic.RateLimitError as exc:
        raise BriefParserError(
            429, "The AI service is busy right now. Try again in a moment."
        ) from exc
    except anthropic.AuthenticationError as exc:
        raise BriefParserUnavailable(
            "The AI service credentials on this server are invalid."
        ) from exc
    except anthropic.BadRequestError as exc:
        raise BriefParserError(
            422, "The AI service rejected these notes. Answer the check manually."
        ) from exc
    except anthropic.APIConnectionError as exc:
        raise BriefParserError(
            502, "Couldn't reach the AI service. Check the connection and retry."
        ) from exc
    except ValidationError as exc:
        raise BriefParserError(
            422, "The AI returned suggestions in an unexpected format. Try again."
        ) from exc

    if getattr(response, "stop_reason", None) == "refusal":
        raise BriefParserError(
            422, "The AI declined to suggest from these notes. Answer manually."
        )
    output: Optional[_ModelOutput] = response.parsed_output
    if output is None:
        raise BriefParserError(
            502, "The AI returned an empty or unreadable response. Try again."
        )

    # Keep only suggestions for pairs we asked about (never trust the model to
    # invent people or skills); missing pairs come back as unknown.
    wanted = {(p["person"].lower(), p["skill"].lower()): p for p in pairs}
    got = {}
    for s in output.suggestions:
        k = (s.person.strip().lower(), s.skill.strip().lower())
        if k in wanted and k not in got:
            got[k] = s
    result = []
    for k, p in wanted.items():
        s = got.get(k)
        result.append({
            "person": p["person"],
            "skill": p["skill"],
            "answer": s.answer if s else "unknown",
            "reason": (s.reason if s else None),
        })
    return result
