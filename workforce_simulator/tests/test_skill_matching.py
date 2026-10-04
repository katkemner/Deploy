"""Tests for the roster-vocabulary bridge (skill_matching) and its consumers.

Covers the deterministic matcher itself, routing profiles resolved from
free-form roster skills (no more blanket ESCALATE), innovation capability
credit for roster skills, the roster-driven brief vocabulary, and the
no-valid-team fallback (respects max team size; honest wording).

Run from the project root::

    python -m pytest tests/test_skill_matching.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

import innovation  # noqa: E402
import project_mode  # noqa: E402
import routing  # noqa: E402
import skill_matching  # noqa: E402
from config_loader import SimConfig  # noqa: E402
from models import HUMAN, Task, Worker  # noqa: E402


KEYS = routing.SKILL_PROFILES.keys()


# ---------------------------------------------------------------------------
# The matcher itself
# ---------------------------------------------------------------------------

def test_exact_match_unchanged():
    assert skill_matching.match("writing", KEYS) == ("writing", "exact")
    assert skill_matching.match("  QA ", KEYS) == ("qa", "exact")


def test_token_match_rightmost_word():
    # The last word names the kind of work; earlier words only qualify it.
    assert skill_matching.match("customer research", KEYS) == ("research", "token")
    assert skill_matching.match("Brand strategy", KEYS) == ("strategy", "token")
    assert skill_matching.match("UX research", KEYS) == ("research", "token")
    assert skill_matching.match("Data analysis", KEYS) == ("analysis", "token")
    assert skill_matching.match("team planning", KEYS) == ("planning", "token")
    assert skill_matching.match("Campaign Strategy", KEYS) == ("strategy", "token")
    assert skill_matching.match("Sales Analytics", KEYS) == ("analytics", "token")
    # Falls back to an earlier word when the last one isn't a key.
    assert skill_matching.match("social media", KEYS) == ("social", "token")
    assert skill_matching.match("Program management", KEYS) == ("program", "token")


def test_stem_match_bridges_suffixes():
    assert skill_matching.match("Copywriting", KEYS) == ("writing", "stem")
    assert skill_matching.match("prototyping", KEYS) == ("prototype", "stem")


def test_short_keys_never_match_by_substring():
    # "qa", "ux", "api" are too short for substring stems — no accidents.
    # "deluxe" contains "ux" and "capital" contains "api" - neither may match.
    assert skill_matching.match("deluxe", KEYS) == (None, "none")
    assert skill_matching.match("capital", KEYS) == (None, "none")


def test_unknown_skill_matches_nothing():
    assert skill_matching.match("underwater welding", KEYS) == (None, "none")
    assert skill_matching.match("", KEYS) == (None, "none")


# ---------------------------------------------------------------------------
# Routing on roster vocabulary
# ---------------------------------------------------------------------------

def _task(name, skill, hours=10):
    return Task(name, skill, hours, 1)


def test_routing_profiles_roster_skills_instead_of_escalating():
    tasks = [
        _task("Write campaign emails", "Copywriting"),
        _task("Interview customers", "customer research"),
        _task("Positioning", "Brand strategy"),
    ]
    records = routing.route_tasks(tasks)
    decisions = {r["task"]: r["routing"] for r in records}
    # None of these should blanket-ESCALATE anymore — they resolve to the
    # writing / research / brand profiles.
    assert decisions["Write campaign emails"] != routing.ESCALATE
    assert decisions["Interview customers"] != routing.ESCALATE
    assert decisions["Positioning"] != routing.ESCALATE


def test_fuzzy_match_is_visible_in_provenance():
    records = routing.route_tasks([_task("Emails", "Copywriting")])
    prov = str(records[0].get("score_provenance", records[0]))
    assert "matched from 'copywriting'" in prov.lower()


def test_truly_unknown_skill_still_escalates():
    records = routing.route_tasks([_task("Weld hull", "underwater welding")])
    assert records[0]["routing"] == routing.ESCALATE


# ---------------------------------------------------------------------------
# Innovation on roster vocabulary
# ---------------------------------------------------------------------------

def test_innovation_credits_roster_skill_names():
    caps_demo, _, _ = innovation._team_capabilities({"research", "prototype", "writing"})
    caps_roster, _, _ = innovation._team_capabilities(
        {"ux research", "prototyping", "copywriting"}
    )
    assert caps_roster == caps_demo and caps_roster  # same credit, non-empty


# ---------------------------------------------------------------------------
# No-valid-team fallback: size cap respected + honest wording
# ---------------------------------------------------------------------------

def _human(name, skills):
    return Worker(name=name, type=HUMAN, role="r", skills=skills,
                  capacity_hours=40, workload_hours=0, cost_rate=80,
                  quality_score=7)


def test_no_valid_team_fallback_respects_cap_and_says_so():
    # Each skill exists on the roster, but no team within the size cap (2)
    # has all three -> no valid team. (Skills NOBODY has become outside help
    # instead; see test_brief_fixes.)
    employees = [
        _human("A", ["Copywriting"]), _human("B", ["customer research"]),
        _human("C", ["Brand strategy"]), _human("D", ["prototyping"]),
    ]
    tasks = [
        {"task": "Write", "required_skill": "Copywriting", "effort_hours": 10,
         "priority": 1, "dependencies": [], "is_required": True},
        {"task": "Interview", "required_skill": "customer research",
         "effort_hours": 10, "priority": 1, "dependencies": [], "is_required": True},
        {"task": "Position", "required_skill": "Brand strategy",
         "effort_hours": 10, "priority": 1, "dependencies": [], "is_required": True},
    ]
    cfg = SimConfig()
    result = project_mode.run_project_simulation(
        employees, [], {
            "optimization_objective": "balanced",
            "team_constraints": {"max_humans_per_team": 2},
            "tasks": tasks,
            "current_team_human_names": [e.name for e in employees],
            "current_team_ai_agent_names": [],
        }, cfg,
    )
    for key in ("recommended_balanced_team", "fastest_valid_team",
                "lowest_cost_valid_team", "most_innovative_valid_team"):
        opt = result["options"][key]
        assert not opt["is_valid_team"]
        # The fallback must respect the team-size cap (was: whole roster).
        assert len(opt["team_members"]) <= 2, (key, opt["team_members"])
        # Its numbers leave work out, and the payload says how much.
        assert opt["unstaffed_hours"] == 10
    rec = result["recommendation"]
    if not result["options"][rec["recommended_option"]]["is_valid_team"]:
        assert "valid options" not in rec["why"]
        assert "closest fit" in rec["why"].lower() or "No option" in rec["why"]
        assert "No team fully covers" in rec["summary_text"] or \
               "closest fit" in rec["summary_text"].lower()


def test_business_skills_route_instead_of_escalating():
    # Real marketing/ops roster wording (from a user's roster) now profiles.
    tasks = [_task(n, sk) for n, sk in [
        ("Social posts", "social media"), ("KPI review", "analytics"),
        ("Run campaign", "campaign management"), ("Launch plan", "Program management"),
        ("Legal check", "risk management"), ("Ad layouts", "Figma"),
    ]]
    records = routing.route_tasks(tasks)
    assert all(r["routing"] != routing.ESCALATE for r in records), [
        (r["task"], r["routing"]) for r in records]
    by_task = {r["task"]: r["routing"] for r in records}
    # High-stakes judgment work stays human-owned.
    assert by_task["Legal check"] == routing.HUMAN_ONLY


def test_innovation_credits_business_skills():
    caps, funcs, phases = innovation._team_capabilities(
        {"social media", "figma", "program management", "analytics"})
    assert {"creative_thinking", "analytical_thinking", "systems_thinking"} <= caps
    assert {"content", "design", "ops", "data"} <= funcs


def test_drafting_message_separates_people_skills_from_ai_only():
    from src.api import brief_parser
    msg = brief_parser._build_user_message(
        "brief", ["Coordination", "Program management", "Writing"],
        people_skills=["Program management"])
    assert "PEOPLE'S SKILLS" in msg and "Program management" in msg
    ai_line = [l for l in msg.splitlines() if l.startswith("AI-AGENT-ONLY")][0]
    assert "Coordination" in ai_line and "Program management" not in ai_line
    # Without people_skills the message is the original single list.
    assert "PEOPLE'S SKILLS" not in brief_parser._build_user_message("b", ["UX"])


def test_ai_only_skill_is_flagged_for_review():
    from src.api import brief_parser
    tasks = [
        brief_parser.DraftTask(task="Coordinate launch", required_skill="coordination",
                               effort_hours=4),
        brief_parser.DraftTask(task="Plan program", required_skill="program management",
                               effort_hours=4),
    ]
    brief_parser._reconcile_skills(
        tasks, ["Coordination", "Program management"],
        people_skills=["Program management"])
    assert tasks[0].required_skill == "Coordination"
    assert tasks[0].needs_user_review and "Only an AI agent" in tasks[0].review_reason
    assert not tasks[1].needs_user_review


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
    print("\nAll skill-matching tests passed.")
