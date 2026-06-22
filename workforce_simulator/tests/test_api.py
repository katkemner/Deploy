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
