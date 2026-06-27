"""Hardening / QA guard tests.

These lock in the *current* behaviour so the hardening pass (copy, helper text,
empty states, docs) provably changes no scoring or routing. They assert stable
recommendations for the sample inputs, default toggle values, safe empty states,
and backward-compatible API response shapes.

Run from the project root with::

    python -m pytest tests/test_hardening.py
    # or directly:
    python tests/test_hardening.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from fastapi.testclient import TestClient  # noqa: E402

from src.api.app import app  # noqa: E402

client = TestClient(app)


def _sample_project(**overrides):
    tasks = client.get("/tasks").json()
    payload = {
        "project_name": "Sample Project",
        "project_goal": "Ship the MVP",
        "deadline_target_hours": 90,
        "budget_target": 15000,
        "optimization_objective": "balanced",
        "tasks": tasks,
        "current_team_human_names": ["Sarah", "Maya", "Priya", "Alex", "Casey"],
        "current_team_ai_agent_names": ["AI Research Agent", "AI QA Reviewer"],
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Stable recommendations + routing (no scoring/routing behaviour change)
# ---------------------------------------------------------------------------

def _valid_options(body):
    return [o for o in body["options"].values() if o["is_valid_team"]]


def test_sample_project_recommendation_is_stable():
    # Balanced objective recommends the highest-total-score valid option.
    body = client.post("/simulate/project", json=_sample_project()).json()
    rec = body["options"][body["recommendation"]["recommended_option"]]
    assert rec["total_score"] == max(o["total_score"] for o in _valid_options(body))


def test_objective_recommendations_are_stable():
    fastest = client.post(
        "/simulate/project", json=_sample_project(optimization_objective="fastest")
    ).json()
    rec_f = fastest["options"][fastest["recommendation"]["recommended_option"]]
    assert rec_f["estimated_duration"] == min(
        o["estimated_duration"] for o in _valid_options(fastest)
    )
    cheapest = client.post(
        "/simulate/project", json=_sample_project(optimization_objective="lowest_cost")
    ).json()
    rec_c = cheapest["options"][cheapest["recommendation"]["recommended_option"]]
    assert rec_c["estimated_cost"] == min(
        o["estimated_cost"] for o in _valid_options(cheapest)
    )


def test_sample_routing_decisions_are_stable():
    tasks = client.get("/tasks").json()
    rows = client.post("/route/tasks", json={"tasks": tasks}).json()["task_routing"]
    decisions = {r["task"]: r["routing"] for r in rows}
    assert decisions["Documentation"] == "AI_ONLY"
    assert decisions["Product strategy"] == "HUMAN_ONLY"
    assert decisions["User research"] == "AI_FIRST_HUMAN_REVIEW"
    # The sample exercises a spread of routing outcomes (good for the demo).
    assert len(set(decisions.values())) >= 3


# ---------------------------------------------------------------------------
# Default toggle values
# ---------------------------------------------------------------------------

def test_scoring_toggles_default_off():
    cfg = client.get("/config").json()
    assert cfg["use_public_priors_for_scoring"] is False
    assert cfg["use_workbank_for_scoring"] is False
    # Calibration toggle is tri-state: None (auto) by default.
    assert cfg.get("use_calibration_multipliers") in (None, False)


# ---------------------------------------------------------------------------
# Safe empty states
# ---------------------------------------------------------------------------

def test_workbank_not_imported_state_is_safe():
    body = client.get("/priors/workbank").json()
    assert body["import_status"] in ("imported", "not_imported", "error")
    # With no imported CSVs/JSON, the default demo state is "not imported".
    if body["import_status"] == "not_imported":
        assert body["task_count"] == 0
        assert body["normalized_priors"] == []
        assert body["validation_warnings"]  # explains what to do


def test_workbank_match_preview_empty_is_safe():
    tasks = client.get("/tasks").json()
    matches = client.post("/priors/workbank/match-tasks", json={"tasks": tasks}).json()["matches"]
    assert len(matches) == len(tasks)
    # No imported WORKBank data -> every task is an unmatched LOW result.
    for m in matches:
        assert m["match_confidence"] in ("HIGH", "MEDIUM", "LOW")


def _reset_calibration_store():
    d = os.path.join(ROOT, "data", "calibration")
    for name in ("actuals.json", "applied_config.json", "proposal_state.json"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            os.remove(p)


def test_calibration_empty_state_is_safe():
    _reset_calibration_store()
    try:
        active = client.get("/calibration/active").json()
        assert active["config_exists"] is False
        assert active["calibration_multipliers_enabled"] is False
        assert active["calibration_provenance"] == []
        summary = client.get("/calibration/summary").json()
        assert summary["project_count"] == 0
        proposals = client.get("/calibration/proposals").json()
        assert proposals["proposals"] == []
    finally:
        _reset_calibration_store()


# ---------------------------------------------------------------------------
# Backward-compatible API response shapes
# ---------------------------------------------------------------------------

def test_project_response_keys_backward_compatible():
    body = client.post("/simulate/project", json=_sample_project()).json()
    required = {
        "project_name", "project_goal", "optimization_objective",
        "recommendation", "options", "comparison_table", "task_routing",
        "routing_summary", "pareto_front", "pareto_explanation",
        "calibration_multipliers_enabled", "calibration_multipliers_applied",
        "calibration_provenance",
    }
    assert required.issubset(set(body.keys()))
    # All nine option keys present.
    assert set(body["options"].keys()) == {
        "current_team", "human_core_ai_gap_fill", "ai_first_eligible",
        "human_first_ai_assist", "recommended_balanced_team",
        "fastest_valid_team", "lowest_cost_valid_team", "lowest_risk_valid_team",
        "most_innovative_valid_team",
    }


def test_routing_row_keys_backward_compatible():
    tasks = client.get("/tasks").json()
    row = client.post("/route/tasks", json={"tasks": tasks}).json()["task_routing"][0]
    required = {
        "task", "required_skill", "routing", "scores", "explanation",
        "review_hours", "expected_rework_hours", "ai_time_saved",
        "net_ai_time_saved", "score_provenance", "route_provenance",
        "public_priors_enabled", "workbank_scoring_enabled",
    }
    assert required.issubset(set(row.keys()))
    assert len(row["scores"]) == 9


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
    print("\nAll hardening tests passed.")
