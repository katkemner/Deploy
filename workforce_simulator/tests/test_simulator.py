"""Simple tests for the workforce simulator.

Run from the project root with::

    python -m pytest tests/
    # or, without pytest installed:
    python tests/test_simulator.py

The tests cover the five areas the brief asks for: CSV loading, skill
matching, task assignment, score calculation, and top-5 ranking.
"""

import os
import sys

# Make ``src`` importable.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import scoring  # noqa: E402
from data_loader import load_all  # noqa: E402
from models import Worker, Task, Team, HUMAN, AI_AGENT  # noqa: E402
from simulator import assign_tasks, simulate_team  # noqa: E402
from optimizer import generate_teams, rank_teams  # noqa: E402

DATA_DIR = os.path.join(ROOT, "data")


# ---------------------------------------------------------------------------
# 1. CSV loading
# ---------------------------------------------------------------------------

def test_csv_loading():
    employees, ai_agents, tasks = load_all(DATA_DIR)
    assert len(employees) == 10
    assert len(ai_agents) == 3
    assert len(tasks) == 10

    sarah = next(e for e in employees if e.name == "Sarah")
    assert sarah.type == HUMAN
    assert sarah.speed_multiplier == 1.0
    assert sarah.available_hours == 20  # 30 capacity - 10 workload
    assert "UX" in sarah.skills

    planner = next(a for a in ai_agents if a.name == "AI Project Planner")
    assert planner.type == AI_AGENT
    assert planner.speed_multiplier == 1.25
    assert planner.workload_hours == 0


# ---------------------------------------------------------------------------
# 2. Skill matching
# ---------------------------------------------------------------------------

def test_skill_matching():
    w = Worker("X", HUMAN, "Dev", ["Python", "API"], 30, 0, 100, 8)
    assert w.has_skill("Python")
    assert w.has_skill("python")     # case-insensitive
    assert w.has_skill(" API ")      # whitespace tolerant
    assert not w.has_skill("React")


# ---------------------------------------------------------------------------
# 3. Task assignment
# ---------------------------------------------------------------------------

def test_task_assignment_picks_skilled_member():
    dev = Worker("Dev", HUMAN, "Dev", ["Python"], 30, 0, 100, 8)
    designer = Worker("Des", HUMAN, "Designer", ["UX"], 30, 0, 80, 8)
    team = Team(humans=[dev, designer])
    tasks = [
        Task("Build", "Python", 10, 1),
        Task("Design", "UX", 10, 1),
    ]
    assignments = assign_tasks(team, tasks)
    by_task = {a.task: a for a in assignments}
    assert by_task["Build"].assigned_to == "Dev"
    assert by_task["Design"].assigned_to == "Des"


def test_task_assignment_marks_missing_skill():
    dev = Worker("Dev", HUMAN, "Dev", ["Python"], 30, 0, 100, 8)
    team = Team(humans=[dev, dev])
    tasks = [Task("Frontend", "React", 10, 1)]
    assignments = assign_tasks(team, tasks)
    assert assignments[0].missing_skill is True
    assert assignments[0].assigned_to is None


def test_ai_agent_works_faster():
    # An AI agent with speed 2.0 should consume half the hours a human would.
    ai = Worker("Bot", AI_AGENT, "QA", ["QA"], 40, 0, 18, 7, speed_multiplier=2.0)
    team = Team(ai_agents=[ai])
    tasks = [Task("Test", "QA", 20, 1)]
    assignments = assign_tasks(team, tasks)
    assert assignments[0].assigned_hours == 10.0  # 20 / 2.0


# ---------------------------------------------------------------------------
# 4. Score calculation
# ---------------------------------------------------------------------------

def test_score_calculation_ranges():
    # Full coverage, plenty of capacity -> high coverage & capacity scores.
    dev = Worker("Dev", HUMAN, "Dev", ["Python"], 30, 0, 100, 8)
    designer = Worker("Des", HUMAN, "Designer", ["UX"], 30, 0, 80, 8)
    team = Team(humans=[dev, designer])
    tasks = [Task("Build", "Python", 10, 1), Task("Design", "UX", 10, 1)]
    result = simulate_team(team, tasks)

    assert result.skill_coverage_score == 100.0
    assert 0 <= result.capacity_fit_score <= 100
    assert 0 <= result.productivity_score <= 100
    assert 0 <= result.risk_score <= 100
    assert 0 <= result.confidence_score <= 100
    assert result.missing_skills == []


def test_missing_skill_increases_risk():
    dev = Worker("Dev", HUMAN, "Dev", ["Python"], 30, 0, 100, 8)
    team = Team(humans=[dev, dev])
    full = [Task("Build", "Python", 10, 1)]
    partial = [Task("Build", "Python", 10, 1), Task("FE", "React", 10, 1)]
    low_risk = simulate_team(team, full)
    high_risk = simulate_team(team, partial)
    assert high_risk.risk_score > low_risk.risk_score
    assert "React" in high_risk.missing_skills


def test_scoring_helpers_bounds():
    assert scoring.skill_coverage_score(5, 10) == 50.0
    assert scoring.capacity_fit_score(100, 0) == 100.0    # no overflow
    assert scoring.capacity_fit_score(100, 50) == 50.0    # half spills over
    assert scoring.capacity_fit_score(100, 100) == 0.0    # all work overflows
    assert scoring.workload_balance_score([0.5, 0.5]) == 100.0  # perfectly even


# ---------------------------------------------------------------------------
# 5. Top-5 ranking
# ---------------------------------------------------------------------------

def test_top5_ranking():
    employees, ai_agents, tasks = load_all(DATA_DIR)
    results = rank_teams(employees, ai_agents, tasks, top_n=5)
    assert len(results) == 5
    # Ranks are 1..5 in order.
    assert [r.rank for r in results] == [1, 2, 3, 4, 5]
    # Sorted descending by total score.
    scores = [r.total_score for r in results]
    assert scores == sorted(scores, reverse=True)
    # Each top team has an explanation.
    for r in results:
        assert r.plain_english_explanation


def test_generate_teams_unique_and_sized():
    employees, ai_agents, _ = load_all(DATA_DIR)
    teams = generate_teams(employees, ai_agents)
    sigs = {t.signature() for t in teams}
    assert len(sigs) == len(teams)  # no duplicates
    for t in teams:
        assert 2 <= len(t.humans) <= 5
        assert 0 <= len(t.ai_agents) <= 2


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
    if failures:
        print(f"\n{failures} test(s) failed.")
        sys.exit(1)
    print("\nAll tests passed.")
