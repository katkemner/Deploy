"""Provenance for routing scores and decisions.

Adds *explainability metadata* describing where each routing score and decision
came from, without changing any value, formula, or decision. Three source types
are recognised:

* ``MANUAL_INPUT``      - supplied directly by the user (a per-task score
  override).
* ``EXISTING_HEURISTIC``- produced by the existing deterministic logic (a skill
  profile, a routing rule, or a formula).
* ``DEFAULT_FALLBACK``  - a built-in default used because no input or profile
  applied (an unprofiled skill, or a score missing from a partial override).

Each provenance entry (built by :func:`item`) carries::

    {field_name, value, source_type, source_name, confidence, explanation}

``confidence`` is a deterministic 0-1 number derived purely from the source
type (manual input is the most certain, a default fallback the least). Nothing
here is random and there are no external calls.
"""

from __future__ import annotations

from typing import Any, Dict

MANUAL_INPUT = "MANUAL_INPUT"
MATCHED_WORKBANK_PRIOR = "MATCHED_WORKBANK_PRIOR"
MATCHED_PUBLIC_PRIOR = "MATCHED_PUBLIC_PRIOR"
EXISTING_HEURISTIC = "EXISTING_HEURISTIC"
DEFAULT_FALLBACK = "DEFAULT_FALLBACK"

# Every valid source type, for validation and the UI.
VALID_SOURCE_TYPES = (
    MANUAL_INPUT, MATCHED_WORKBANK_PRIOR, MATCHED_PUBLIC_PRIOR,
    EXISTING_HEURISTIC, DEFAULT_FALLBACK,
)

# Deterministic confidence by source type: a value you supplied is the most
# trustworthy; a matched WORKBank/public prior and a model heuristic are
# moderate; a bare default is weak. (A prior-backed item may override this with
# a match-confidence-derived value.)
CONFIDENCE = {
    MANUAL_INPUT: 0.95,
    MATCHED_WORKBANK_PRIOR: 0.78,
    MATCHED_PUBLIC_PRIOR: 0.75,
    EXISTING_HEURISTIC: 0.7,
    DEFAULT_FALLBACK: 0.3,
}


def item(
    field_name: str,
    value,
    source_type: str,
    source_name: str,
    explanation: str,
    confidence: float = None,
    **extra,
) -> dict:
    """Build one provenance entry.

    ``confidence`` defaults to the deterministic value for ``source_type`` but
    may be overridden (e.g. a prior-backed score uses its match confidence).
    Any ``extra`` keyword fields (e.g. ``matched_prior_id``, ``match_confidence``,
    ``blend_ratio``) are merged into the entry.
    """
    entry = {
        "field_name": field_name,
        "value": value,
        "source_type": source_type,
        "source_name": source_name,
        "confidence": (
            confidence if confidence is not None
            else CONFIDENCE.get(source_type, CONFIDENCE[DEFAULT_FALLBACK])
        ),
        "explanation": explanation,
    }
    entry.update(extra)
    return entry
