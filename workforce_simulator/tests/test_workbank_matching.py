"""Tests for the read-only WORKBank matching preview.

Run from the project root with::

    python -m pytest tests/test_workbank_matching.py
    # or directly:
    python tests/test_workbank_matching.py
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

import workbank_matching  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "workbank", "workbank_normalized.json")


def _normalized() -> dict:
    with open(FIXTURE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _match(task: dict) -> dict:
    return workbank_matching.match_tasks([task], _normalized())[0]


# ---------------------------------------------------------------------------
# Confidence tiers
# ---------------------------------------------------------------------------

def test_exact_task_match_is_high():
    m = _match({
        "task": "Write unit tests for a module",
        "required_skill": "testing",
        "task_type": "coding",
    })
    assert m["matched_workbank_task_id"] == "WB-1"
    assert m["match_confidence"] == "HIGH"
    assert m["match_score"] >= 0.70


def test_similar_wording_is_medium_or_high():
    m = _match({
        "task": "Create automated unit tests for the billing module",
        "required_skill": "testing",
        "task_type": "coding",
    })
    assert m["matched_workbank_task_id"] == "WB-1"
    assert m["match_confidence"] in ("MEDIUM", "HIGH")
    assert m["match_score"] >= 0.45


def test_unrelated_task_is_low():
    m = _match({
        "task": "Negotiate annual vendor contract pricing",
        "required_skill": "negotiation",
        "task_type": "operations",
    })
    assert m["match_confidence"] == "LOW"
    assert m["match_score"] < 0.45


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

_MATCH_KEYS = {
    "project_task_id", "project_task_name", "matched_workbank_task_id",
    "matched_task_text", "matched_occupation_title", "matched_task_type",
    "match_score", "match_confidence", "match_method", "explanation",
    "candidate_matches",
}


def test_match_result_has_expected_structure():
    m = _match({"task": "Write unit tests for a module", "required_skill": "testing"})
    assert set(m.keys()) == _MATCH_KEYS
    assert m["match_method"]
    assert m["explanation"]
    # Top-3 candidate matches when available (the fixture has three tasks).
    assert 1 <= len(m["candidate_matches"]) <= 3
    cand = m["candidate_matches"][0]
    for key in ("matched_workbank_task_id", "matched_task_text",
                "matched_occupation_title", "matched_task_type",
                "match_score", "match_confidence"):
        assert key in cand
    # Candidates are ordered best-first.
    scores = [c["match_score"] for c in m["candidate_matches"]]
    assert scores == sorted(scores, reverse=True)


def test_no_imported_workbank_returns_low_unmatched():
    m = workbank_matching.match_tasks(
        [{"task": "Write unit tests for a module"}],
        {"normalized_priors": []},
    )[0]
    assert m["matched_workbank_task_id"] is None
    assert m["match_confidence"] == "LOW"
    assert m["match_score"] == 0.0


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from src.api.app import app  # noqa: E402

client = TestClient(app)


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


def test_match_endpoint_returns_expected_structure():
    tasks = client.get("/tasks").json()
    r = client.post("/priors/workbank/match-tasks", json={"tasks": tasks})
    assert r.status_code == 200
    body = r.json()
    assert "import_status" in body
    assert len(body["matches"]) == len(tasks)
    for m in body["matches"]:
        assert set(m.keys()) == _MATCH_KEYS
        assert m["match_confidence"] in ("HIGH", "MEDIUM", "LOW")
        assert len(m["candidate_matches"]) <= 3


def test_match_endpoint_rejects_empty():
    r = client.post("/priors/workbank/match-tasks", json={"tasks": []})
    assert r.status_code == 422


def test_project_response_includes_workbank_match_preview():
    body = client.post("/simulate/project", json=_sample_project()).json()
    assert body["task_routing"], "expected task routing rows"
    for row in body["task_routing"]:
        assert "workbank_match_preview" in row
        preview = row["workbank_match_preview"]
        for key in ("matched_workbank_task_id", "matched_task_text",
                    "matched_occupation_title", "match_score",
                    "match_confidence", "explanation"):
            assert key in preview


def test_workbank_preview_does_not_change_routing_or_options():
    # The preview must not alter routing decisions or the five options.
    body = client.post("/simulate/project", json=_sample_project()).json()
    decisions = {r["task"]: r["routing"] for r in body["task_routing"]}
    assert decisions["Documentation"] == "AI_ONLY"
    assert decisions["Product strategy"] == "HUMAN_ONLY"
    assert len(body["options"]) == 6
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
    print("\nAll WORKBank matching tests passed.")
