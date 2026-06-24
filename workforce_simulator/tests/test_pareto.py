"""Tests for the Pareto-front preview (read-only tradeoff view).

Covers the dominance logic at the engine level and the additive API output on
Project Mode, plus the guarantee that the recommendation is unchanged.

Run from the project root with::

    python -m pytest tests/test_pareto.py
    # or directly:
    python tests/test_pareto.py
"""

import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

import pareto  # noqa: E402


# ---------------------------------------------------------------------------
# Stubs: a minimal "result" with just the fields objective_values reads.
# ---------------------------------------------------------------------------

def _result(duration, cost, human_hours, risk, coverage, productivity,
            balance, confidence):
    human = SimpleNamespace(name="H")
    return SimpleNamespace(
        team=SimpleNamespace(humans=[human]),
        member_hours={"H": human_hours},
        estimated_duration=duration,
        estimated_cost=cost,
        risk_score=risk,
        required_skill_coverage_score=coverage,
        productivity_score=productivity,
        workload_balance_score=balance,
        confidence_score=confidence,
    )


def _burden(review, rework):
    return {"review_burden_hours": review, "expected_rework_hours": rework}


# A clearly-best option, a clearly-dominated option, and a tradeoff option.
def _scenario():
    options = {
        # best on everything (or tied): dominates "weak".
        "strong": _result(10, 100, 50, 5, 100, 90, 90, 90),
        # worse on every objective than "strong": dominated.
        "weak": _result(20, 200, 80, 40, 80, 60, 60, 60),
        # fastest but very expensive: a genuine tradeoff vs "strong".
        "fast_pricey": _result(5, 500, 50, 5, 100, 90, 90, 90),
    }
    burdens = {
        "strong": _burden(10, 5),
        "weak": _burden(30, 20),
        "fast_pricey": _burden(10, 5),
    }
    labels = {"strong": "Strong", "weak": "Weak", "fast_pricey": "Fast Pricey"}
    return options, burdens, labels


# ---------------------------------------------------------------------------
# Dominance primitives
# ---------------------------------------------------------------------------

def test_dominates_true_when_better_or_equal_and_strictly_better():
    a = {k: (1 if d == "min" else 100) for k, d, _l, _p in pareto.OBJECTIVES}
    b = {k: (2 if d == "min" else 50) for k, d, _l, _p in pareto.OBJECTIVES}
    assert pareto.dominates(a, b) is True
    assert pareto.dominates(b, a) is False


def test_dominates_false_when_equal():
    a = {k: (1 if d == "min" else 100) for k, d, _l, _p in pareto.OBJECTIVES}
    b = dict(a)
    # Equal on all objectives -> neither strictly better -> no domination.
    assert pareto.dominates(a, b) is False
    assert pareto.dominates(b, a) is False


def test_dominates_false_on_tradeoff():
    a = dict(duration=5, cost=500, human_hours=50, review_hours=10,
             rework_hours=5, risk=5, skill_coverage=100, productivity=90,
             workload_balance=90, confidence=90)
    b = dict(duration=10, cost=100, human_hours=50, review_hours=10,
             rework_hours=5, risk=5, skill_coverage=100, productivity=90,
             workload_balance=90, confidence=90)
    # a is faster, b is cheaper -> neither dominates.
    assert pareto.dominates(a, b) is False
    assert pareto.dominates(b, a) is False


# ---------------------------------------------------------------------------
# build_pareto_front
# ---------------------------------------------------------------------------

def test_dominated_option_marked_non_pareto():
    options, burdens, labels = _scenario()
    front = {p.option_id: p for p in
             pareto.build_pareto_front(options, burdens, labels)}
    assert front["weak"].is_pareto_optimal is False
    assert "strong" in front["weak"].dominated_by
    # The dominating option lists the dominated one.
    assert "weak" in front["strong"].dominates


def test_non_dominated_options_marked_pareto():
    options, burdens, labels = _scenario()
    front = {p.option_id: p for p in
             pareto.build_pareto_front(options, burdens, labels)}
    assert front["strong"].is_pareto_optimal is True
    assert front["fast_pricey"].is_pareto_optimal is True
    assert front["strong"].dominated_by == []
    assert front["fast_pricey"].dominated_by == []


def test_objective_values_extracted_from_outputs():
    options, burdens, labels = _scenario()
    front = {p.option_id: p for p in
             pareto.build_pareto_front(options, burdens, labels)}
    ov = front["strong"].objective_values
    assert ov["duration"] == 10
    assert ov["cost"] == 100
    assert ov["human_hours"] == 50
    assert ov["review_hours"] == 10
    assert ov["rework_hours"] == 5
    assert set(ov.keys()) == {k for k, _d, _l, _p in pareto.OBJECTIVES}


def test_tradeoff_summary_and_strengths():
    options, burdens, labels = _scenario()
    front = {p.option_id: p for p in
             pareto.build_pareto_front(options, burdens, labels)}
    # fast_pricey is uniquely fastest -> "fastest" appears in its summary.
    assert "fastest" in front["fast_pricey"].tradeoff_summary
    assert "duration" in front["fast_pricey"].strengths
    # weak is dominated -> summary says so.
    assert "Dominated by" in front["weak"].tradeoff_summary


def test_explanation_warns_when_recommendation_dominated():
    options, burdens, labels = _scenario()
    front = pareto.build_pareto_front(options, burdens, labels)
    # Recommend the dominated option -> explanation must warn (rec unchanged).
    text = pareto.explain(front, "weak", labels)
    assert "WARNING" in text
    assert "Weak" in text


def test_explanation_no_warning_when_recommendation_optimal():
    options, burdens, labels = _scenario()
    front = pareto.build_pareto_front(options, burdens, labels)
    text = pareto.explain(front, "strong", labels)
    assert "WARNING" not in text


# ---------------------------------------------------------------------------
# API: additive Project Mode output + unchanged recommendation
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from src.api.app import app  # noqa: E402

client = TestClient(app)


def _sample_project(**overrides):
    tasks = client.get("/tasks").json()
    payload = {
        "project_name": "Sample", "project_goal": "Ship",
        "deadline_target_hours": 90, "budget_target": 15000,
        "optimization_objective": "balanced",
        "tasks": tasks,
        "current_team_human_names": ["Sarah", "Maya", "Priya", "Alex", "Casey"],
        "current_team_ai_agent_names": ["AI Research Agent", "AI QA Reviewer"],
    }
    payload.update(overrides)
    return payload


_PARETO_KEYS = {
    "option_id", "option_name", "is_pareto_optimal", "dominated_by",
    "dominates", "tradeoff_summary", "objective_values", "strengths",
    "weaknesses",
}


def test_project_response_includes_pareto_front():
    body = client.post("/simulate/project", json=_sample_project()).json()
    assert "pareto_front" in body
    assert "pareto_explanation" in body
    assert isinstance(body["pareto_explanation"], str) and body["pareto_explanation"]
    # One ParetoOption per staffing option, each with the documented shape.
    assert len(body["pareto_front"]) == len(body["options"])
    for p in body["pareto_front"]:
        assert set(p.keys()) == _PARETO_KEYS
        assert len(p["objective_values"]) == 10
    # At least one option is always non-dominated.
    assert any(p["is_pareto_optimal"] for p in body["pareto_front"])


def test_recommended_option_is_in_pareto_front():
    body = client.post("/simulate/project", json=_sample_project()).json()
    rec = body["recommendation"]["recommended_option"]
    ids = {p["option_id"] for p in body["pareto_front"]}
    assert rec in ids


def test_recommendation_unchanged_by_pareto():
    # The recommendation for each objective is exactly what Project Mode chose
    # before Pareto existed (Pareto is additive and must not re-rank).
    fastest = client.post(
        "/simulate/project", json=_sample_project(optimization_objective="fastest")
    ).json()
    assert fastest["recommendation"]["recommended_option"] == "fastest_valid_team"

    cheapest = client.post(
        "/simulate/project", json=_sample_project(optimization_objective="lowest_cost")
    ).json()
    assert cheapest["recommendation"]["recommended_option"] == "lowest_cost_valid_team"


def test_pareto_front_is_read_only_options_unchanged():
    body = client.post("/simulate/project", json=_sample_project()).json()
    # Project Mode still returns its five options + recommendation intact.
    assert len(body["options"]) == 5
    assert body["recommendation"]["recommended_option"] in body["options"]
    assert len(body["comparison_table"]) == 5


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
    print("\nAll Pareto tests passed.")
