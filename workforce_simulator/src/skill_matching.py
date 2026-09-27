"""Deterministic mapping from free-form skill names to canonical profile keys.

Uploaded rosters name skills the way HR files do ("Copywriting", "UX research",
"Brand strategy"), while the routing suitability sheet and the innovation
capability table are keyed by short canonical names ("writing", "ux", "brand").
This module bridges the two so those layers keep working on real rosters,
without any LLM: pure, auditable string rules.

Matching rules, tried in order (first hit wins):

1. **exact**  - the whole normalized skill equals a canonical key.
2. **token**  - a word of the skill equals a canonical key ("customer research"
   -> "research"). The leftmost matching word wins.
3. **stem**   - a word and a key share a stem after stripping common suffixes
   ("Copywriting" -> "writing", "prototyping" -> "prototype"). Substring stems
   only count when the key's stem is at least 4 characters, so short keys like
   "qa", "ux", or "api" can never match by accident.

Everything is deterministic: ties prefer the leftmost word, then the longest
key, then alphabetical order.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional, Tuple

_SUFFIXES = ("ings", "ing", "es", "s", "e")
_MIN_STEM_SUBSTRING = 4


def _norm(text: str) -> str:
    return str(text or "").strip().lower()


def _words(text: str) -> list:
    return [w for w in re.split(r"[^a-z0-9]+", _norm(text)) if w]


def _stem(word: str) -> str:
    for suf in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            return word[: -len(suf)]
    return word


def _stem_match(word: str, key: str) -> bool:
    ws, ks = _stem(word), _stem(key)
    if ws == ks:
        return True
    # Substring stems ("writ" in "copywrit") only for reasonably long stems.
    if len(ks) >= _MIN_STEM_SUBSTRING and ks in ws:
        return True
    if len(ws) >= _MIN_STEM_SUBSTRING and ws in ks:
        return True
    return False


def match(skill: str, keys: Iterable[str]) -> Tuple[Optional[str], str]:
    """Map ``skill`` to one of ``keys``. Returns ``(key, how)`` or ``(None, "none")``.

    ``how`` is "exact", "token", or "stem" — surfaced in provenance so every
    fuzzy match is visible and auditable.
    """
    key_list = sorted({_norm(k) for k in keys if _norm(k)})
    norm = _norm(skill)
    if not norm:
        return None, "none"

    if norm in key_list:
        return norm, "exact"

    words = _words(skill)

    # Leftmost word that IS a canonical key.
    for w in words:
        if w in key_list:
            return w, "token"

    # Leftmost word that stem-matches a key; among several keys prefer the
    # longest (most specific), then alphabetical for determinism.
    for w in words:
        candidates = [k for k in key_list if _stem_match(w, k)]
        if candidates:
            candidates.sort(key=lambda k: (-len(k), k))
            return candidates[0], "stem"

    return None, "none"
