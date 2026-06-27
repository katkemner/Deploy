"""Tests for the dynamic-agent staffing strategies.

Each strategy is only a candidate-plan generator: it decides who does which
task (human vs conjured AI), then runs through the SAME scheduler + scorer.
These tests assert the assignment behaviour, dynamic-agent synthesis, and that
the existing scorer/routing is untouched.

Run from the project root::

    python -m pytest tests/test_staffing_strategies.py
    # or directly:
    python tests/test_staffing_strategies.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

import routing  # noqa: E402
import staffing_strategies as strat  # noqa: E402
from models import AI_AGENT, HUMAN, Task, Worker  # noqa: E402
from simulator import assign_tasks, simulate_team  # noqa: E402
from models import Team  # noqa: E402


def _human(name, skills, capacity=40, cost=80, quality=8):
    return Worker(name=name, type=HUMAN, role="eng", skills=skills,
                  capacity_hours=capacity, workload_hours=0, cost_rate=cost,
                  quality_score=quality)


def _routing_map(tasks):
    """Real routing decisions/scores for a set of tasks (no priors/workbank)."""
    records = routing.route_tasks(tasks)
    return {r["task"]: {"decision": r["routing"], "scores": r["scores"]} for r in records}


# Tasks chosen to span routing buckets:
# - Documentation -> AI_ONLY
# - User research  -> AI_FIRST_HUMAN_REVIEW
# - Product strategy -> HUMAN_ONLY
def _tasks():
    return [
        Task("Docs", "Documentation", 10, 1),
        Task("Research", "Research", 12, 1),
        Task("Strategy", "Strategy", 8, 1),
    ]


# ---------------------------------------------------------------------------
# allowed_types constraint in the simulator (backward compatible)
# ---------------------------------------------------------------------------

def test_allowed_types_pins_worker_type():
    humans = [_human("H", ["Documentation"])]
    ai = strat.synthesize_agent(Task("Docs", "Documentation", 10, 1), {"ai_capability_fit": 5, "speed_value": 4}, "AI Documentation Agent")
    team = Team(humans, [ai])
    tasks = [Task("Docs", "Documentation", 10, 1)]
    # Force the task to AI only.
    a = assign_tasks(team, tasks, allowed_types={"Docs": {AI_AGENT}})
    assert a[0].assigned_type == AI_AGENT
    # Force the task to HUMAN only.
    a = assign_tasks(team, tasks, allowed_types={"Docs": {HUMAN}})
    assert a[0].assigned_type == HUMAN
    # No constraint -> unchanged behaviour (some skilled worker is chosen).
    a = assign_tasks(team, tasks)
    assert a[0].assigned_to is not None


def test_allowed_types_empty_candidates_is_a_gap():
    humans = [_human("H", ["Documentation"])]
    team = Team(humans, [])  # no AI on team
    tasks = [Task("Docs", "Documentation", 10, 1)]
    a = assign_tasks(team, tasks, allowed_types={"Docs": {AI_AGENT}})
    assert a[0].missing_skill is True


# ---------------------------------------------------------------------------
# Dynamic agent synthesis (grounded in the sheet)
# ---------------------------------------------------------------------------

def test_synthesized_agent_is_grounded_in_scores():
    t = Task("Docs", "Documentation", 10, 1)
    scores = {"ai_capability_fit": 5, "speed_value": 4}
    ag = strat.synthesize_agent(t, scores, "AI Documentation Agent")
    assert ag.type == AI_AGENT
    assert ag.skills == ["Documentation"]
    assert ag.quality_score == 10.0          # fit 5 -> 10
    assert ag.speed_multiplier == 1.4        # 1 + 0.1*4
    assert ag.cost_rate == strat.AI_AGENT_COST_RATE
    # Capacity right-sized for its one task (effort / speed).
    assert abs(ag.capacity_hours - 10 / 1.4) < 0.01


# ---------------------------------------------------------------------------
# Strategy plans
# ---------------------------------------------------------------------------

def test_ai_first_assigns_ai_to_ai_eligible_tasks():
    humans = [_human("H", ["Documentation", "Research", "Strategy"])]
    tasks = _tasks()
    team, allowed, agents, notes = strat.build_plan(
        strat.AI_FIRST, humans, tasks, _routing_map(tasks)
    )
    # Documentation (AI_ONLY) and Research (AI_FIRST) go to AI; Strategy stays human.
    assert allowed["Docs"] == {AI_AGENT}
    assert allowed["Research"] == {AI_AGENT}
    assert allowed["Strategy"] == {HUMAN}
    assert len(agents) == 2
    assert len(notes) == 2


def test_human_core_only_takes_ai_only_and_gaps():
    # Human covers all three skills -> only the AI_ONLY task goes to AI.
    humans = [_human("H", ["Documentation", "Research", "Strategy"])]
    tasks = _tasks()
    team, allowed, agents, notes = strat.build_plan(
        strat.HUMAN_CORE, humans, tasks, _routing_map(tasks)
    )
    assert allowed["Docs"] == {AI_AGENT}       # AI_ONLY -> AI
    assert allowed["Research"] == {HUMAN}      # human leads (has the skill)
    assert allowed["Strategy"] == {HUMAN}
    assert len(agents) == 1


def test_human_core_gap_fill_uses_ai_when_no_human_has_skill():
    # Human lacks Research; routing says AI can own it -> gap filled by AI.
    humans = [_human("H", ["Strategy"])]  # only Strategy
    tasks = _tasks()
    team, allowed, agents, notes = strat.build_plan(
        strat.HUMAN_CORE, humans, tasks, _routing_map(tasks)
    )
    assert allowed["Docs"] == {AI_AGENT}       # AI_ONLY
    assert allowed["Research"] == {AI_AGENT}   # gap fill (AI_FIRST + no human)
    assert allowed["Strategy"] == {HUMAN}
    assert any("gap" in n for n in notes)


def test_human_first_never_uses_ai():
    humans = [_human("H", ["Documentation", "Research", "Strategy"])]
    tasks = _tasks()
    team, allowed, agents, notes = strat.build_plan(
        strat.HUMAN_FIRST, humans, tasks, _routing_map(tasks)
    )
    assert all(v == {HUMAN} for v in allowed.values())
    assert agents == []


def test_human_first_flags_gap_when_no_human_has_skill():
    # No human can do Research; Human-First never conjures AI -> invalid plan.
    humans = [_human("H", ["Strategy"])]
    tasks = [Task("Research", "Research", 12, 1), Task("Strategy", "Strategy", 8, 1)]
    team, allowed, agents, notes = strat.build_plan(
        strat.HUMAN_FIRST, humans, tasks, _routing_map(tasks)
    )
    res = simulate_team(team, tasks, require_full_required_skill_coverage=True,
                        allowed_types=allowed)
    assert "Research" in res.missing_required_skills
    assert res.is_valid_team is False


def test_unlimited_agents_one_per_ai_task():
    # Two AI_ONLY tasks of the same skill -> two distinct conjured agents.
    humans = [_human("H", ["Strategy"])]
    tasks = [
        Task("Docs1", "Documentation", 10, 1),
        Task("Docs2", "Documentation", 10, 1),
        Task("Strategy", "Strategy", 8, 1),
    ]
    team, allowed, agents, notes = strat.build_plan(
        strat.AI_FIRST, humans, tasks, _routing_map(tasks)
    )
    assert len(agents) == 2
    assert len({a.name for a in agents}) == 2  # unique names, no cap


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
    print("\nAll staffing-strategy tests passed.")
