"""Tests for the risk-tiered checkpoint plan and the irreversibility flag.

Covers: irreversible tasks raise error cost (with provenance) and earn a
release gate; HUMAN_ONLY tasks land in the no-delegate zone; low-risk
repetitive AI_ONLY work gets a sampling audit instead of full review;
high-risk AI work gets a mid-stream checkpoint; the rubber-stamping warning
fires on concentrated review load; and /simulate/project returns the plan.

Run from the project root::

    python -m pytest tests/test_checkpoints.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from fastapi.testclient import TestClient  # noqa: E402

import checkpoints  # noqa: E402
import routing  # noqa: E402
from src.api import routes  # noqa: E402
from src.api.app import app  # noqa: E402

client = TestClient(app)


def _task(name, skill, **extra):
    t = {"task": name, "required_skill": skill, "effort_hours": 10,
         "priority": 1, "dependencies": [], "is_required": True}
    t.update(extra)
    return t


def test_irreversible_raises_error_cost_with_provenance():
    plain = routing.route_tasks([_task("Emails", "Writing")])[0]
    hard = routing.route_tasks([_task("Emails", "Writing", irreversible=True)])[0]
    assert hard["irreversible"] is True
    assert hard["scores"]["error_cost"] == plain["scores"]["error_cost"] + 1
    prov = {p["field_name"]: p for p in hard["score_provenance"]}
    assert prov["error_cost"]["irreversibility_adjustment"] == 1
    assert "hard to undo" in prov["error_cost"]["explanation"]


def test_plan_tiers_no_delegate_sampling_and_midstream():
    records = routing.route_tasks([
        _task("Positioning", "Strategy"),                 # HUMAN_ONLY profile
        _task("Format variants", "Documentation"),        # AI_ONLY, repetitive
        _task("Launch email", "Writing", irreversible=True),  # AI-ish + hard to undo
        _task("Weld hull", "underwater welding"),         # unknown -> ESCALATE
    ])
    plan = checkpoints.build_checkpoint_plan(records)
    assert [n["task"] for n in plan["no_delegate"]] == ["Positioning"]
    assert [u["task"] for u in plan["undecided"]] == ["Weld hull"]
    by_task = {c["task"]: c for c in plan["checkpoints"]}
    assert by_task["Format variants"]["checkpoint"] == "sampling_audit"
    # Irreversible -> high-risk mid-stream checkpoint AND a release gate.
    assert by_task["Launch email"]["checkpoint"] == "midstream_and_final"
    assert [g["task"] for g in plan["release_gates"]] == ["Launch email"]
    assert "human-only" in plan["summary"]


def test_critical_path_counts_as_high_risk():
    records = routing.route_tasks([_task("Format variants", "Documentation")])
    relaxed = checkpoints.build_checkpoint_plan(records)
    critical = checkpoints.build_checkpoint_plan(
        records, critical_tasks=["Format variants"])
    assert relaxed["checkpoints"][0]["checkpoint"] == "sampling_audit"
    assert critical["checkpoints"][0]["checkpoint"] == "midstream_and_final"


def test_rubber_stamping_warning_on_heavy_review_load():
    records = routing.route_tasks([_task("Emails", "Writing")])
    quiet = checkpoints.build_checkpoint_plan(records, burden={
        "review_burden_hours": 5.0,
        "reviewer_bottleneck": {"human_capacity_hours": 100.0},
    })
    loud = checkpoints.build_checkpoint_plan(records, burden={
        "review_burden_hours": 30.0,
        "reviewer_bottleneck": {"human_capacity_hours": 100.0},
    })
    assert quiet["rubber_stamping_warning"] is None
    assert "rubber-stamping" in (loud["rubber_stamping_warning"] or "")


def test_project_simulation_returns_checkpoint_plan():
    routes._reset_active_roster()
    client.post("/employees/use-demo")
    body = {
        "project_name": "P", "project_goal": "G",
        "optimization_objective": "balanced",
        "team_constraints": {"max_humans_per_team": 5},
        "tasks": [
            _task("Positioning", "Strategy"),
            _task("Launch email", "Writing", irreversible=True),
        ],
        "current_team_human_names": ["Sarah", "Alex"],
        "current_team_ai_agent_names": [],
    }
    r = client.post("/simulate/project", json=body)
    assert r.status_code == 200, r.text
    plan = r.json()["checkpoint_plan"]
    assert plan["summary"]
    assert [g["task"] for g in plan["release_gates"]] == ["Launch email"]
    assert any(n["task"] == "Positioning" for n in plan["no_delegate"])
    routes._reset_active_roster()


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
    print("\nAll checkpoint tests passed.")
