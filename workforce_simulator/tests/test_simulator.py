"""Tests for the workforce simulator (v2).

Run from the project root with::

    python -m pytest tests/
    # or, without pytest installed:
    python tests/test_simulator.py

Covers CSV loading, skill matching, task assignment, scoring, required vs
optional skill coverage, team validity, dependency ordering, critical-path
calculation, configurable weights, and top-5 ranking.
"""

import os
import sys

# Make ``src`` importable.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import scoring        # noqa: E402
import scheduler      # noqa: E402
import routing        # noqa: E402
import montecarlo     # noqa: E402
from data_loader import load_all                      # noqa: E402
from config_loader import load_config, SimConfig      # noqa: E402
from models import Worker, Task, Team, Assignment, HUMAN, AI_AGENT  # noqa: E402
from simulator import assign_tasks, simulate_team     # noqa: E402
from optimizer import generate_teams, rank_teams      # noqa: E402

DATA_DIR = os.path.join(ROOT, "data")
CONFIG_PATH = os.path.join(ROOT, "config", "scoring_weights.json")


def _by_name(workers):
    return {w.name: w for w in workers}


# ---------------------------------------------------------------------------
# 1. CSV loading (incl. new task columns)
# ---------------------------------------------------------------------------

def test_csv_loading():
    employees, ai_agents, tasks = load_all(DATA_DIR)
    assert len(employees) == 10
    assert len(ai_agents) == 3
    assert len(tasks) == 10

    sarah = _by_name(employees)["Sarah"]
    assert sarah.type == HUMAN and sarah.speed_multiplier == 1.0
    assert sarah.available_hours == 20

    # Dependencies and required flags parsed.
    by_task = {t.task: t for t in tasks}
    assert by_task["Frontend build"].dependencies == ["Prototype design"]
    assert by_task["QA testing"].dependencies == ["Frontend build", "Backend API"]
    assert by_task["Documentation"].dependencies == ["QA testing"]
    assert by_task["User research"].is_required is True
    assert by_task["Product strategy"].is_required is False


# ---------------------------------------------------------------------------
# 2. Skill matching
# ---------------------------------------------------------------------------

def test_skill_matching():
    w = Worker("X", HUMAN, "Dev", ["Python", "API"], 30, 0, 100, 8)
    assert w.has_skill("Python")
    assert w.has_skill("python")
    assert w.has_skill(" API ")
    assert not w.has_skill("React")


# ---------------------------------------------------------------------------
# 3. Task assignment
# ---------------------------------------------------------------------------

def test_task_assignment_picks_skilled_member():
    dev = Worker("Dev", HUMAN, "Dev", ["Python"], 30, 0, 100, 8)
    designer = Worker("Des", HUMAN, "Designer", ["UX"], 30, 0, 80, 8)
    team = Team(humans=[dev, designer])
    tasks = [Task("Build", "Python", 10, 1), Task("Design", "UX", 10, 1)]
    by_task = {a.task: a for a in assign_tasks(team, tasks)}
    assert by_task["Build"].assigned_to == "Dev"
    assert by_task["Design"].assigned_to == "Des"


def test_ai_agent_works_faster():
    ai = Worker("Bot", AI_AGENT, "QA", ["QA"], 40, 0, 18, 7, speed_multiplier=2.0)
    team = Team(ai_agents=[ai])
    assignments = assign_tasks(team, [Task("Test", "QA", 20, 1)])
    assert assignments[0].assigned_hours == 10.0  # 20 / 2.0


# ---------------------------------------------------------------------------
# 4. Required vs optional skill coverage
# ---------------------------------------------------------------------------

def test_required_and_optional_coverage():
    dev = Worker("Dev", HUMAN, "Dev", ["Python"], 30, 0, 100, 8)
    writer = Worker("Writer", HUMAN, "Writer", ["Writing"], 30, 0, 70, 8)
    team = Team(humans=[dev, writer])
    tasks = [
        Task("Build", "Python", 10, 1, is_required=True),
        Task("Frontend", "React", 10, 1, is_required=True),    # uncovered required
        Task("Docs", "Writing", 10, 2, is_required=False),     # covered optional
        Task("Strategy", "Strategy", 10, 2, is_required=False),  # uncovered optional
    ]
    res = simulate_team(team, tasks, require_full_required_skill_coverage=True)
    # 1 of 2 required covered, 1 of 2 optional covered.
    assert res.required_skill_coverage_score == 50.0
    assert res.optional_skill_coverage_score == 50.0
    assert res.missing_required_skills == ["React"]
    assert res.missing_optional_skills == ["Strategy"]


# ---------------------------------------------------------------------------
# 5. Team validity
# ---------------------------------------------------------------------------

def test_invalid_team_when_required_skill_missing():
    dev = Worker("Dev", HUMAN, "Dev", ["Python"], 30, 0, 100, 8)
    team = Team(humans=[dev, dev])
    tasks = [Task("Frontend", "React", 10, 1, is_required=True)]
    res = simulate_team(team, tasks, require_full_required_skill_coverage=True)
    assert res.is_valid_team is False
    assert res.invalid_reasons  # has a reason

    # With the flag off, the same team is "valid" (just penalised).
    res2 = simulate_team(team, tasks, require_full_required_skill_coverage=False)
    assert res2.is_valid_team is True


def test_valid_team_when_all_required_covered():
    dev = Worker("Dev", HUMAN, "Dev", ["Python"], 30, 0, 100, 8)
    fe = Worker("FE", HUMAN, "FE", ["React"], 30, 0, 95, 8)
    team = Team(humans=[dev, fe])
    tasks = [
        Task("Build", "Python", 10, 1, is_required=True),
        Task("Frontend", "React", 10, 1, is_required=True),
    ]
    res = simulate_team(team, tasks, require_full_required_skill_coverage=True)
    assert res.is_valid_team is True
    assert res.invalid_reasons == []
    assert res.missing_required_skills == []


# ---------------------------------------------------------------------------
# 6. Dependency ordering & critical path
# ---------------------------------------------------------------------------

def test_dependency_ordering():
    w1 = Worker("W1", HUMAN, "X", ["X"], 40, 0, 50, 8)
    w2 = Worker("W2", HUMAN, "Y", ["Y"], 40, 0, 50, 8)
    team = Team(humans=[w1, w2])
    tasks = [
        Task("A", "X", 10, 1),
        Task("B", "Y", 10, 1, dependencies=["A"]),
    ]
    assignments = assign_tasks(team, tasks)
    scheduler.schedule(assignments)
    by_task = {a.task: a for a in assignments}
    # B cannot start before A finishes.
    assert by_task["A"].finish_time == 10
    assert by_task["B"].start_time >= by_task["A"].finish_time
    assert by_task["B"].finish_time == 20


def test_critical_path_from_dependencies():
    w1 = Worker("W1", HUMAN, "X", ["X"], 40, 0, 50, 8)
    w2 = Worker("W2", HUMAN, "Y", ["Y"], 40, 0, 50, 8)
    w3 = Worker("W3", HUMAN, "Z", ["Z"], 40, 0, 50, 8)
    team = Team(humans=[w1, w2, w3])
    tasks = [
        Task("A", "X", 10, 1),
        Task("B", "Y", 10, 1, dependencies=["A"]),
        Task("C", "Z", 10, 1, dependencies=["B"]),
        Task("Side", "X", 5, 1),  # independent, off the critical path
    ]
    assignments = assign_tasks(team, tasks)
    info = scheduler.schedule(assignments)
    assert info["duration"] == 30           # A->B->C, 10 each
    assert info["critical_path"] == ["A", "B", "C"]
    by_task = {a.task: a for a in assignments}
    assert by_task["Side"].is_on_critical_path is False


def test_critical_path_from_resource_contention():
    # One worker must do two independent tasks -> they serialise and form
    # the critical path even with no dependency between them.
    w = Worker("Solo", HUMAN, "X", ["X"], 40, 0, 50, 8)
    team = Team(humans=[w])
    tasks = [Task("A", "X", 10, 1), Task("B", "X", 10, 2)]
    assignments = assign_tasks(team, tasks)
    info = scheduler.schedule(assignments)
    assert info["duration"] == 20
    assert info["critical_path"] == ["A", "B"]


# ---------------------------------------------------------------------------
# 7. Scoring helpers & configurable weights
# ---------------------------------------------------------------------------

def test_scoring_helpers_bounds():
    assert scoring.skill_coverage_score(5, 10) == 50.0
    assert scoring.skill_coverage_score(0, 0) == 100.0     # nothing to cover
    assert scoring.capacity_fit_score(100, 0) == 100.0
    assert scoring.capacity_fit_score(100, 50) == 50.0
    assert scoring.workload_balance_score([0.5, 0.5]) == 100.0


def test_config_loading_and_normalisation():
    config = load_config(CONFIG_PATH)
    assert config.require_full_required_skill_coverage is True
    assert config.max_humans_per_team == 5
    assert config.min_humans_per_team == 2
    # Weights normalise to sum 1.0.
    assert abs(sum(config.weights.values()) - 1.0) < 1e-9
    # 30/100 -> 0.30 for skill coverage.
    assert abs(config.weights["skill_coverage"] - 0.30) < 1e-9


def test_weights_change_ranking_score():
    scores = {
        "skill_coverage_score": 100.0,
        "capacity_fit_score": 0.0,
        "productivity_score": 0.0,
        "workload_balance_score": 0.0,
        "cost_efficiency_score": 0.0,
        "risk_score": 100.0,  # low_risk component = 0
    }
    coverage_heavy = {"skill_coverage": 1.0, "capacity_fit": 0.0,
                      "productivity": 0.0, "workload_balance": 0.0,
                      "cost_efficiency": 0.0, "low_risk": 0.0}
    cost_heavy = {"skill_coverage": 0.0, "capacity_fit": 0.0,
                  "productivity": 0.0, "workload_balance": 0.0,
                  "cost_efficiency": 1.0, "low_risk": 0.0}
    assert scoring.total_score(scores, coverage_heavy) == 100.0
    assert scoring.total_score(scores, cost_heavy) == 0.0


def test_required_penalty_lowers_total():
    scores = {
        "skill_coverage_score": 50.0, "capacity_fit_score": 100.0,
        "productivity_score": 100.0, "workload_balance_score": 100.0,
        "cost_efficiency_score": 100.0, "risk_score": 0.0,
    }
    full = scoring.total_score(scores, missing_required_fraction=0.0)
    penalised = scoring.total_score(scores, missing_required_fraction=1.0)
    assert penalised < full


# ---------------------------------------------------------------------------
# 8. Top-5 ranking
# ---------------------------------------------------------------------------

def test_top5_ranking_excludes_invalid_teams():
    employees, ai_agents, tasks = load_all(DATA_DIR)
    config = load_config(CONFIG_PATH)
    assert config.require_full_required_skill_coverage is True
    results = rank_teams(employees, ai_agents, tasks, config, top_n=5)
    assert len(results) == 5
    assert [r.rank for r in results] == [1, 2, 3, 4, 5]
    # Every team in the top 5 must be valid (no missing required skills).
    for r in results:
        assert r.is_valid_team is True
        assert r.missing_required_skills == []
    # Sorted descending by total score.
    scores = [r.total_score for r in results]
    assert scores == sorted(scores, reverse=True)
    # Each has a critical path and explanation.
    for r in results:
        assert r.critical_path
        assert r.plain_english_explanation


def test_generate_teams_respects_config_limits():
    employees, ai_agents, _ = load_all(DATA_DIR)
    config = SimConfig(min_humans_per_team=3, max_humans_per_team=3,
                       min_ai_agents_per_team=0, max_ai_agents_per_team=1)
    teams = generate_teams(employees, ai_agents, config)
    sigs = {t.signature() for t in teams}
    assert len(sigs) == len(teams)  # unique
    for t in teams:
        assert len(t.humans) == 3
        assert 0 <= len(t.ai_agents) <= 1


# ---------------------------------------------------------------------------
# 9. Task-level human/AI routing
# ---------------------------------------------------------------------------

def test_routing_ai_only_for_highly_automatable_task():
    # Writing/Documentation: high AI fit, repetitive, easy verify, low stakes.
    t = Task("Docs", "Writing", 15, 3, [], is_required=False)
    rec = routing.route_task(t)
    assert rec["routing"] == routing.AI_ONLY
    assert rec["explanation"]


def test_routing_human_only_for_high_stakes_task():
    # Strategy: heavy judgment, high error cost & context, hard to verify.
    t = Task("Strategy", "Strategy", 15, 1, [], is_required=True)
    rec = routing.route_task(t)
    assert rec["routing"] == routing.HUMAN_ONLY
    # No AI involvement -> no review or rework burden.
    assert rec["review_hours"] == 0.0
    assert rec["expected_rework_hours"] == 0.0


def test_routing_escalates_unknown_skill():
    t = Task("Mystery", "Quantum", 10, 1, [], is_required=True)
    rec = routing.route_task(t)
    assert rec["routing"] == routing.ESCALATE
    # Scores are unknown for an unprofiled skill.
    assert all(v is None for v in rec["scores"].values())


def test_routing_score_override_is_respected():
    # Force a HUMAN_ONLY profile via explicit scores on an otherwise AI skill.
    scores = {f: 3 for f in routing.SCORE_FIELDS}
    scores.update(error_cost=5, verification_ease=1, context_sensitivity=5,
                  human_judgment_need=5, ai_capability_fit=1)
    t = {"task": "X", "required_skill": "Writing", "effort_hours": 10,
         "priority": 1, "is_required": True, "routing_scores": scores}
    rec = routing.route_task(t)
    assert rec["routing"] == routing.HUMAN_ONLY


def test_routing_summary_totals_and_net():
    _, _, tasks = load_all(DATA_DIR)
    records = routing.route_tasks(tasks)
    summary = routing.summarize_routing(records)
    # Totals are the sum of the per-task estimates.
    assert summary["total_review_hours"] == round(
        sum(r["review_hours"] for r in records), 2
    )
    # net = saved - review - rework.
    assert summary["net_ai_time_saved"] == round(
        summary["total_ai_time_saved"]
        - summary["total_review_hours"]
        - summary["total_expected_rework_hours"],
        2,
    )
    assert summary["ai_saves_time"] == (summary["net_ai_time_saved"] > 0)


def test_reviewer_burden_zero_without_ai():
    employees, _, tasks = load_all(DATA_DIR)
    records = routing.route_tasks(tasks)
    humans = employees[:3]
    no_ai = routing.reviewer_burden_for_team(records, humans, has_ai=False)
    assert no_ai["review_burden_hours"] == 0.0
    assert no_ai["reviewer_bottleneck"]["is_bottleneck"] is False
    # With AI there is a real burden.
    with_ai = routing.reviewer_burden_for_team(records, humans, has_ai=True)
    assert with_ai["review_burden_hours"] > 0.0


# ---------------------------------------------------------------------------
# 10. Monte-Carlo uncertainty
# ---------------------------------------------------------------------------

def _mc_request(**overrides):
    _, _, tasks = load_all(DATA_DIR)
    req = {
        "tasks": [
            {"task": t.task, "required_skill": t.required_skill,
             "effort_hours": t.effort_hours, "priority": t.priority,
             "dependencies": t.dependencies, "is_required": t.is_required}
            for t in tasks
        ],
        "human_names": ["Sarah", "Maya", "Priya", "Alex", "Casey"],
        "ai_agent_names": ["AI Research Agent", "AI QA Reviewer"],
        "iterations": 200,
        "seed": 42,
    }
    req.update(overrides)
    return req


def test_montecarlo_percentiles_are_ordered():
    employees, ai_agents, _ = load_all(DATA_DIR)
    config = load_config(CONFIG_PATH)
    r = montecarlo.run_uncertainty(employees, ai_agents, _mc_request(), config)
    for key in ("duration", "cost"):
        s = r[key]
        assert s["min"] <= s["p10"] <= s["p50"] <= s["p90"] <= s["max"]


def test_montecarlo_is_reproducible_with_seed():
    employees, ai_agents, _ = load_all(DATA_DIR)
    config = load_config(CONFIG_PATH)
    r1 = montecarlo.run_uncertainty(employees, ai_agents, _mc_request(seed=7), config)
    r2 = montecarlo.run_uncertainty(employees, ai_agents, _mc_request(seed=7), config)
    assert r1["duration"] == r2["duration"]
    assert r1["cost"] == r2["cost"]
    # A different seed should change the sampled outcome.
    r3 = montecarlo.run_uncertainty(employees, ai_agents, _mc_request(seed=99), config)
    assert (r3["duration"]["p50"], r3["duration"]["p90"]) != (
        r1["duration"]["p50"], r1["duration"]["p90"]
    )


def test_montecarlo_probabilities_in_range():
    employees, ai_agents, _ = load_all(DATA_DIR)
    config = load_config(CONFIG_PATH)
    r = montecarlo.run_uncertainty(
        employees, ai_agents,
        _mc_request(deadline_target_hours=110, budget_target=20000), config
    )
    assert 0.0 <= r["probability_meets_deadline"] <= 1.0
    assert 0.0 <= r["probability_within_budget"] <= 1.0


def test_montecarlo_zero_range_is_degenerate():
    # Optimistic == likely == pessimistic -> every iteration is identical, so
    # the distribution collapses to the baseline (std 0).
    employees, ai_agents, _ = load_all(DATA_DIR)
    config = load_config(CONFIG_PATH)
    req = _mc_request(default_low_factor=1.0, default_high_factor=1.0)
    r = montecarlo.run_uncertainty(employees, ai_agents, req, config)
    assert r["duration"]["std"] == 0.0
    assert r["duration"]["p50"] == r["baseline"]["duration"]


def test_montecarlo_rejects_unknown_member():
    employees, ai_agents, _ = load_all(DATA_DIR)
    config = load_config(CONFIG_PATH)
    try:
        montecarlo.run_uncertainty(
            employees, ai_agents, _mc_request(human_names=["Ghost"]), config
        )
        assert False, "expected ProjectModeError"
    except montecarlo.ProjectModeError:
        pass


# ---------------------------------------------------------------------------
# Score / routing provenance (additive metadata; changes no value or decision)
# ---------------------------------------------------------------------------

import provenance  # noqa: E402

PROVENANCE_KEYS = {
    "field_name", "value", "source_type", "source_name", "confidence", "explanation",
}
ROUTE_PROV_FIELDS = {
    "recommended_route", "estimated_review_hours",
    "expected_rework_hours", "net_ai_time_saved",
}


def test_routing_record_includes_provenance():
    t = Task("Docs", "Writing", 15, 3, [], is_required=False)
    rec = routing.route_task(t)
    assert len(rec["score_provenance"]) == len(routing.SCORE_FIELDS)
    assert len(rec["route_provenance"]) == 4
    # Score provenance covers exactly the nine suitability scores.
    assert {p["field_name"] for p in rec["score_provenance"]} == set(routing.SCORE_FIELDS)
    # Route provenance covers the route + the three derived estimates.
    assert {p["field_name"] for p in rec["route_provenance"]} == ROUTE_PROV_FIELDS


def test_every_provenance_item_is_well_formed():
    _, _, tasks = load_all(DATA_DIR)
    for t in tasks:
        rec = routing.route_task(t)
        for p in rec["score_provenance"] + rec["route_provenance"]:
            assert set(p.keys()) == PROVENANCE_KEYS
            assert p["source_type"] in provenance.VALID_SOURCE_TYPES
            assert 0.0 <= p["confidence"] <= 1.0


def test_provenance_confidence_is_deterministic_by_source():
    assert provenance.item("f", 1, provenance.MANUAL_INPUT, "n", "e")["confidence"] == 0.95
    assert provenance.item("f", 1, provenance.EXISTING_HEURISTIC, "n", "e")["confidence"] == 0.7
    assert provenance.item("f", 1, provenance.DEFAULT_FALLBACK, "n", "e")["confidence"] == 0.3


def test_known_skill_scores_are_heuristic():
    t = Task("Docs", "Writing", 15, 3, [], is_required=False)
    rec = routing.route_task(t)
    assert all(
        p["source_type"] == provenance.EXISTING_HEURISTIC
        for p in rec["score_provenance"]
    )
    route = next(p for p in rec["route_provenance"] if p["field_name"] == "recommended_route")
    assert route["source_type"] == provenance.EXISTING_HEURISTIC


def test_manual_override_provenance():
    t = {"task": "X", "required_skill": "Writing", "effort_hours": 10,
         "priority": 1, "is_required": True,
         "routing_scores": {"ai_capability_fit": 5, "error_cost": 1}}
    rec = routing.route_task(t)
    by_field = {p["field_name"]: p for p in rec["score_provenance"]}
    assert by_field["ai_capability_fit"]["source_type"] == provenance.MANUAL_INPUT
    assert by_field["error_cost"]["source_type"] == provenance.MANUAL_INPUT
    # A field not in the override falls back to the default.
    assert by_field["verification_ease"]["source_type"] == provenance.DEFAULT_FALLBACK


def test_unknown_skill_provenance_is_default_fallback():
    t = Task("Mystery", "Quantum", 10, 1, [], is_required=True)
    rec = routing.route_task(t)
    assert rec["routing"] == routing.ESCALATE
    assert all(
        p["source_type"] == provenance.DEFAULT_FALLBACK for p in rec["score_provenance"]
    )
    route = next(p for p in rec["route_provenance"] if p["field_name"] == "recommended_route")
    assert route["source_type"] == provenance.DEFAULT_FALLBACK


def test_provenance_does_not_change_existing_route_decisions():
    # The routing decisions for the sample tasks must be exactly what the engine
    # produced before provenance was added.
    _, _, tasks = load_all(DATA_DIR)
    decisions = {r["task"]: r["routing"] for r in routing.route_tasks(tasks)}
    assert decisions["Documentation"] == routing.AI_ONLY
    assert decisions["Product strategy"] == routing.HUMAN_ONLY
    assert decisions["User research"] == routing.AI_FIRST_HUMAN_REVIEW
    assert decisions["Backend API"] == routing.HUMAN_FIRST_AI_ASSIST


def test_net_ai_time_saved_field():
    _, _, tasks = load_all(DATA_DIR)
    rec = routing.route_task(tasks[0])
    assert rec["net_ai_time_saved"] == round(
        rec["ai_time_saved"] - rec["review_hours"] - rec["expected_rework_hours"], 2
    )


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
