"""Tests for calibration consumption (engine reads approved multipliers).

Covers the two guarantees and the apply -> consume -> disable flow:

* No applied config -> simulation outputs are unchanged.
* Applied multipliers change the matching outputs (duration / review / rework /
  risk) only when consumption is enabled, and disabling restores the
  uncalibrated behaviour without deleting the config.
* Simulation responses carry the calibration provenance block.

Run from the project root with::

    python -m pytest tests/test_calibration_consumption.py
    # or directly:
    python tests/test_calibration_consumption.py
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

import calibration as cal  # noqa: E402
import routing  # noqa: E402
import scheduler  # noqa: E402
from models import Assignment, Task, Team, Worker  # noqa: E402
from simulator import simulate_team  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures (engine objects)
# ---------------------------------------------------------------------------

def _tasks():
    return [
        Task("Build", "python", 10.0, priority=1, dependencies=[]),
        Task("Test", "python", 10.0, priority=1, dependencies=["Build"]),
    ]


def _team():
    dev = Worker("Dev", "human", "engineer", ["python"], 200.0, 0.0, 80.0, 8.0)
    return Team(humans=[dev], ai_agents=[])


def _write_config(multipliers, provenance=None):
    """Write an applied calibration config to a temp file; return its path."""
    d = tempfile.mkdtemp()
    path = os.path.join(d, "applied_config.json")
    cal.save_calibration_config(
        path, {"multipliers": multipliers, "provenance": provenance or []}
    )
    return path


# ---------------------------------------------------------------------------
# active_calibration resolution
# ---------------------------------------------------------------------------

def test_no_config_is_disabled_and_none():
    d = tempfile.mkdtemp()
    missing = os.path.join(d, "applied_config.json")
    active = cal.active_calibration(missing, None)
    assert active["config_exists"] is False
    assert active["enabled"] is False
    assert active["engine_multipliers"] is None
    assert active["response"]["calibration_multipliers_enabled"] is False
    assert active["response"]["calibration_multipliers_applied"] == {}
    assert active["response"]["calibration_provenance"] == []


def test_existing_config_auto_enables():
    path = _write_config({**cal.DEFAULT_CALIBRATION_MULTIPLIERS,
                          "task_duration_multiplier": 1.25})
    active = cal.active_calibration(path, None)  # None -> auto
    assert active["config_exists"] is True
    assert active["enabled"] is True
    assert active["engine_multipliers"]["task_duration_multiplier"] == 1.25


def test_flag_false_disables_existing_config():
    path = _write_config({**cal.DEFAULT_CALIBRATION_MULTIPLIERS,
                          "task_duration_multiplier": 1.25})
    active = cal.active_calibration(path, False)
    assert active["enabled"] is False
    assert active["engine_multipliers"] is None
    assert active["response"]["calibration_multipliers_applied"] == {}


def test_flag_true_enables_even_without_config():
    d = tempfile.mkdtemp()
    missing = os.path.join(d, "applied_config.json")
    active = cal.active_calibration(missing, True)
    assert active["enabled"] is True
    # Neutral defaults -> nothing actually applied, behaviour unchanged.
    assert active["engine_multipliers"] == cal.DEFAULT_CALIBRATION_MULTIPLIERS
    assert active["response"]["calibration_multipliers_applied"] == {}


# ---------------------------------------------------------------------------
# Scheduler: task_duration + dependency_buffer multipliers
# ---------------------------------------------------------------------------

def _assignments():
    return [
        Assignment("Build", "python", 10.0, 1, dependencies=[],
                   assigned_to="Dev", assigned_type="human", assigned_hours=10.0),
        Assignment("Test", "python", 10.0, 1, dependencies=["Build"],
                   assigned_to="Dev", assigned_type="human", assigned_hours=10.0),
    ]


def test_scheduler_unchanged_without_calibration():
    base = scheduler.schedule(_assignments())
    assert base["duration"] == 20.0


def test_task_duration_multiplier_scales_duration():
    mult = {**cal.DEFAULT_CALIBRATION_MULTIPLIERS, "task_duration_multiplier": 1.5}
    out = scheduler.schedule(_assignments(), mult)
    # Both 10h tasks scale to 15h on one worker -> 30h total.
    assert out["duration"] == 30.0


def test_dependency_buffer_applies_only_to_dependent_tasks():
    mult = {**cal.DEFAULT_CALIBRATION_MULTIPLIERS, "dependency_buffer_multiplier": 2.0}
    out = scheduler.schedule(_assignments(), mult)
    # Build (no deps) stays 10h; Test (deps) doubles to 20h -> 30h total.
    assert out["duration"] == 30.0


# ---------------------------------------------------------------------------
# simulate_team: duration + risk penalties
# ---------------------------------------------------------------------------

def test_simulate_team_duration_unchanged_without_calibration():
    a = simulate_team(_team(), _tasks(), True, None)
    b = simulate_team(_team(), _tasks(), True)
    assert a.estimated_duration == b.estimated_duration


def test_simulate_team_duration_changes_with_multiplier():
    base = simulate_team(_team(), _tasks(), True)
    mult = {**cal.DEFAULT_CALIBRATION_MULTIPLIERS, "task_duration_multiplier": 1.5}
    cal_res = simulate_team(_team(), _tasks(), True, mult)
    assert cal_res.estimated_duration > base.estimated_duration


def test_skill_gap_penalty_raises_risk():
    # A required skill no one covers -> missing_required_fraction > 0.
    tasks = [Task("Niche", "rust", 10.0, priority=1)]
    base = simulate_team(_team(), tasks, False)
    mult = {**cal.DEFAULT_CALIBRATION_MULTIPLIERS, "skill_gap_penalty": 0.2}
    cal_res = simulate_team(_team(), tasks, False, mult)
    assert cal_res.risk_score > base.risk_score


# ---------------------------------------------------------------------------
# Routing: review + rework multipliers (decision unchanged)
# ---------------------------------------------------------------------------

def _ai_task():
    # A writing task routes AI_FIRST_HUMAN_REVIEW -> non-zero review + rework.
    return {"task": "Docs", "required_skill": "writing", "effort_hours": 40.0,
            "priority": 1, "is_required": True}


def test_routing_unchanged_without_calibration():
    base = routing.route_task(_ai_task())
    same = routing.route_task(_ai_task(), calibration=None)
    assert base["review_hours"] == same["review_hours"]
    assert base["expected_rework_hours"] == same["expected_rework_hours"]


def test_review_multiplier_scales_review_hours():
    base = routing.route_task(_ai_task())
    mult = {**cal.DEFAULT_CALIBRATION_MULTIPLIERS, "review_time_multiplier": 2.0}
    cal_rec = routing.route_task(_ai_task(), calibration=mult)
    assert base["review_hours"] > 0
    assert cal_rec["review_hours"] == round(base["review_hours"] * 2.0, 2)
    # Decision is unchanged -- only the estimate scales.
    assert cal_rec["routing"] == base["routing"]


def test_rework_multiplier_scales_rework_hours():
    base = routing.route_task(_ai_task())
    mult = {**cal.DEFAULT_CALIBRATION_MULTIPLIERS, "rework_multiplier": 3.0}
    cal_rec = routing.route_task(_ai_task(), calibration=mult)
    assert base["expected_rework_hours"] > 0
    assert cal_rec["expected_rework_hours"] == round(
        base["expected_rework_hours"] * 3.0, 2
    )
    assert cal_rec["routing"] == base["routing"]


# ---------------------------------------------------------------------------
# Provenance payload shape
# ---------------------------------------------------------------------------

def test_provenance_payload_has_required_fields():
    prov = [{
        "updated_by": cal.CALIBRATION_APPLY_SOURCE,
        "source_project_id": "PX",
        "multiplier_name": "task_duration_multiplier",
        "previous_value": 1.0,
        "new_value": 1.4,
        "reason": "duration overran",
        "apply_notes": "",
    }]
    path = _write_config(
        {**cal.DEFAULT_CALIBRATION_MULTIPLIERS, "task_duration_multiplier": 1.4},
        prov,
    )
    active = cal.active_calibration(path, None)
    items = active["response"]["calibration_provenance"]
    assert len(items) == 1
    item = items[0]
    for key in ("multiplier_name", "value", "source_project_id",
                "previous_value", "reason", "updated_by"):
        assert key in item, key
    assert item["multiplier_name"] == "task_duration_multiplier"
    assert item["value"] == 1.4
    assert item["source_project_id"] == "PX"
    assert item["previous_value"] == 1.0
    assert item["updated_by"] == cal.CALIBRATION_APPLY_SOURCE


# ---------------------------------------------------------------------------
# API: apply -> consume -> disable, and the response calibration block
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from src.api.app import app  # noqa: E402

client = TestClient(app)


def _reset_calibration_store():
    d = os.path.join(ROOT, "data", "calibration")
    for name in ("actuals.json", "applied_config.json", "proposal_state.json"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            os.remove(p)


def _actuals(**kw):
    base = {
        "project_id": "CONS-1", "project_name": "Demo", "project_type": "software",
        "predicted_duration": 100, "actual_duration": 150,
        "predicted_cost": 10000, "actual_cost": 11000,
        "predicted_human_hours": 200, "actual_human_hours": 215,
        "predicted_review_hours": 20, "actual_review_hours": 40,
        "predicted_rework_hours": 10, "actual_rework_hours": 20,
        "predicted_bottleneck": "Alex", "actual_bottleneck": "Alex",
    }
    base.update(kw)
    return base


def _sample_project(**overrides):
    tasks = client.get("/tasks").json()
    payload = {
        "project_name": "Sample", "project_goal": "Ship",
        "optimization_objective": "balanced",
        "tasks": tasks,
        "current_team_human_names": ["Sarah", "Maya", "Priya", "Alex", "Casey"],
        "current_team_ai_agent_names": ["AI Research Agent", "AI QA Reviewer"],
    }
    payload.update(overrides)
    return payload


def _set_use_flag(value):
    cfg = client.get("/config").json()
    cfg = {k: v for k, v in cfg.items() if k != "weight_provenance"}
    cfg["use_calibration_multipliers"] = value
    assert client.post("/config", json=cfg).status_code == 200


def test_api_no_config_response_block_disabled():
    _reset_calibration_store()
    body = client.post("/simulate/project", json=_sample_project()).json()
    assert body["calibration_multipliers_enabled"] is False
    assert body["calibration_multipliers_applied"] == {}
    assert body["calibration_provenance"] == []
    _reset_calibration_store()


def test_api_applied_multiplier_changes_duration_and_can_be_disabled():
    _reset_calibration_store()
    original = client.get("/config").json()
    try:
        # Baseline duration with no applied config.
        base = client.post("/simulate/project", json=_sample_project()).json()
        base_duration = base["options"]["current_team"]["estimated_duration"]

        # Submit actuals + apply the duration multiplier (150/100 -> 1.5).
        client.post("/calibration/actuals", json=_actuals(project_id="CONS-DUR"))
        applied = client.post("/calibration/apply", json={
            "proposal_ids": ["CONS-DUR::task_duration_multiplier"],
        }).json()
        assert applied["updated_config"]["task_duration_multiplier"] == 1.5

        # Auto-enabled (config now exists) -> duration grows + provenance shown.
        cal_body = client.post("/simulate/project", json=_sample_project()).json()
        cal_duration = cal_body["options"]["current_team"]["estimated_duration"]
        assert cal_duration > base_duration
        assert cal_body["calibration_multipliers_enabled"] is True
        names = [p["multiplier_name"] for p in cal_body["calibration_provenance"]]
        assert "task_duration_multiplier" in names

        # Disable via the flag (config kept) -> back to the uncalibrated value.
        _set_use_flag(False)
        off_body = client.post("/simulate/project", json=_sample_project()).json()
        assert off_body["calibration_multipliers_enabled"] is False
        assert off_body["options"]["current_team"]["estimated_duration"] == base_duration
    finally:
        client.post("/config", json={
            k: v for k, v in original.items() if k != "weight_provenance"
        })
        _reset_calibration_store()


def test_api_calibration_active_endpoint():
    _reset_calibration_store()
    try:
        client.post("/calibration/actuals", json=_actuals(project_id="CONS-ACT"))
        client.post("/calibration/apply", json={
            "proposal_ids": ["CONS-ACT::review_time_multiplier"],
        })
        body = client.get("/calibration/active").json()
        assert body["config_exists"] is True
        assert body["calibration_multipliers_enabled"] is True
        assert "review_time_multiplier" in body["multipliers"]
        assert body["warning"]
        names = [p["multiplier_name"] for p in body["calibration_provenance"]]
        assert "review_time_multiplier" in names
    finally:
        _reset_calibration_store()


def test_api_route_tasks_carries_calibration_block():
    _reset_calibration_store()
    tasks = client.get("/tasks").json()
    body = client.post("/route/tasks", json={"tasks": tasks}).json()
    assert body["calibration_multipliers_enabled"] is False
    assert "calibration_provenance" in body
    _reset_calibration_store()


def test_api_rejected_and_unapplied_proposals_are_ignored():
    # Only an explicitly applied proposal may reach the engine. A rejected
    # proposal and a never-touched (unapplied) proposal must both stay neutral
    # and never appear in the applied/provenance output.
    _reset_calibration_store()
    try:
        client.post("/calibration/actuals", json=_actuals(project_id="CONS-REJ"))
        # Reject the review multiplier; apply only the duration multiplier.
        client.post("/calibration/reject", json={
            "proposal_ids": ["CONS-REJ::review_time_multiplier"],
        })
        client.post("/calibration/apply", json={
            "proposal_ids": ["CONS-REJ::task_duration_multiplier"],
        })

        active = client.get("/calibration/active").json()
        applied = active["calibration_multipliers_applied"]
        prov_names = {p["multiplier_name"] for p in active["calibration_provenance"]}

        # Applied proposal is consumed and traceable.
        assert "task_duration_multiplier" in applied
        assert "task_duration_multiplier" in prov_names
        # Rejected proposal stays neutral and is NOT applied.
        assert "review_time_multiplier" not in applied
        assert "review_time_multiplier" not in prov_names
        assert active["multipliers"]["review_time_multiplier"] == 1.0
        # Unapplied proposal (never selected) stays neutral too.
        assert "rework_multiplier" not in applied
        assert active["multipliers"]["rework_multiplier"] == 1.0
    finally:
        _reset_calibration_store()


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
    print("\nAll calibration-consumption tests passed.")
