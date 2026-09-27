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


def test_token_match_leftmost_word():
    assert skill_matching.match("customer research", KEYS) == ("research", "token")
    assert skill_matching.match("Brand strategy", KEYS) == ("brand", "token")
    assert skill_matching.match("UX research", KEYS) == ("ux", "token")
    assert skill_matching.match("Data analysis", KEYS) == ("data", "token")
    assert skill_matching.match("campaign planning", KEYS) == ("planning", "token")


def test_stem_match_bridges_suffixes():
    assert skill_matching.match("Copywriting", KEYS) == ("writing", "stem")
    assert skill_matching.match("prototyping", KEYS) == ("prototype", "stem")


def test_short_keys_never_match_by_substring():
    # "qa", "ux", "api" are too short for substring stems — no accidents.
    key, how = skill_matching.match("presentations", KEYS)
    assert key is None and how == "none"
    assert skill_matching.match("negotiation", KEYS) == (None, "none")


def test_unknown_skill_matches_nothing():
    assert skill_matching.match("Adobe Creative Suite", KEYS) == (None, "none")
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
    records = routing.route_tasks([_task("Negotiate contracts", "negotiation")])
    assert records[0]["routing"] == routing.ESCALATE


# ---------------------------------------------------------------------------
# Innovation on roster vocabulary
# ---------------------------------------------------------------------------

def test_innovation_credits_roster_skill_names():
    caps_demo, _, _ = innovation._team_capabilities({"ux", "prototype", "writing"})
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
    # Nobody (human or AI) covers "quantum sculpting" -> no valid team exists.
    employees = [
        _human("A", ["Copywriting"]), _human("B", ["customer research"]),
        _human("C", ["Brand strategy"]), _human("D", ["prototyping"]),
    ]
    tasks = [
        {"task": "Write", "required_skill": "Copywriting", "effort_hours": 10,
         "priority": 1, "dependencies": [], "is_required": True},
        {"task": "Impossible", "required_skill": "quantum sculpting",
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
    rec = result["recommendation"]
    if not result["options"][rec["recommended_option"]]["is_valid_team"]:
        assert "valid options" not in rec["why"]
        assert "closest fit" in rec["why"].lower() or "No option" in rec["why"]
        assert "No team fully covers" in rec["summary_text"] or \
               "closest fit" in rec["summary_text"].lower()


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
