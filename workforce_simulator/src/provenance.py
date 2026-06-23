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
EXISTING_HEURISTIC = "EXISTING_HEURISTIC"
DEFAULT_FALLBACK = "DEFAULT_FALLBACK"

# Every valid source type, for validation and the UI.
VALID_SOURCE_TYPES = (MANUAL_INPUT, EXISTING_HEURISTIC, DEFAULT_FALLBACK)

# Deterministic confidence by source type: a value you supplied is the most
# trustworthy; a model heuristic is moderate; a bare default is weak.
CONFIDENCE = {
    MANUAL_INPUT: 0.95,
    EXISTING_HEURISTIC: 0.7,
    DEFAULT_FALLBACK: 0.3,
}


def item(
    field_name: str,
    value: Any,
    source_type: str,
    source_name: str,
    explanation: str,
) -> Dict[str, Any]:
    """Build one provenance entry with a deterministic confidence."""
    return {
        "field_name": field_name,
        "value": value,
        "source_type": source_type,
        "source_name": source_name,
        "confidence": CONFIDENCE.get(source_type, CONFIDENCE[DEFAULT_FALLBACK]),
        "explanation": explanation,
    }
