"""Tests for the deterministic innovation_score lens.

Verifies the 0-100 weighted score, that it uses the project's real
coverage/overload (the guardrail), that human-led teams beat AI-heavy ones, and
that capability coverage is treated as team skill-coverage (not personality).

Run from the project root::

    python -m pytest tests/test_innovation.py
    # or directly:
    python tests/test_innovation.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

import innovation  # noqa: E402
from models import AI_AGENT, HUMAN, Task, Team, Worker  # noqa: E402
from simulator import simulate_team  # noqa: E402


def _human(name, skills, capacity=40):
    return Worker(name=name, type=HUMAN, role="r", skills=skills,
                  capacity_hours=capacity, workload_hours=0, cost_rate=80,
                  quality_score=8)


def _zero_burden():
    return {"ai_time_saved": 0.0, "net_time_saved": 0.0,
            "review_burden_hours": 0.0, "expected_rework_hours": 0.0}


def _tasks():
    # A cross-functional project spanning exploration/prototype/validation/launch.
    return [
        Task("Research users", "Research", 10, 1),
        Task("Design UX", "UX", 10, 1),
        Task("Build", "React", 10, 1),
        Task("QA", "QA", 10, 1),
        Task("Launch ops", "Operations", 10, 1),
    ]


def test_score_is_0_to_100_and_weighted():
    humans = [_human("A", ["Research", "UX"]), _human("B", ["React", "QA", "Operations"])]
    tasks = _tasks()
    res = simulate_team(Team(humans, []), tasks, require_full_required_skill_coverage=True)
    total, comps = innovation.score(res, {}, _zero_burden())
    assert 0 <= total <= 100
    assert set(comps.keys()) == set(innovation.WEIGHTS.keys())
    expected = sum(comps[k] * innovation.WEIGHTS[k] for k in innovation.WEIGHTS) / 100.0
    assert abs(total - round(expected, 2)) < 0.05


def test_weights_sum_to_100():
    assert sum(innovation.WEIGHTS.values()) == 100


def test_capability_coverage_counts_tags_only_when_skills_present():
    broad = [_human("A", ["Research", "UX", "Prototype"]),
             _human("B", ["Strategy", "Operations", "QA", "Automation"])]
    narrow = [_human("C", ["QA"])]
    tasks = _tasks()
    rb = simulate_team(Team(broad, []), tasks, True)
    rn = simulate_team(Team(narrow, []), tasks, True)
    _, cb = innovation.score(rb, {}, _zero_burden())
    _, cn = innovation.score(rn, {}, _zero_burden())
    assert cb["innovation_capability_coverage_score"] > cn["innovation_capability_coverage_score"]


def test_guardrail_penalizes_missing_required_skills():
    tasks = _tasks()
    full = [_human("A", ["Research", "UX"]), _human("B", ["React", "QA", "Operations"])]
    partial = [_human("C", ["Research"])]  # misses UX/React/QA/Operations
    rf = simulate_team(Team(full, []), tasks, True)
    rp = simulate_team(Team(partial, []), tasks, True)
    _, cf = innovation.score(rf, {}, _zero_burden())
    _, cp = innovation.score(rp, {}, _zero_burden())
    assert cf["project_fit_guardrail_score"] > cp["project_fit_guardrail_score"]


def test_human_led_beats_ai_heavy_on_innovation():
    # Same project: a human-owned plan should out-score an AI-owned plan on
    # innovation (novel work comes from people, not AI volume).
    tasks = [Task("Research users", "Research", 10, 1), Task("Design UX", "UX", 10, 1)]
    humans = [_human("A", ["Research", "UX"])]
    res_human = simulate_team(Team(humans, []), tasks, True)
    # AI-heavy team: agents cover the skills, so the candidate scorer assigns
    # the creative tasks to AI -> humans not doing the novel work.
    agents = [
        Worker("AI Research Agent", AI_AGENT, "AI agent", ["Research"], 40, 0, 18, 9, 1.4),
        Worker("AI UX Agent", AI_AGENT, "AI agent", ["UX"], 40, 0, 18, 9, 1.4),
    ]
    res_ai = simulate_team(Team(humans, agents), tasks, True)
    th, _ = innovation.score(res_human, {}, _zero_burden())
    tai, _ = innovation.score(res_ai, {}, _zero_burden())
    assert th > tai


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
    print("\nAll innovation tests passed.")
