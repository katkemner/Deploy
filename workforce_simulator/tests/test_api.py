"""API tests for the workforce simulator FastAPI layer.

Run from the project root with::

    python -m pytest tests/test_api.py
    # or directly:
    python tests/test_api.py

Uses FastAPI's TestClient (no server needs to be running).
"""

import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from fastapi.testclient import TestClient  # noqa: E402

from src.api.app import app  # noqa: E402

client = TestClient(app)


# ---------------------------------------------------------------------------
# Health & data endpoints
# ---------------------------------------------------------------------------

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_get_employees():
    r = client.get("/employees")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 10
    names = {e["name"] for e in body}
    assert "Sarah" in names and "Alex" in names
    sarah = next(e for e in body if e["name"] == "Sarah")
    assert sarah["available_hours"] == 20
    assert "UX" in sarah["skills"]


def test_get_ai_agents():
    r = client.get("/ai-agents")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    planner = next(a for a in body if a["name"] == "AI Project Planner")
    assert planner["speed_multiplier"] == 1.25
    assert "Planning" in planner["capabilities"]


def test_get_tasks():
    r = client.get("/tasks")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 10
    qa = next(t for t in body if t["task"] == "QA testing")
    assert qa["dependencies"] == ["Frontend build", "Backend API"]
    assert qa["is_required"] is True


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def test_simulate_returns_top5():
    r = client.post("/simulate")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 5
    assert [x["rank"] for x in body] == [1, 2, 3, 4, 5]
    # All ranked teams are valid and have a critical path + explanation.
    for x in body:
        assert x["is_valid_team"] is True
        assert x["critical_path"]
        assert x["plain_english_explanation"]


def test_simulate_manual_team_current_best():
    payload = {
        "human_names": ["Sarah", "Maya", "Priya", "Alex", "Casey"],
        "ai_agent_names": ["AI Research Agent", "AI QA Reviewer"],
    }
    r = client.post("/simulate/manual-team", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["team_members"] == ["Sarah", "Maya", "Priya", "Alex", "Casey"]
    assert body["ai_agents"] == ["AI Research Agent", "AI QA Reviewer"]
    assert body["is_valid_team"] is True
    assert body["required_skill_coverage_score"] == 100.0
    # Task schedule is fully populated.
    assert len(body["task_schedule"]) == 10
    item = body["task_schedule"][0]
    for key in ("task", "assigned_to", "start_time", "finish_time",
                "is_on_critical_path", "adjusted_effort_hours"):
        assert key in item
    assert body["critical_path"]


def test_simulate_manual_team_rejects_unknown_name():
    payload = {"human_names": ["Sarah", "Nobody"], "ai_agent_names": []}
    r = client.post("/simulate/manual-team", json=payload)
    assert r.status_code == 400
    assert "Nobody" in r.json()["detail"]["unknown_humans"]


def test_simulate_manual_team_requires_members():
    r = client.post(
        "/simulate/manual-team",
        json={"human_names": [], "ai_agent_names": []},
    )
    assert r.status_code == 422  # schema validation error


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def _valid_config():
    return {
        "weights": {
            "skill_coverage": 30, "capacity_fit": 20, "productivity": 20,
            "workload_balance": 15, "cost_efficiency": 10, "low_risk": 5,
        },
        "require_full_required_skill_coverage": True,
        "min_humans_per_team": 2, "max_humans_per_team": 5,
        "min_ai_agents_per_team": 0, "max_ai_agents_per_team": 2,
    }


def test_get_config():
    r = client.get("/config")
    assert r.status_code == 200
    assert "weights" in r.json()


def test_post_config_roundtrip():
    original = client.get("/config").json()
    try:
        cfg = _valid_config()
        cfg["weights"]["cost_efficiency"] = 40
        r = client.post("/config", json=cfg)
        assert r.status_code == 200
        assert r.json()["weights"]["cost_efficiency"] == 40
        # Persisted.
        assert client.get("/config").json()["weights"]["cost_efficiency"] == 40
    finally:
        # Restore the original config so other tests/runs are unaffected.
        client.post("/config", json=original)


def test_post_config_rejects_negative_weight():
    cfg = _valid_config()
    cfg["weights"]["productivity"] = -5
    r = client.post("/config", json=cfg)
    assert r.status_code == 422


def test_post_config_rejects_impossible_constraints():
    cfg = _valid_config()
    cfg["min_humans_per_team"] = 6
    cfg["max_humans_per_team"] = 2
    r = client.post("/config", json=cfg)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

def test_upload_employees_rejects_malformed_csv():
    bad = b"this,is\nnot,the,right,columns\n"
    r = client.post(
        "/upload/employees",
        files={"file": ("bad.csv", io.BytesIO(bad), "text/csv")},
    )
    assert r.status_code == 400


def test_upload_employees_roundtrip():
    # Read current file, re-upload it unchanged, and confirm acceptance.
    path = os.path.join(ROOT, "data", "employees.csv")
    with open(path, "rb") as fh:
        content = fh.read()
    r = client.post(
        "/upload/employees",
        files={"file": ("employees.csv", io.BytesIO(content), "text/csv")},
    )
    assert r.status_code == 200
    assert r.json()["rows"] == 10


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

def test_outputs_latest_after_simulate():
    client.post("/simulate")  # ensure results.json exists
    r = client.get("/outputs/latest")
    assert r.status_code == 200
    assert len(r.json()) == 5


# ---------------------------------------------------------------------------
# Project Mode (POST /simulate/project)
# ---------------------------------------------------------------------------

def _sample_project(**overrides):
    """Build a project scenario from the current sample tasks."""
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


def test_project_simulation_returns_all_options():
    r = client.post("/simulate/project", json=_sample_project())
    assert r.status_code == 200
    body = r.json()
    # All five decision options are present.
    for key in (
        "current_team",
        "ai_assisted_current_team",
        "recommended_balanced_team",
        "fastest_valid_team",
        "lowest_cost_valid_team",
    ):
        assert key in body["options"], key
        assert "total_score" in body["options"][key]
    # Comparison table has one row per option and a recommendation summary.
    assert len(body["comparison_table"]) == 5
    assert body["recommendation"]["recommended_option"] in body["options"]
    assert body["recommendation"]["summary_text"]
    assert body["recommendation"]["critical_path"]


def test_project_current_team_returned_exactly():
    r = client.post("/simulate/project", json=_sample_project())
    current = r.json()["options"]["current_team"]
    assert current["team_members"] == ["Sarah", "Maya", "Priya", "Alex", "Casey"]
    assert current["ai_agents"] == ["AI Research Agent", "AI QA Reviewer"]


def test_project_ai_assisted_team_returned():
    # Current team with no AI agents -> the assisted option should add some.
    r = client.post(
        "/simulate/project",
        json=_sample_project(current_team_ai_agent_names=[]),
    )
    assisted = r.json()["options"]["ai_assisted_current_team"]
    assert "ai_agents_added" in assisted
    assert len(assisted["ai_agents_added"]) >= 1
    assert len(assisted["ai_assist_notes"]) == len(assisted["ai_agents_added"])


def test_project_recommended_balanced_is_valid():
    r = client.post("/simulate/project", json=_sample_project())
    balanced = r.json()["options"]["recommended_balanced_team"]
    assert balanced["is_valid_team"] is True
    assert balanced["missing_required_skills"] == []


def test_project_fastest_is_shortest_among_options():
    r = client.post(
        "/simulate/project", json=_sample_project(optimization_objective="fastest")
    )
    body = r.json()
    fastest = body["options"]["fastest_valid_team"]
    balanced = body["options"]["recommended_balanced_team"]
    # Fastest valid team is no slower than the balanced team.
    assert fastest["estimated_duration"] <= balanced["estimated_duration"]
    assert body["recommendation"]["recommended_option"] == "fastest_valid_team"


def test_project_lowest_cost_is_cheapest_among_options():
    r = client.post(
        "/simulate/project", json=_sample_project(optimization_objective="lowest_cost")
    )
    body = r.json()
    cheapest = body["options"]["lowest_cost_valid_team"]
    balanced = body["options"]["recommended_balanced_team"]
    assert cheapest["estimated_cost"] <= balanced["estimated_cost"]
    assert body["recommendation"]["recommended_option"] == "lowest_cost_valid_team"


def test_project_invalid_current_team_is_handled():
    r = client.post(
        "/simulate/project",
        json=_sample_project(current_team_human_names=["Sarah", "Ghost"]),
    )
    assert r.status_code == 400
    assert "Ghost" in r.json()["detail"]


def test_project_json_dependencies_respected():
    # Two tasks where B depends on A; B must start no earlier than A finishes.
    tasks = [
        {"task": "A", "required_skill": "Python", "effort_hours": 10,
         "priority": 1, "dependencies": [], "is_required": True},
        {"task": "B", "required_skill": "Python", "effort_hours": 10,
         "priority": 1, "dependencies": ["A"], "is_required": True},
    ]
    payload = {
        "tasks": tasks,
        "optimization_objective": "balanced",
        "current_team_human_names": ["John", "Casey"],
        "current_team_ai_agent_names": [],
    }
    r = client.post("/simulate/project", json=payload)
    assert r.status_code == 200
    schedule = r.json()["options"]["current_team"]["task_schedule"]
    by_task = {s["task"]: s for s in schedule}
    assert by_task["B"]["start_time"] >= by_task["A"]["finish_time"]


def test_project_rejects_empty_tasks():
    r = client.post(
        "/simulate/project",
        json={"tasks": [], "current_team_human_names": ["Sarah"]},
    )
    assert r.status_code == 422  # schema requires at least one task


# ---------------------------------------------------------------------------
# Task-level routing
# ---------------------------------------------------------------------------

def test_route_tasks_endpoint():
    tasks = client.get("/tasks").json()
    r = client.post("/route/tasks", json={"tasks": tasks})
    assert r.status_code == 200
    body = r.json()
    assert len(body["task_routing"]) == len(tasks)
    decisions = {row["routing"] for row in body["task_routing"]}
    # Every decision is one of the five valid routing labels.
    assert decisions <= {
        "AI_ONLY", "AI_FIRST_HUMAN_REVIEW", "HUMAN_FIRST_AI_ASSIST",
        "HUMAN_ONLY", "ESCALATE",
    }
    # Each task carries the nine 1-5 suitability scores + an explanation.
    first = body["task_routing"][0]
    assert len(first["scores"]) == 9
    assert first["explanation"]
    summary = body["routing_summary"]
    assert "net_ai_time_saved" in summary
    assert "routing_distribution" in summary


def test_route_tasks_rejects_empty():
    r = client.post("/route/tasks", json={"tasks": []})
    assert r.status_code == 422


def test_project_includes_routing_and_review_burden():
    payload = _sample_project()
    r = client.post("/simulate/project", json=payload)
    body = r.json()
    # Routing table has one row per task; summary is present.
    assert len(body["task_routing"]) == len(payload["tasks"])
    assert "routing_summary" in body

    # Comparison rows carry review burden, rework, and bottleneck flag.
    row = body["comparison_table"][0]
    for key in ("review_burden_hours", "expected_rework_hours",
                "net_ai_time_saved", "reviewer_bottleneck"):
        assert key in row

    # Each option exposes its reviewer-bottleneck detail.
    opt = body["options"]["ai_assisted_current_team"]
    assert "reviewer_bottleneck" in opt
    assert "message" in opt["reviewer_bottleneck"]

    # Recommendation explains whether AI saves time or shifts it.
    assert body["recommendation"]["ai_time_verdict"]


def test_project_no_ai_option_has_no_review_burden():
    # A current team with no AI agents should carry zero AI review burden.
    r = client.post(
        "/simulate/project",
        json=_sample_project(
            current_team_human_names=["Sarah", "Maya"],
            current_team_ai_agent_names=[],
        ),
    )
    current = r.json()["options"]["current_team"]
    assert current["review_burden_hours"] == 0.0
    assert current["reviewer_bottleneck"]["is_bottleneck"] is False


# ---------------------------------------------------------------------------
# Monte-Carlo uncertainty (POST /simulate/uncertainty)
# ---------------------------------------------------------------------------

def _uncertainty_payload(**overrides):
    tasks = client.get("/tasks").json()
    payload = {
        "tasks": tasks,
        "human_names": ["Sarah", "Maya", "Priya", "Alex", "Casey"],
        "ai_agent_names": ["AI Research Agent", "AI QA Reviewer"],
        "iterations": 200,
        "seed": 42,
        "deadline_target_hours": 110,
        "budget_target": 20000,
    }
    payload.update(overrides)
    return payload


def test_uncertainty_returns_statistics():
    r = client.post("/simulate/uncertainty", json=_uncertainty_payload())
    assert r.status_code == 200
    body = r.json()
    for key in ("duration", "cost"):
        s = body[key]
        assert s["min"] <= s["p10"] <= s["p50"] <= s["p90"] <= s["max"]
        assert len(s["histogram"]) >= 1
    assert 0.0 <= body["probability_meets_deadline"] <= 1.0
    assert 0.0 <= body["probability_within_budget"] <= 1.0
    assert len(body["task_ranges"]) == len(_uncertainty_payload()["tasks"])


def test_uncertainty_is_reproducible_via_api():
    a = client.post("/simulate/uncertainty", json=_uncertainty_payload(seed=11)).json()
    b = client.post("/simulate/uncertainty", json=_uncertainty_payload(seed=11)).json()
    assert a["duration"] == b["duration"]
    assert a["cost"] == b["cost"]


def test_uncertainty_rejects_unknown_member():
    r = client.post(
        "/simulate/uncertainty", json=_uncertainty_payload(human_names=["Ghost"])
    )
    assert r.status_code == 400
    assert "Ghost" in r.json()["detail"]


def test_uncertainty_rejects_empty_team():
    r = client.post(
        "/simulate/uncertainty",
        json=_uncertainty_payload(human_names=[], ai_agent_names=[]),
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Routing provenance (API)
# ---------------------------------------------------------------------------

_VALID_SOURCES = {"MANUAL_INPUT", "EXISTING_HEURISTIC", "DEFAULT_FALLBACK"}
_PROV_KEYS = {
    "field_name", "value", "source_type", "source_name", "confidence", "explanation",
}


def test_route_tasks_response_includes_provenance():
    tasks = client.get("/tasks").json()
    rows = client.post("/route/tasks", json={"tasks": tasks}).json()["task_routing"]
    for row in rows:
        assert "score_provenance" in row and "route_provenance" in row
        assert len(row["score_provenance"]) == 9
        assert len(row["route_provenance"]) == 4
        for p in row["score_provenance"] + row["route_provenance"]:
            assert set(p.keys()) == _PROV_KEYS
            assert p["source_type"] in _VALID_SOURCES


def test_route_tasks_provenance_marks_manual_override():
    tasks = client.get("/tasks").json()
    t = dict(tasks[0])
    t["routing_scores"] = {"ai_capability_fit": 5}
    row = client.post("/route/tasks", json={"tasks": [t]}).json()["task_routing"][0]
    by_field = {p["field_name"]: p for p in row["score_provenance"]}
    assert by_field["ai_capability_fit"]["source_type"] == "MANUAL_INPUT"
    assert by_field["verification_ease"]["source_type"] == "DEFAULT_FALLBACK"


def test_project_mode_routing_has_provenance_and_still_works():
    body = client.post("/simulate/project", json=_sample_project()).json()
    # Project Mode still returns all five options (behaviour unchanged).
    assert len(body["options"]) == 5
    assert body["recommendation"]["recommended_option"] in body["options"]
    # And its task routing now carries provenance.
    row = body["task_routing"][0]
    assert "score_provenance" in row and "route_provenance" in row
    assert all(
        p["source_type"] in _VALID_SOURCES
        for p in row["score_provenance"] + row["route_provenance"]
    )


# ---------------------------------------------------------------------------
# Evidence priors (GET /priors) + unchanged behaviour
# ---------------------------------------------------------------------------

def test_get_priors_returns_expected_sections():
    r = client.get("/priors")
    assert r.status_code == 200
    body = r.json()
    for section in (
        "source_weights", "evidence_priors",
        "task_routing_priors", "hybrid_guardrail_priors",
    ):
        assert section in body and isinstance(body[section], list)
    assert body["representative_seed"] is True
    assert len(body["source_weights"]) == 5


def test_priors_do_not_change_routing_behaviour():
    # Routing decisions on the sample tasks are unchanged by adding priors.
    tasks = client.get("/tasks").json()
    rows = client.post("/route/tasks", json={"tasks": tasks}).json()["task_routing"]
    decisions = {r["task"]: r["routing"] for r in rows}
    assert decisions["Documentation"] == "AI_ONLY"
    assert decisions["Product strategy"] == "HUMAN_ONLY"
    assert decisions["User research"] == "AI_FIRST_HUMAN_REVIEW"


def test_priors_do_not_change_project_mode():
    # Project Mode still returns the five options and a recommendation.
    body = client.post("/simulate/project", json=_sample_project()).json()
    assert len(body["options"]) == 5
    assert body["recommendation"]["recommended_option"] in body["options"]


# ---------------------------------------------------------------------------
# Prior matching preview (POST /priors/match-tasks) + unchanged behaviour
# ---------------------------------------------------------------------------

def test_match_tasks_returns_expected_structure():
    tasks = client.get("/tasks").json()
    r = client.post("/priors/match-tasks", json={"tasks": tasks})
    assert r.status_code == 200
    matches = r.json()["matches"]
    assert len(matches) == len(tasks)
    for m in matches:
        for key in ("project_task_id", "matched_prior_id", "matched_prior_type",
                    "match_score", "match_confidence", "match_method",
                    "explanation", "candidates"):
            assert key in m
        assert m["match_confidence"] in ("HIGH", "MEDIUM", "LOW")
        assert len(m["candidates"]) <= 3


def test_match_tasks_exact_is_high_via_api():
    payload = {"tasks": [{
        "task": "QA", "required_skill": "QA", "effort_hours": 10,
        "task_type": "qa", "description": "qa", "expected_output": "qa",
    }]}
    m = client.post("/priors/match-tasks", json=payload).json()["matches"][0]
    assert m["matched_prior_id"] == "TRP-QA"
    assert m["match_confidence"] == "HIGH"


def test_match_tasks_rejects_empty():
    r = client.post("/priors/match-tasks", json={"tasks": []})
    assert r.status_code == 422


def test_project_response_has_prior_match_preview_fields():
    body = client.post("/simulate/project", json=_sample_project()).json()
    row = next(r for r in body["task_routing"] if r["task"] == "Documentation")
    assert "prior_match_preview" in row
    assert "prior_match_confidence" in row
    assert "prior_match_explanation" in row
    # The preview must NOT change the routing decision.
    assert row["routing"] == "AI_ONLY"


def test_prior_matching_does_not_change_routing_or_project_results():
    tasks = client.get("/tasks").json()
    # Routing decisions unchanged.
    rows = client.post("/route/tasks", json={"tasks": tasks}).json()["task_routing"]
    decisions = {r["task"]: r["routing"] for r in rows}
    assert decisions["Documentation"] == "AI_ONLY"
    assert decisions["Product strategy"] == "HUMAN_ONLY"
    # Project Mode options/recommendation unchanged in shape.
    body = client.post("/simulate/project", json=_sample_project()).json()
    assert len(body["options"]) == 5
    assert body["recommendation"]["recommended_option"] in body["options"]


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
    print("\nAll API tests passed.")
