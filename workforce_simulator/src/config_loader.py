"""Load scoring weights and team constraints from a JSON config file.

The config lives at ``config/scoring_weights.json``. Weights are stored on
any convenient scale (the defaults sum to 100) and are normalised to sum to
1.0 here so the ranking maths stays simple. Sensible defaults are used for
any missing key so a partial config still works.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict


# Default weights (relative; normalised at load time).
DEFAULT_WEIGHTS = {
    "skill_coverage": 30.0,
    "capacity_fit": 20.0,
    "productivity": 20.0,
    "workload_balance": 15.0,
    "cost_efficiency": 10.0,
    "low_risk": 5.0,
}


@dataclass
class SimConfig:
    """All tunable settings for one simulation run."""

    weights: Dict[str, float] = field(
        default_factory=lambda: _normalise(DEFAULT_WEIGHTS)
    )
    require_full_required_skill_coverage: bool = True
    min_humans_per_team: int = 2
    max_humans_per_team: int = 5
    min_ai_agents_per_team: int = 0
    max_ai_agents_per_team: int = 2


def _normalise(weights: Dict[str, float]) -> Dict[str, float]:
    """Scale weights so they sum to 1.0 (returns defaults if total is 0)."""
    total = sum(weights.values())
    if total <= 0:
        return _normalise(DEFAULT_WEIGHTS)
    return {key: value / total for key, value in weights.items()}


def load_config(path: str) -> SimConfig:
    """Load a ``SimConfig`` from ``path``, filling in defaults as needed."""
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    # Merge provided weights over the defaults, then normalise.
    weights = dict(DEFAULT_WEIGHTS)
    weights.update({k: float(v) for k, v in raw.get("weights", {}).items()})

    return SimConfig(
        weights=_normalise(weights),
        require_full_required_skill_coverage=bool(
            raw.get("require_full_required_skill_coverage", True)
        ),
        min_humans_per_team=int(raw.get("min_humans_per_team", 2)),
        max_humans_per_team=int(raw.get("max_humans_per_team", 5)),
        min_ai_agents_per_team=int(raw.get("min_ai_agents_per_team", 0)),
        max_ai_agents_per_team=int(raw.get("max_ai_agents_per_team", 2)),
    )


def read_raw_config(path: str) -> dict:
    """Return the config file's contents as a plain dict (un-normalised).

    Used by the API's ``GET /config`` so callers see the same scale they
    write back (e.g. weights of 30, not 0.30). The internal ``_comment`` key,
    if present, is stripped.
    """
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    raw.pop("_comment", None)
    return raw


def write_raw_config(path: str, data: dict) -> None:
    """Persist a config dict to ``path`` as pretty JSON (used by the API)."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)

