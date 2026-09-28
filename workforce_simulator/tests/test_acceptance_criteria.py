"""Tests for per-task acceptance criteria (expected_output surfaced end to end).

The brief-drafting AI already produces ``expected_output`` per task; these
tests verify it now travels through the engine and API instead of being
dropped: routing records carry it as ``acceptance_criteria`` (so reviewers of
AI output know what to check), and schedule rows carry it too. Tasks without
one still work (None, never an error).

Run from the project root::

    python -m pytest tests/test_acceptance_criteria.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from fastapi.testclient import TestClient  # noqa: E402

import project_mode  # noqa: E402
import routing  # noqa: E402
from src.api import routes  # noqa: E402
from src.api.app import app  # noqa: E402

client = TestClient(app)

CRITERION = "Approved messaging framework with core message, pillars, and tone."


def _task(name, skill, expected=None):
    t = {"task": name, "required_skill": skill, "effort_hours": 10,
         "priority": 1, "dependencies": [], "is_required": True}
    if expected is not None:
        t["expected_output"] = expected
    return t


def test_routing_record_carries_acceptance_criteria():
    records = routing.route_tasks([
        _task("Messaging framework", "Writing", CRITERION),
        _task("QA pass", "QA"),  # none declared
    ])
    assert records[0]["acceptance_criteria"] == CRITERION
    assert records[1]["acceptance_criteria"] is None


def test_tasks_from_request_keeps_expected_output():
    tasks = project_mode.tasks_from_request([
        _task("A", "Writing", "  " + CRITERION + "  "),
        _task("B", "QA"),
    ])
    assert tasks[0].expected_output == CRITERION  # trimmed
    assert tasks[1].expected_output == ""


def test_project_simulation_round_trips_acceptance_criteria():
    routes._reset_active_roster()
    client.post("/employees/use-demo")
    body = {
        "project_name": "P",
        "project_goal": "G",
        "optimization_objective": "balanced",
        "team_constraints": {"max_humans_per_team": 5},
        "tasks": [
            _task("Messaging framework", "Writing", CRITERION),
            _task("QA pass", "QA"),
        ],
        "current_team_human_names": ["Sarah", "Alex"],
        "current_team_ai_agent_names": [],
    }
    r = client.post("/simulate/project", json=body)
    assert r.status_code == 200, r.text
    res = r.json()
    # Routing rows carry the criterion (reviewers of AI output check it).
    by_task = {row["task"]: row for row in res["task_routing"]}
    assert by_task["Messaging framework"]["acceptance_criteria"] == CRITERION
    assert by_task["QA pass"]["acceptance_criteria"] is None
    # Every option's schedule rows carry it too.
    for key, opt in res["options"].items():
        sched = {s["task"]: s for s in opt["task_schedule"]}
        assert sched["Messaging framework"]["acceptance_criteria"] == CRITERION, key
        assert sched["QA pass"]["acceptance_criteria"] is None, key
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
    print("\nAll acceptance-criteria tests passed.")
