"""LLM input-assist layer: turn brief text into editable draft tasks.

This is the **only** module that talks to Anthropic, and it is deliberately
narrow. It converts already-extracted brief text into a list of *draft tasks*
that a human reviews and edits before anything runs. It does **not** score,
route, schedule, optimise, or recommend staffing — the deterministic engine is
untouched.

Key guarantees:

* ``required_skill`` is constrained to the project's real skill vocabulary
  (the union of employee skills + AI-agent capabilities), which is injected
  into the prompt. After parsing we *re-check* every skill in code and force
  ``needs_user_review`` for anything outside the vocabulary — so a model that
  ignores the instruction still can't smuggle an invented skill through.
* Effort hours are almost never in a brief, so the model estimates them and we
  flag ``effort_is_estimated`` for the UI.
* The Anthropic SDK is imported lazily and the client reads ``ANTHROPIC_API_KEY``
  from the environment. When the key is absent we raise
  :class:`BriefParserUnavailable` so the route can return a clean 503 and the
  rest of the app keeps working.
"""

from __future__ import annotations

import os
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError

# Default model used for drafting. Overridable at runtime via the
# ANTHROPIC_MODEL env var (e.g. claude-haiku-4-5 / claude-sonnet-4-6 are cheaper
# swaps for this extraction-style task). Read per-call so the env var can be set
# without restarting / re-importing.
DEFAULT_MODEL = "claude-opus-4-8"
MAX_TOKENS = 8000


def _model_name() -> str:
    """The drafting model: ``ANTHROPIC_MODEL`` env var, else the default."""
    return os.environ.get("ANTHROPIC_MODEL", "").strip() or DEFAULT_MODEL


class BriefParserUnavailable(Exception):
    """AI drafting can't run (e.g. no API key, SDK missing). Maps to 503."""


class BriefParserError(Exception):
    """A recoverable problem during drafting (refusal, rate limit, etc.).

    ``status`` is the HTTP status the route should surface.
    """

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# ---------------------------------------------------------------------------
# Structured-output schema (what the model must return)
# ---------------------------------------------------------------------------
# Note: no numeric min/max constraints here — structured-output JSON schemas
# don't support them. We validate effort_hours > 0 in code after parsing.

class DraftTask(BaseModel):
    """One AI-drafted task. Maps cleanly onto ``ProjectTaskInput``."""

    task: str = Field(description="Short task name.")
    required_skill: str = Field(
        description="A single skill, chosen from the provided AVAILABLE SKILLS "
        "list when at all possible."
    )
    effort_hours: float = Field(
        description="Estimated effort in hours (a positive number). Briefs "
        "rarely state hours, so estimate."
    )
    effort_is_estimated: bool = Field(
        default=True,
        description="True when effort_hours was estimated rather than stated.",
    )
    priority: int = Field(default=1, description="1 = highest priority.")
    dependencies: List[str] = Field(
        default_factory=list,
        description="Names of other tasks that must finish first (exact names).",
    )
    description: Optional[str] = Field(
        default=None, description="One-line description of the work."
    )
    expected_output: Optional[str] = Field(
        default=None, description="What 'done' looks like for this task."
    )
    needs_user_review: bool = Field(
        default=False,
        description="True if the task is uncertain or the required skill isn't "
        "in AVAILABLE SKILLS.",
    )
    review_reason: Optional[str] = Field(
        default=None, description="Why this task was flagged for review."
    )


class BriefParseResult(BaseModel):
    """The full result returned by the parser / endpoint."""

    draft_tasks: List[DraftTask] = Field(default_factory=list)
    available_skills: List[str] = Field(default_factory=list)
    unmatched_skills: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


# The model only needs to produce the task list + its own notes; the route
# fills in available_skills / unmatched_skills deterministically.
class _ModelOutput(BaseModel):
    draft_tasks: List[DraftTask] = Field(default_factory=list)
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You convert a project brief into a list of DRAFT TASKS for a human to "
    "review and edit before any simulation runs. You are an input-assist tool "
    "only.\n\n"
    "Hard rules:\n"
    "- Do NOT assign people, estimate staffing, schedule, score, rank, or "
    "recommend who should do the work. Only produce draft tasks.\n"
    "- Choose `required_skill` ONLY from the AVAILABLE SKILLS list the user "
    "provides. If a task needs a skill that is not in that list, pick your "
    "closest guess AND set `needs_user_review` true with a short "
    "`review_reason` naming the missing skill. Never present an invented "
    "skill as if it were available.\n"
    "- Briefs almost never state effort in hours. Estimate `effort_hours` as a "
    "positive number and set `effort_is_estimated` true. These are starting "
    "points the user will edit.\n"
    "- Break the brief into discrete, concrete tasks. Express ordering via "
    "`dependencies`, referencing other task names exactly.\n"
    "- If the brief is too vague to produce tasks, return an empty list and "
    "explain why in `notes`."
)


def _build_user_message(text: str, available_skills: List[str]) -> str:
    skills = ", ".join(available_skills) if available_skills else "(none provided)"
    return (
        f"AVAILABLE SKILLS (choose required_skill from these): {skills}\n\n"
        "Convert the following project brief into draft tasks following the "
        "rules. Return only the structured result.\n\n"
        "----- PROJECT BRIEF -----\n"
        f"{text}\n"
        "----- END BRIEF -----"
    )


# ---------------------------------------------------------------------------
# Skill reconciliation (deterministic — never trust the model blindly)
# ---------------------------------------------------------------------------

def _reconcile_skills(
    tasks: List[DraftTask], available_skills: List[str]
) -> List[str]:
    """Force review on any task whose skill isn't in the vocabulary.

    Returns the sorted list of distinct skills the model used that aren't
    available. Mutates ``tasks`` in place (sets ``needs_user_review`` and a
    ``review_reason`` for unmatched skills) and repairs non-positive effort.
    """
    lookup = {s.lower(): s for s in available_skills}
    unmatched: set[str] = set()
    for t in tasks:
        # Repair impossible effort so the draft is always a valid starting point.
        if not t.effort_hours or t.effort_hours <= 0:
            t.effort_hours = 8.0
            t.effort_is_estimated = True
        skill = (t.required_skill or "").strip()
        if skill.lower() in lookup:
            # Normalise to the canonical casing from the vocabulary.
            t.required_skill = lookup[skill.lower()]
            continue
        # Out-of-vocabulary skill: flag for the user.
        if available_skills:  # only meaningful when we provided a list
            unmatched.add(skill)
            t.needs_user_review = True
            reason = f"Skill '{skill}' isn't in the available team skills."
            t.review_reason = (
                f"{t.review_reason} {reason}".strip()
                if t.review_reason
                else reason
            )
    return sorted(unmatched)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_brief(text: str, available_skills: List[str]) -> BriefParseResult:
    """Draft editable tasks from brief text. The engine is never touched.

    Raises :class:`BriefParserUnavailable` (no key / SDK) or
    :class:`BriefParserError` (refusal, rate limit, connection, bad request).
    """
    if not text or not text.strip():
        raise BriefParserError(422, "No brief text was provided.")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise BriefParserUnavailable(
            "AI task drafting isn't configured on this server "
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
        # Only the request essentials are sent. temperature / top_p / top_k are
        # intentionally omitted so the request uses the model's defaults.
        response = client.messages.parse(
            model=_model_name(),
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": _build_user_message(text, available_skills),
                }
            ],
            output_format=_ModelOutput,
        )
    except anthropic.RateLimitError as exc:
        raise BriefParserError(
            429, "The AI service is busy right now. Try again in a moment."
        ) from exc
    except anthropic.AuthenticationError as exc:
        # Don't leak the key/cause to the client; the message stays generic.
        raise BriefParserUnavailable(
            "The AI service credentials on this server are invalid."
        ) from exc
    except anthropic.BadRequestError as exc:
        raise BriefParserError(
            422, "The AI service rejected this brief. Try shortening or editing it."
        ) from exc
    except anthropic.APIConnectionError as exc:
        raise BriefParserError(
            502, "Couldn't reach the AI service. Check the connection and retry."
        ) from exc
    except ValidationError as exc:
        # messages.parse() validates the model's JSON against _ModelOutput and
        # raises ValidationError if it doesn't conform (malformed structured
        # output). Surface a clean 422 rather than a 500.
        raise BriefParserError(
            422,
            "The AI returned tasks in an unexpected format. Try again or edit "
            "the brief.",
        ) from exc

    # Safety classifiers may decline (HTTP 200, stop_reason == "refusal").
    if getattr(response, "stop_reason", None) == "refusal":
        raise BriefParserError(
            422,
            "The AI declined to draft tasks from this text. Edit the brief and "
            "try again.",
        )

    model_output: Optional[_ModelOutput] = response.parsed_output
    if model_output is None:
        # No parsed content (e.g. an empty/non-text response).
        raise BriefParserError(
            502, "The AI returned an empty or unreadable response. Try again."
        )
    tasks = list(model_output.draft_tasks)
    unmatched = _reconcile_skills(tasks, available_skills)

    return BriefParseResult(
        draft_tasks=tasks,
        available_skills=available_skills,
        unmatched_skills=unmatched,
        notes=model_output.notes,
    )
