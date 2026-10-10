"""Tests for the brief-understanding fixes.

* Skills nobody has become labelled outside help (never silently dropped).
* No fake numbers: unstaffed work is reported, Monte Carlo won't claim a
  deadline/budget chance it can't know.
* Roster hours are per week, scaled by the project length.
* Task skills are matched to the roster's skills (AI, or words as fallback).
* Budget/timeline targets from a brief are sanity-checked.

Run from the project root::

    python -m pytest tests/test_brief_fixes.py
"""

import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

import montecarlo  # noqa: E402
import outside_help  # noqa: E402
import project_mode  # noqa: E402
from config_loader import SimConfig  # noqa: E402
from models import HUMAN, Worker  # noqa: E402
from src.api import brief_parser, skill_mapper  # noqa: E402


def _human(name, skills, capacity=40, workload=0, rate=80):
    return Worker(name=name, type=HUMAN, role="r", skills=skills,
                  capacity_hours=capacity, workload_hours=workload,
                  cost_rate=rate, quality_score=7)


def _t(name, skill, hours, deps=()):
    return {"task": name, "required_skill": skill, "effort_hours": hours,
            "priority": 1, "dependencies": list(deps), "is_required": True}


EMPLOYEES = [_human("Ana", ["Strategy"]), _human("Ben", ["Writing"])]
TASKS = [
    _t("Plan", "Strategy", 10),
    _t("Buy ads", "Paid media", 20, deps=["Plan"]),
    _t("Write copy", "Writing", 10, deps=["Buy ads"]),
]


def _run(tasks=TASKS, employees=EMPLOYEES, **extra):
    req = {
        "optimization_objective": "balanced",
        "tasks": tasks,
        "current_team_human_names": [e.name for e in employees],
        "current_team_ai_agent_names": [],
    }
    req.update(extra)
    return project_mode.run_project_simulation(employees, [], req, SimConfig())


# ---------------------------------------------------------------------------
# Outside help
# ---------------------------------------------------------------------------

def test_gap_work_is_scheduled_as_outside_help_with_rate():
    res = _run(outside_help_rate=100)
    gap = res["staffing_gap"]
    assert gap["skills"] == ["Paid media"] and gap["hours"] == 20
    assert gap["cost_estimate"] == 2000 and gap["cost_included"]
    rec = res["options"][res["recommendation"]["recommended_option"]]
    assert rec["is_valid_team"]
    assert "Outside hire (Paid media)" in rec["team_members"]
    assert rec["outside_help_members"] == ["Outside hire (Paid media)"]
    assert rec["unstaffed_hours"] == 0
    # All 40h are scheduled (chain of 10 + 20 + 10) and the $2,000 is costed.
    assert rec["estimated_duration"] == 40
    assert rec["estimated_cost"] == 20 * 80 + 2000
    text = res["recommendation"]["summary_text"]
    assert "Paid media" in text
    # The summary paragraph agrees with the risk/next rows.
    assert "Biggest risk: low" not in text
    assert res["recommendation"]["biggest_risk"] in text


def test_gap_cost_not_included_without_rate_and_says_so():
    res = _run()
    gap = res["staffing_gap"]
    assert gap["cost_estimate"] is None and not gap["cost_included"]
    assert "NOT included" in gap["message"]
    rec = res["options"][res["recommendation"]["recommended_option"]]
    assert rec["estimated_duration"] == 40          # time still counted
    assert rec["estimated_cost"] == 20 * 80         # only the roster's cost


def test_no_gap_means_empty_staffing_gap():
    res = _run(tasks=[_t("Plan", "Strategy", 10)])
    assert res["staffing_gap"]["tasks"] == []
    assert res["staffing_gap"]["message"] == ""


def test_roster_covering_nothing_gives_no_fake_team():
    res = _run(tasks=[_t("Buy ads", "Paid media", 20), _t("Edit video", "Video", 5)])
    rec = res["recommendation"]
    assert rec["roster_covers_nothing"]
    assert "Nobody on your roster" in rec["summary_text"]
    opt = res["options"][rec["recommended_option"]]
    assert all(m.startswith("Outside hire") for m in opt["team_members"])
    assert res["staffing_gap"]["hours"] == 25


def test_outside_help_does_not_add_reviewer_capacity():
    res = _run(outside_help_rate=100)
    rec = res["options"][res["recommendation"]["recommended_option"]]
    # The placeholder never appears as a reviewer.
    assert "Outside hire" not in str(rec["reviewer_bottleneck"])


# ---------------------------------------------------------------------------
# Monte Carlo honesty
# ---------------------------------------------------------------------------

def _mc(human_names, **extra):
    req = {"tasks": TASKS, "human_names": human_names, "ai_agent_names": [],
           "iterations": 50, "seed": 42, "deadline_target_hours": 1000,
           "budget_target": 100000}
    req.update(extra)
    return montecarlo.run_uncertainty(EMPLOYEES, [], req, SimConfig())


def test_mc_refuses_probabilities_when_work_is_unstaffed():
    out = _mc(["Ana", "Ben"])
    assert out["unstaffed_tasks"] == ["Buy ads"]
    assert out["probability_meets_deadline"] is None
    assert out["probability_within_budget"] is None


def test_mc_accepts_outside_help_names_and_reports_chances():
    out = _mc(["Ana", "Ben", "Outside hire (Paid media)"], outside_help_rate=100)
    assert out["unstaffed_tasks"] == []
    assert out["probability_meets_deadline"] == 1.0
    assert out["probability_within_budget"] == 1.0


def test_mc_no_budget_chance_when_outside_cost_unknown():
    out = _mc(["Ana", "Ben", "Outside hire (Paid media)"])
    assert out["cost_excludes_outside_help"]
    assert out["probability_meets_deadline"] == 1.0
    assert out["probability_within_budget"] is None


# ---------------------------------------------------------------------------
# Per-week capacity
# ---------------------------------------------------------------------------

def test_resolve_weeks_sources():
    assert outside_help.resolve_weeks(8, 120)[:2] == (8.0, "set")
    assert outside_help.resolve_weeks(None, 120)[:2] == (3.0, "deadline")
    assert outside_help.resolve_weeks(None, None)[:2] == (1.0, "default")
    # A short deadline never shrinks capacity below one week.
    assert outside_help.resolve_weeks(None, 10)[0] == 1.0


def test_weekly_capacity_scales_with_project_length():
    busy = [_human("Ana", ["Strategy"], capacity=40, workload=30)]  # 10h free/week
    tasks = [_t("Plan", "Strategy", 50)]
    one = _run(tasks=tasks, employees=busy, project_weeks=1)
    eight = _run(tasks=tasks, employees=busy, project_weeks=8)
    key = "current_team"
    assert one["options"][key]["overloaded_members"] == ["Ana"]
    assert eight["options"][key]["overloaded_members"] == []
    assert eight["capacity_basis"]["weeks"] == 8
    assert "per week" in eight["capacity_basis"]["explanation"]


def test_capacity_scaling_never_mutates_the_roster():
    w = _human("Ana", ["Strategy"], capacity=40, workload=10)
    outside_help.scale_capacity([w], 4)
    assert (w.capacity_hours, w.workload_hours) == (40, 10)


# ---------------------------------------------------------------------------
# Skill mapping
# ---------------------------------------------------------------------------

PEOPLE = ["Data", "Strategy", "Coordination", "Writing"]
AVAILABLE = PEOPLE + ["Automation"]


def test_mapper_word_fallback_without_ai(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = skill_mapper.map_skills(
        ["Campaign Strategy", "Data Analysis", "Paid media", "Writing"],
        PEOPLE, AVAILABLE)
    assert out["method"] == "words"
    got = {i["skill"]: i["suggestion"] for i in out["items"]}
    # Skills someone already has aren't listed.
    assert "Writing" not in got
    assert got["Campaign Strategy"] == "Strategy"
    assert got["Data Analysis"] == "Data"
    assert got["Paid media"] is None


def test_mapper_ai_answers_are_kept_inside_the_vocabulary(monkeypatch):
    def fake(skills, people, ai_only, tasks=None):
        return {
            "dashboarding": {"roster_skill": "Data", "reason": "Dashboards are data work."},
            "stakeholder management": {"roster_skill": None, "reason": "Nobody fits."},
        }, {}
    monkeypatch.setattr(skill_mapper, "_ai_review", fake)
    out = skill_mapper.map_skills(["Dashboarding", "Stakeholder Management"],
                                  PEOPLE, AVAILABLE)
    assert out["method"] == "ai"
    got = {i["skill"]: i for i in out["items"]}
    assert got["Dashboarding"]["suggestion"] == "Data"
    assert got["Stakeholder Management"]["suggestion"] is None


def test_mapper_drops_invented_skills_from_the_model(monkeypatch):
    class FakeResponse:
        stop_reason = "end_turn"
        parsed_output = skill_mapper._ModelOutput(matches=[
            skill_mapper._Match(skill="Dashboarding", roster_skill="Tableau Wizardry"),
            skill_mapper._Match(skill="Ops", roster_skill="automation"),
        ])

    class FakeClient:
        def __init__(self):
            self.messages = SimpleNamespace(parse=lambda **kw: FakeResponse())

    import anthropic
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    out = skill_mapper.map_skills(["Dashboarding", "Ops"], PEOPLE, AVAILABLE)
    got = {i["skill"]: i for i in out["items"]}
    assert got["Dashboarding"]["suggestion"] is None      # invented -> dropped
    assert got["Ops"]["suggestion"] == "Automation"       # canonical casing
    assert got["Ops"]["ai_only"] is True


def test_mapper_falls_back_to_words_when_ai_fails(monkeypatch):
    def boom(*a):
        raise brief_parser.BriefParserError(502, "down")
    monkeypatch.setattr(skill_mapper, "_ai_review", boom)
    out = skill_mapper.map_skills(
        ["Campaign Strategy"], PEOPLE, AVAILABLE,
        tasks=[{"task": "Make ads", "required_skill": "Writing"}])
    assert out["method"] == "words"
    assert out["items"][0]["suggestion"] == "Strategy"
    # No AI = no stretch review, and the response says so.
    assert out["stretches"] == [] and out["stretch_check"] == "unavailable"


# ---------------------------------------------------------------------------
# Stretched labels (fix: ad creative labelled "Prototype")
# ---------------------------------------------------------------------------

def _fake_client(monkeypatch, output, seen=None):
    class FakeResponse:
        stop_reason = "end_turn"
        parsed_output = output

    def parse(**kw):
        if seen is not None:
            seen.append(kw["messages"][0]["content"])
        return FakeResponse()

    class FakeClient:
        def __init__(self):
            self.messages = SimpleNamespace(parse=parse)

    import anthropic
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)


def test_stretched_label_is_flagged_with_outside_help_default(monkeypatch):
    seen = []
    _fake_client(monkeypatch, skill_mapper._ModelOutput(fits=[
        skill_mapper._Fit(task="Produce ad creative", fit="stretch",
                          needed_skill="Ad creative production",
                          reason="Prototype is a software skill."),
        skill_mapper._Fit(task="Write report", fit="good"),
        skill_mapper._Fit(task="Not asked about", fit="stretch", needed_skill="X"),
    ]), seen)
    out = skill_mapper.map_skills(
        ["Prototype", "Writing"], PEOPLE + ["Prototype"], AVAILABLE + ["Prototype"],
        tasks=[{"task": "Produce ad creative", "required_skill": "Prototype"},
               {"task": "Write report", "required_skill": "Writing"}])
    assert out["stretch_check"] == "ai"
    assert out["stretches"] == [{
        "task": "Produce ad creative", "required_skill": "Prototype",
        "needed_skill": "Ad creative production", "suggestion": None,
        "reason": "Prototype is a software skill.",
    }]
    # Only task and skill names go to the AI.
    assert "Produce ad creative | labelled: Prototype" in seen[0]


def test_stretch_suggests_a_better_roster_skill_when_one_exists(monkeypatch):
    _fake_client(monkeypatch, skill_mapper._ModelOutput(fits=[
        skill_mapper._Fit(task="Set campaign direction", fit="stretch",
                          needed_skill="strategy"),
    ]))
    out = skill_mapper.map_skills(
        ["Writing"], PEOPLE, AVAILABLE,
        tasks=[{"task": "Set campaign direction", "required_skill": "Writing"}])
    assert out["stretches"][0]["suggestion"] == "Strategy"


# ---------------------------------------------------------------------------
# Work moves off overloaded people
# ---------------------------------------------------------------------------

def test_overloaded_persons_work_moves_to_teammate_with_room():
    from models import Team
    from simulator import assign_tasks
    star = Worker(name="Maya", type=HUMAN, role="r", skills=["Data"],
                  capacity_hours=40, workload_hours=0, cost_rate=50, quality_score=9)
    other = _human("Sarah", ["Data"], rate=90)
    tasks = project_mode.tasks_from_request(
        [_t(f"Analysis {i}", "Data", 15) for i in range(4)])
    out = assign_tasks(Team([star, other], []), tasks)
    load = {}
    for a in out:
        load[a.assigned_to] = load.get(a.assigned_to, 0) + a.assigned_hours
    # 60h of Data work, 40h each: nobody is over capacity any more.
    assert load["Maya"] <= 40 and load["Sarah"] <= 40
    assert load["Maya"] + load["Sarah"] == 60


def test_overload_stays_when_nobody_has_room():
    from models import Team
    from simulator import assign_tasks
    tasks = project_mode.tasks_from_request([_t(f"T{i}", "Data", 30) for i in range(3)])
    out = assign_tasks(Team([_human("Ana", ["Data"]), _human("Ben", ["Data"])], []), tasks)
    # 90h for 80h of room: the overload is real and stays visible.
    assert sum(a.assigned_hours for a in out) == 90


# ---------------------------------------------------------------------------
# AI output that feeds a decision gets a human check
# ---------------------------------------------------------------------------

def _rt(name, skill, deps=(), stage=None, irreversible=False):
    from models import Task
    return Task(name, skill, 10, 1, dependencies=list(deps), stage=stage,
                irreversible=irreversible)


def test_ai_only_output_feeding_a_decision_gets_reviewed():
    import routing
    alone = routing.route_tasks([_rt("Weekly insights", "writing")])[0]["routing"]
    assert alone == routing.AI_ONLY  # precondition: AI could own it alone
    recs = routing.route_tasks([
        _rt("Weekly insights", "writing"),
        _rt("Approve budget changes", "strategy", deps=["Weekly insights"], stage="choice"),
        _rt("Final report", "writing"),
        _rt("Present findings", "coordination", deps=["Final report"], irreversible=True),
    ])
    by = {r["task"]: r for r in recs}
    for name in ("Weekly insights", "Final report"):
        assert by[name]["routing"] == routing.AI_FIRST_HUMAN_REVIEW, name
        assert by[name]["review_hours"] > 0
    assert "Approve budget changes" in by["Weekly insights"]["explanation"]


def test_break_even_ai_verdict_has_no_negative_zero():
    text = project_mode._ai_time_verdict({
        "ai_time_saved": 40, "review_burden_hours": 31,
        "expected_rework_hours": 9.3, "net_time_saved": -0.3})
    assert "-0h" not in text and "breaks even" in text


def test_skills_map_endpoint(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from src.api.app import app
    client = TestClient(app)
    client.post("/employees/use-demo")
    body = client.post("/skills/map", json={"skills": ["Campaign Strategy", "Strategy"]}).json()
    assert [i["skill"] for i in body["items"]] == ["Campaign Strategy"]
    assert body["items"][0]["suggestion"] == "Strategy"


# ---------------------------------------------------------------------------
# Brief targets
# ---------------------------------------------------------------------------

def test_brief_targets_drop_impossible_figures():
    t = brief_parser._clean_targets(brief_parser.BriefTargets(
        total_budget=75000, labor_budget=25000, timeline_weeks=8))
    assert (t.total_budget, t.labor_budget, t.timeline_weeks) == (75000, 25000, 8)
    t = brief_parser._clean_targets(brief_parser.BriefTargets(
        total_budget=10000, labor_budget=50000, timeline_weeks=0))
    assert t.labor_budget is None and t.timeline_weeks is None
    assert brief_parser._clean_targets(None) is None


def test_brief_prompt_asks_for_labor_budget_only():
    assert "labor_budget" in brief_parser._SYSTEM_PROMPT
    assert "not labor" in brief_parser._SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Roster options keep only the people who'd get work
# ---------------------------------------------------------------------------

def test_roster_options_drop_idle_people():
    roster = [_human("Ana", ["Strategy"]), _human("Ben", ["Writing"])] + [
        _human(f"Idle{i}", ["Accounting"]) for i in range(8)
    ]
    res = _run(tasks=[_t("Plan", "Strategy", 10), _t("Copy", "Writing", 10)],
               employees=roster, project_weeks=4)
    opt = res["options"]["current_team"]
    assert sorted(opt["team_members"]) == ["Ana", "Ben"]
    assert len(opt["idle_roster_members"]) == 8
    assert not opt["over_max_team_size"]
    rec = res["options"][res["recommendation"]["recommended_option"]]
    assert len(rec["team_members"]) <= 5


def test_roster_option_over_max_size_is_never_recommended():
    skills = ["A", "B", "C", "D", "E", "F", "G"]
    roster = [_human(f"P{s}", [s]) for s in skills]
    tasks = [_t(f"Task {s}", s, 5) for s in skills]
    res = _run(tasks=tasks, employees=roster, project_weeks=4,
               team_constraints={"max_humans_per_team": 5})
    opt = res["options"]["current_team"]
    assert len(opt["team_members"]) == 7 and opt["over_max_team_size"]
    assert opt["is_valid_team"]
    # No 5-person team covers 7 skills, so nothing within the cap is valid;
    # the 7-person roster team is then the only fully staffed fallback.
    assert res["recommendation"]["recommended_option"] in (
        "current_team", "ai_assisted_current_team")


def test_cap_applies_when_a_valid_team_fits():
    roster = [_human("A", ["X"]), _human("B", ["Y"]), _human("C", ["Z"]),
              _human("D", ["X", "Y", "Z"])]
    tasks = [_t("Do X", "X", 40), _t("Do Y", "Y", 40), _t("Do Z", "Z", 40)]
    res = _run(tasks=tasks, employees=roster, project_weeks=4,
               team_constraints={"max_humans_per_team": 2})
    # A valid team within the cap exists, so the recommendation is within it.
    rec = res["options"][res["recommendation"]["recommended_option"]]
    assert rec["is_valid_team"] and len(rec["team_members"]) <= 2


def test_choose_recommendation_skips_oversized_valid_options():
    def fake(people, score):
        return SimpleNamespace(
            team=SimpleNamespace(humans=[_human(f"P{i}", ["X"]) for i in range(people)]),
            missing_required_skills=[], total_score=score, estimated_cost=100,
            required_skill_coverage_score=100,
        )
    options = {"current_team": fake(10, 99), "recommended_balanced_team": fake(3, 80)}
    assert project_mode.choose_recommendation(options, "balanced", 5) == \
        "recommended_balanced_team"
    # Without a cap (or nothing within it), the best valid option wins.
    assert project_mode.choose_recommendation(options, "balanced") == "current_team"
    assert project_mode.choose_recommendation(options, "balanced", 2) == "current_team"
