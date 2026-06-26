"""Tests for opt-in WORKBank-backed routing scores.

Covers the precedence (MANUAL > WORKBANK > PUBLIC_PRIOR > HEURISTIC > DEFAULT),
the confidence blend rules, full provenance, and the warnings - all gated behind
``use_workbank_for_scoring`` (default off, no behaviour change).

Run from the project root with::

    python -m pytest tests/test_workbank_scoring.py
    # or directly:
    python tests/test_workbank_scoring.py
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

import routing  # noqa: E402
import workbank_matching  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "workbank", "workbank_normalized.json")


def _normalized() -> dict:
    with open(FIXTURE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _wb_record(wb_id="WB-1") -> dict:
    return next(r for r in _normalized()["normalized_priors"]
               if r["workbank_task_id"] == wb_id)


def _wb_binding(confidence="HIGH", wb_fields=None, wb_id="WB-1",
                occupation="Software Developer") -> dict:
    return {
        "matched_workbank_task_id": wb_id,
        "matched_occupation_title": occupation,
        "match_confidence": confidence,
        "match_score": 0.9,
        "wb_fields": {"ai_capability_fit": 1} if wb_fields is None else wb_fields,
    }


def _prior_binding(prior_fields, mpid="TRP-X", confidence="HIGH") -> dict:
    return {
        "matched_prior_id": mpid,
        "match_confidence": confidence,
        "match_score": 0.9,
        "prior_fields": prior_fields,
    }


# A task whose skill has a known heuristic profile (research: ai_capability_fit=4).
def _task(**kw):
    base = {"task": "Investigate the market", "required_skill": "research",
            "effort_hours": 10, "priority": 2}
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# workbank_scores mapping
# ---------------------------------------------------------------------------

def test_workbank_scores_mapping():
    scores = workbank_matching.workbank_scores(_wb_record("WB-1"))
    # 0.8 -> 5-scale 4 ; uncertainty 0.2 -> verify 4 (inverse), error 2.
    assert scores["ai_capability_fit"] == 4
    assert scores["verification_ease"] == 4
    assert scores["error_cost"] == 2
    assert scores["context_sensitivity"] == 3
    assert scores["speed_value"] == 4
    assert scores["repetition_level"] == 4  # task_type "coding"
    assert "human_judgment_need" in scores and "collaboration_value" in scores


def test_workbank_scores_skips_unknown_task_type_repetition():
    rec = dict(_wb_record("WB-1"))
    rec["task_type"] = "mystery-type"
    scores = workbank_matching.workbank_scores(rec)
    assert "repetition_level" not in scores  # not filled for unknown task types


# ---------------------------------------------------------------------------
# Toggle off = no behaviour change
# ---------------------------------------------------------------------------

def test_workbank_off_is_unchanged():
    off = routing.route_task(_task())
    # use_workbank stays False by default -> identical scores + routing.
    again = routing.route_task(_task(), workbank_binding=_wb_binding(), use_workbank=False)
    assert off["scores"] == again["scores"]
    assert off["routing"] == again["routing"]
    # No WORKBank provenance was introduced.
    assert all(p["source_type"] != "MATCHED_WORKBANK_PRIOR"
               for p in again["score_provenance"])


# ---------------------------------------------------------------------------
# Confidence rules
# ---------------------------------------------------------------------------

def test_high_confidence_workbank_influences_score():
    off = routing.route_task(_task())
    on = routing.route_task(
        _task(), workbank_binding=_wb_binding("HIGH", {"ai_capability_fit": 1}),
        use_workbank=True,
    )
    # heuristic ai_capability_fit=4; HIGH blend 0.8*1 + 0.2*4 = 1.6 -> 2.
    assert on["scores"]["ai_capability_fit"] == 2
    assert off["scores"]["ai_capability_fit"] == 4
    prov = {p["field_name"]: p for p in on["score_provenance"]}
    p = prov["ai_capability_fit"]
    assert p["source_type"] == "MATCHED_WORKBANK_PRIOR"
    assert p["source_name"] == "WORKBank"
    assert p["matched_workbank_task_id"] == "WB-1"
    assert p["matched_occupation_title"] == "Software Developer"
    assert p["match_confidence"] == "HIGH"
    assert p["blend_ratio"] == 0.8
    assert on["matched_workbank_prior_used"] == "WB-1"
    assert on["workbank_scoring_enabled"] is True


def test_medium_confidence_workbank_blends_with_heuristic():
    on = routing.route_task(
        _task(), workbank_binding=_wb_binding("MEDIUM", {"ai_capability_fit": 1}),
        use_workbank=True,
    )
    # MEDIUM blend 0.5*1 + 0.5*4 = 2.5 -> 2.
    assert on["scores"]["ai_capability_fit"] == 2
    prov = {p["field_name"]: p for p in on["score_provenance"]}
    assert prov["ai_capability_fit"]["blend_ratio"] == 0.5
    assert on["workbank_warning"] and "MEDIUM" in on["workbank_warning"]


def test_low_confidence_workbank_is_ignored():
    off = routing.route_task(_task())
    on = routing.route_task(
        _task(), workbank_binding=_wb_binding("LOW", {"ai_capability_fit": 1}),
        use_workbank=True,
    )
    assert on["scores"] == off["scores"]
    assert on["matched_workbank_prior_used"] is None
    assert all(p["source_type"] != "MATCHED_WORKBANK_PRIOR"
               for p in on["score_provenance"])


# ---------------------------------------------------------------------------
# Precedence
# ---------------------------------------------------------------------------

def test_manual_input_overrides_workbank():
    on = routing.route_task(
        _task(routing_scores={"ai_capability_fit": 5}),
        workbank_binding=_wb_binding("HIGH", {"ai_capability_fit": 1}),
        use_workbank=True,
    )
    assert on["scores"]["ai_capability_fit"] == 5
    prov = {p["field_name"]: p for p in on["score_provenance"]}
    assert prov["ai_capability_fit"]["source_type"] == "MANUAL_INPUT"


def test_workbank_beats_public_prior_when_both_on():
    # WORKBank fills ai_capability_fit; the public prior fills verification_ease.
    on = routing.route_task(
        _task(),
        binding=_prior_binding({"ai_capability_fit": 0.0, "verification_ease": 100.0}),
        use_priors=True,
        workbank_binding=_wb_binding("HIGH", {"ai_capability_fit": 5}),
        use_workbank=True,
    )
    prov = {p["field_name"]: p for p in on["score_provenance"]}
    # The shared field goes to WORKBank...
    assert prov["ai_capability_fit"]["source_type"] == "MATCHED_WORKBANK_PRIOR"
    # ...while a field only the public prior fills still uses the public prior.
    assert prov["verification_ease"]["source_type"] == "MATCHED_PUBLIC_PRIOR"


def test_public_prior_available_when_workbank_off():
    on = routing.route_task(
        _task(),
        binding=_prior_binding({"ai_capability_fit": 100.0}),
        use_priors=True,
        use_workbank=False,
    )
    prov = {p["field_name"]: p for p in on["score_provenance"]}
    assert prov["ai_capability_fit"]["source_type"] == "MATCHED_PUBLIC_PRIOR"


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------

def test_warning_when_enabled_but_data_missing():
    on = routing.route_task(_task(), workbank_binding=None, use_workbank=True)
    assert on["workbank_scoring_enabled"] is True
    assert on["matched_workbank_prior_used"] is None
    assert on["workbank_warning"] and "no usable imported WORKBank" in on["workbank_warning"]


# ---------------------------------------------------------------------------
# API: config exposure + integration + warnings
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from src.api.app import app  # noqa: E402
from src.api import routes as routes_mod  # noqa: E402

client = TestClient(app)


def _set_config(**overrides):
    cfg = client.get("/config").json()
    cfg = {k: v for k, v in cfg.items() if k != "weight_provenance"}
    cfg.update(overrides)
    assert client.post("/config", json=cfg).status_code == 200


def test_config_exposes_workbank_flag_default_false():
    cfg = client.get("/config").json()
    assert "use_workbank_for_scoring" in cfg
    assert cfg["use_workbank_for_scoring"] is False


def test_route_tasks_warns_when_enabled_but_no_data():
    original = client.get("/config").json()
    try:
        _set_config(use_workbank_for_scoring=True)
        tasks = client.get("/tasks").json()
        body = client.post("/route/tasks", json={"tasks": tasks}).json()
        assert body["workbank_scoring_enabled"] is True
        # No imported WORKBank data at the canonical path -> top-level warning.
        assert "workbank_warning" in body
    finally:
        client.post("/config", json={
            k: v for k, v in original.items() if k != "weight_provenance"
        })


def test_route_tasks_uses_workbank_when_enabled_and_data_present():
    original = client.get("/config").json()
    wrote = False
    try:
        # Make imported WORKBank data available at the canonical path.
        os.makedirs(os.path.dirname(routes_mod.WORKBANK_NORMALIZED), exist_ok=True)
        with open(FIXTURE, "r", encoding="utf-8") as fh:
            data = fh.read()
        with open(routes_mod.WORKBANK_NORMALIZED, "w", encoding="utf-8") as fh:
            fh.write(data)
        wrote = True

        _set_config(use_workbank_for_scoring=True)
        task = {"task": "Write unit tests for a module", "required_skill": "testing",
                "effort_hours": 10, "priority": 1, "task_type": "coding"}
        body = client.post("/route/tasks", json={"tasks": [task]}).json()
        row = body["task_routing"][0]
        assert row["workbank_scoring_enabled"] is True
        assert row["matched_workbank_prior_used"] == "WB-1"
        assert row["workbank_match_confidence"] == "HIGH"
        assert any(p["source_type"] == "MATCHED_WORKBANK_PRIOR"
                   for p in row["score_provenance"])
    finally:
        client.post("/config", json={
            k: v for k, v in original.items() if k != "weight_provenance"
        })
        if wrote and os.path.exists(routes_mod.WORKBANK_NORMALIZED):
            os.remove(routes_mod.WORKBANK_NORMALIZED)


# Allow running directly without pytest.
if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL  {name}: {exc}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"ERROR {name}: {exc!r}")
    if failures:
        print(f"\n{failures} test(s) failed.")
        sys.exit(1)
    print("\nAll WORKBank scoring tests passed.")
