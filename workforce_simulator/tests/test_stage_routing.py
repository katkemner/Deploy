"""Tests for decision-cycle stage tags and stage priors in routing.

A task's optional ``stage`` (attention / intelligence / design / choice /
implementation / feedback) nudges its 1-5 suitability scores by at most one
point, with full provenance, before the routing rules run. Choice-stage work
shifts toward humans (the evidence: decision tasks show negative human-AI
synergy), intelligence-stage work toward AI. Untagged tasks behave exactly
as before, and manual score overrides are never adjusted.

Run from the project root::

    python -m pytest tests/test_stage_routing.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from fastapi.testclient import TestClient  # noqa: E402

import routing  # noqa: E402
from models import STAGES  # noqa: E402
from src.api import routes  # noqa: E402
from src.api.app import app  # noqa: E402

client = TestClient(app)


def _task(name, skill, stage=None, **extra):
    t = {"task": name, "required_skill": skill, "effort_hours": 10,
         "priority": 1, "dependencies": [], "is_required": True}
    if stage is not None:
        t["stage"] = stage
    t.update(extra)
    return t


def test_untagged_task_routes_exactly_as_before():
    plain = routing.route_tasks([_task("Emails", "Writing")])[0]
    assert plain["stage"] is None
    # The demo writing profile is AI_ONLY territory; unchanged without a stage.
    assert plain["routing"] == routing.AI_ONLY


def test_choice_stage_pulls_decision_work_away_from_ai_only():
    # The "tagline misfire": commodity-writing profile + a choosing task.
    # Tagged as choice-stage, it must no longer be AI_ONLY.
    tagged = routing.route_tasks([_task("Select tagline", "Writing", "choice")])[0]
    assert tagged["stage"] == "choice"
    assert tagged["routing"] != routing.AI_ONLY
    # The nudges are visible: judgment up, AI fit down, with provenance notes.
    assert tagged["scores"]["human_judgment_need"] == 3  # was 2
    assert tagged["scores"]["ai_capability_fit"] == 4    # was 5
    prov = {p["field_name"]: p for p in tagged["score_provenance"]}
    assert "'choice' stage" in prov["ai_capability_fit"]["explanation"]
    assert prov["ai_capability_fit"]["stage_adjustment"] == -1


def test_intelligence_stage_boosts_ai_fit():
    # UX profile has ai_capability_fit 2; intelligence stage nudges it to 3.
    rec = routing.route_tasks([_task("Synthesize interviews", "UX", "intelligence")])[0]
    assert rec["scores"]["ai_capability_fit"] == 3
    prov = {p["field_name"]: p for p in rec["score_provenance"]}
    assert prov["ai_capability_fit"]["stage_adjustment"] == 1


def test_manual_override_is_never_stage_adjusted():
    rec = routing.route_tasks([
        _task("Select tagline", "Writing", "choice",
              routing_scores={"ai_capability_fit": 5}),
    ])[0]
    # The override wins untouched; non-overridden fields (which default to 3
    # whenever any override is supplied) still get the stage nudge: 3 + 1 = 4.
    assert rec["scores"]["ai_capability_fit"] == 5
    assert rec["scores"]["human_judgment_need"] == 4


def test_design_stage_is_deliberately_neutral():
    plain = routing.route_tasks([_task("Draft ads", "Writing")])[0]
    design = routing.route_tasks([_task("Draft ads", "Writing", "design")])[0]
    assert design["scores"] == plain["scores"]
    assert design["stage"] == "design"


def test_invalid_stage_rejected_by_api_and_ignored_by_engine():
    # Engine: unknown stage never nudges (defensive path).
    rec = routing.route_tasks([_task("Emails", "Writing", "brainstorm")])[0]
    assert rec["stage"] is None and rec["routing"] == routing.AI_ONLY
    # API: 422 with the allowed stages named.
    routes._reset_active_roster()
    client.post("/employees/use-demo")
    body = {
        "project_name": "P", "project_goal": "G",
        "optimization_objective": "balanced",
        "team_constraints": {"max_humans_per_team": 5},
        "tasks": [_task("Emails", "Writing", "brainstorm")],
        "current_team_human_names": ["Sarah"],
        "current_team_ai_agent_names": [],
    }
    r = client.post("/simulate/project", json=body)
    assert r.status_code == 422
    assert "stage must be one of" in r.text
    routes._reset_active_roster()


def test_stage_round_trips_through_project_simulation():
    routes._reset_active_roster()
    client.post("/employees/use-demo")
    body = {
        "project_name": "P", "project_goal": "G",
        "optimization_objective": "balanced",
        "team_constraints": {"max_humans_per_team": 5},
        "tasks": [
            _task("Select tagline", "Writing", "Choice"),  # any casing accepted
            _task("QA pass", "QA"),
        ],
        "current_team_human_names": ["Sarah", "Alex"],
        "current_team_ai_agent_names": [],
    }
    r = client.post("/simulate/project", json=body)
    assert r.status_code == 200, r.text
    rows = {row["task"]: row for row in r.json()["task_routing"]}
    assert rows["Select tagline"]["stage"] == "choice"
    assert rows["Select tagline"]["routing"] != routing.AI_ONLY
    assert rows["QA pass"]["stage"] is None
    routes._reset_active_roster()


def test_all_declared_stages_have_adjustment_entries():
    assert set(routing._STAGE_ADJUSTMENTS.keys()) == set(STAGES)


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
    print("\nAll stage-routing tests passed.")
