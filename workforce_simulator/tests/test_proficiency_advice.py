"""Tests for relative-capability advice and the pre-run strength check.

Covers: proficiency parsing from roster files (words, numbers, frequencies),
notes captured but never returned by any endpoint, the check listing only
the person-skill pairs the tasks need, the advice rules (person leads /
spot-check / keep review with named guardrails / keep for growth / no advice
when close or unknown), the advice-only guarantee (routing, costs and the
recommendation are identical with or without answers), answers never being
stored, and the opt-in AI suggestion (filtered to asked pairs; 503 without a
key).

Run from the project root::

    python -m pytest tests/test_proficiency_advice.py
"""

import io
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from fastapi.testclient import TestClient  # noqa: E402

import capability_advice as ca  # noqa: E402
import routing  # noqa: E402
from models import HUMAN, Assignment  # noqa: E402
from src.api import proficiency_suggest, routes  # noqa: E402
from src.api.app import app  # noqa: E402

client = TestClient(app)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parse_level_words_numbers_and_frequencies():
    assert ca.parse_level("Expert") == "almost_always"
    assert ca.parse_level("strong") == "usually"
    assert ca.parse_level("Intermediate") == "sometimes"
    assert ca.parse_level("beginner") == "rarely"
    assert ca.parse_level("almost always") == "almost_always"
    assert ca.parse_level("5") == "almost_always"
    assert ca.parse_level("3") == "sometimes"
    assert ca.parse_level("8/10") == "usually"
    assert ca.parse_level("purple") is None
    assert ca.parse_level("") is None


def test_parse_proficiency_cell_mixed_separators():
    got = ca.parse_proficiency_cell("Copywriting: expert; SQL: 2, Figma: usually | API=learning")
    assert got == {"copywriting": "almost_always", "sql": "rarely",
                   "figma": "usually", "api": "rarely"}
    assert ca.parse_proficiency_cell("no levels here") == {}
    assert ca.parse_proficiency_cell(None) == {}


# ---------------------------------------------------------------------------
# Upload + check endpoint (privacy: notes never returned)
# ---------------------------------------------------------------------------

_CSV = (
    "Employee,Skills,Skill Proficiency,Strengths,Growth Areas\n"
    "Kai,Copywriting|Brand strategy,Copywriting: expert,Fast clean drafts,Strategy depth\n"
    "Ana,UX research|Copywriting,,Great interviewer,\n"
    "Bo,Excel,,,\n"
)


def _upload(csv=_CSV):
    routes._reset_active_roster()
    r = client.post("/employees/seed-upload",
                    files={"file": ("t.csv", io.BytesIO(csv.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    return r


def test_upload_captures_proficiency_and_notes_without_leaking_notes():
    r = _upload()
    report = r.json()["status"]["report"]
    assert report["proficiency_found"] == 1
    assert report["notes_found"] == 2
    secret = "Fast clean drafts"
    assert secret not in r.text
    for path in ("/employees", "/employees/active"):
        assert secret not in client.get(path).text
    routes._reset_active_roster()


def test_check_lists_only_needed_pairs_with_file_prefill():
    _upload()
    r = client.post("/proficiency/check", json={"tasks": [
        {"task": "Write emails", "required_skill": "Copywriting"},
        {"task": "Interviews", "required_skill": "UX research"},
    ]})
    assert r.status_code == 200
    body = r.json()
    pairs = {(p["person"], p["skill"]): p for p in body["pairs"]}
    assert set(pairs) == {("Kai", "Copywriting"), ("Ana", "Copywriting"),
                          ("Ana", "UX research")}  # Bo (Excel) not asked
    assert pairs[("Kai", "Copywriting")]["prefill"] == "almost_always"
    assert pairs[("Kai", "Copywriting")]["source"] == "your roster file"
    assert pairs[("Ana", "Copywriting")]["prefill"] is None
    assert body["any_notes"] is True
    assert "Fast clean drafts" not in r.text
    assert "not stored" in body["why"]
    routes._reset_active_roster()


# ---------------------------------------------------------------------------
# Advice rules (unit)
# ---------------------------------------------------------------------------

def _task(name, skill, **extra):
    t = {"task": name, "required_skill": skill, "effort_hours": 10,
         "priority": 1, "dependencies": [], "is_required": True}
    t.update(extra)
    return t


def _assign(task, skill, person):
    return Assignment(task=task, required_skill=skill, effort_hours=10,
                      priority=1, assigned_to=person, assigned_type=HUMAN)


def _advice(tasks, people_answers):
    records = routing.route_tasks(tasks)
    assignments = [_assign(t["task"], t["required_skill"], p)
                   for t, (p, _) in zip(tasks, people_answers)]
    answers = [{"person": p, "skill": t["required_skill"], "answer": a}
               for t, (p, a) in zip(tasks, people_answers) if a]
    return ca.build_advice(records, assignments, answers)


def test_ai_clearly_stronger_easy_cheap_gives_spot_check():
    adv = _advice([_task("Emails", "Writing")], [("Kai", "rarely")])
    assert adv["items"][0]["kind"] == "spot_check"
    assert "spot-check" in adv["items"][0]["advice"]


def test_person_clearly_stronger_leads():
    adv = _advice([_task("Positioning", "Strategy")], [("Kai", "almost_always")])
    item = adv["items"][0]
    assert item["kind"] == "person_leads"
    # Task-level wording: the person's name stays out of the advice text.
    assert "Kai" not in item["advice"]
    assert item["details"]["person"] == "Kai"


def test_decision_task_keeps_full_review_and_names_why():
    adv = _advice([_task("Pick tagline", "Writing", stage="choice")], [("Kai", "rarely")])
    item = adv["items"][0]
    assert item["kind"] == "keep_review"
    assert "decision task" in item["advice"]


def test_hard_to_undo_keeps_full_review():
    adv = _advice([_task("Send launch email", "Writing", irreversible=True)], [("Kai", "rarely")])
    item = adv["items"][0]
    assert item["kind"] == "keep_review"
    assert "hard to undo" in item["advice"]


def test_skill_building_task_keeps_the_learner_on_it():
    # Strategy (learning value 4), intelligence stage -> AI fit 3 (~55%);
    # a "rarely" person (~25%) trails by 30 points, but it builds skill.
    adv = _advice([_task("Market sizing", "Strategy", stage="intelligence")], [("Kai", "rarely")])
    assert adv["items"][0]["kind"] == "keep_for_growth"


def test_close_gap_and_unknown_give_no_advice():
    close = _advice([_task("Emails", "Writing")], [("Kai", "almost_always")])
    assert close["items"] == [] and close["answered_tasks"] == 1
    unknown = _advice([_task("Emails", "Writing")], [("Kai", None)])
    assert unknown["items"] == [] and unknown["unknown_tasks"] == 1
    assert "isn't personalized" in unknown["note"]


# ---------------------------------------------------------------------------
# API: advice only, never stored
# ---------------------------------------------------------------------------

def _scenario(answers):
    return {
        "project_name": "P", "project_goal": "G",
        "optimization_objective": "balanced",
        "team_constraints": {"max_humans_per_team": 5},
        "tasks": [_task("Emails", "Writing"), _task("Positioning", "Strategy")],
        "current_team_human_names": ["Taylor", "Maya", "Priya"],
        "current_team_ai_agent_names": [],
        "proficiency_answers": answers,
    }


def test_advice_only_changes_nothing_else_and_is_not_stored():
    routes._reset_active_roster()
    client.post("/employees/use-demo")
    answers = [
        {"person": "Taylor", "skill": "Writing", "answer": "rarely"},
        {"person": "Maya", "skill": "Strategy", "answer": "almost_always"},
        {"person": "Priya", "skill": "Strategy", "answer": "almost_always"},
    ]
    with_answers = client.post("/simulate/project", json=_scenario(answers)).json()
    without = client.post("/simulate/project", json=_scenario([])).json()

    advice = with_answers["checkpoint_plan"]["capability_advice"]
    kinds = {a["task"]: a["kind"] for a in advice["items"]}
    assert kinds.get("Positioning") == "person_leads"

    # Advice only: routing, recommendation, costs and hours are identical.
    assert with_answers["task_routing"] == without["task_routing"]
    assert (with_answers["recommendation"]["recommended_option"]
            == without["recommendation"]["recommended_option"])
    for k, opt in with_answers["options"].items():
        assert opt["estimated_cost"] == without["options"][k]["estimated_cost"]
        assert opt["estimated_duration"] == without["options"][k]["estimated_duration"]

    # Not stored: the later run without answers has no advice at all.
    assert without["checkpoint_plan"]["capability_advice"]["items"] == []
    routes._reset_active_roster()


def test_invalid_answer_rejected():
    routes._reset_active_roster()
    client.post("/employees/use-demo")
    bad = _scenario([{"person": "Taylor", "skill": "Writing", "answer": "great"}])
    assert client.post("/simulate/project", json=bad).status_code == 422
    routes._reset_active_roster()


# ---------------------------------------------------------------------------
# Opt-in AI suggestion from notes
# ---------------------------------------------------------------------------

def test_suggest_returns_503_without_key():
    _upload()
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        r = client.post("/proficiency/suggest",
                        json={"pairs": [{"person": "Ana", "skill": "UX research"}]})
        assert r.status_code == 503
    finally:
        if saved is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved
        routes._reset_active_roster()


def test_suggest_filters_to_asked_pairs_and_sends_only_their_notes():
    captured = {}
    output = proficiency_suggest._ModelOutput(suggestions=[
        proficiency_suggest._Suggestion(person="Ana", skill="UX research",
                                        answer="almost_always", reason="Great interviewer"),
        # Invented pair the model wasn't asked about -> must be dropped.
        proficiency_suggest._Suggestion(person="Zed", skill="Sales",
                                        answer="usually", reason="made up"),
    ])

    class _Msgs:
        def parse(self, **kw):
            captured.update(kw)
            return types.SimpleNamespace(parsed_output=output, stop_reason="end_turn")

    fake = types.ModuleType("anthropic")
    for name in ("RateLimitError", "AuthenticationError", "BadRequestError", "APIConnectionError"):
        setattr(fake, name, type(name, (Exception,), {}))
    fake.Anthropic = lambda *a, **k: types.SimpleNamespace(messages=_Msgs())

    saved_mod = sys.modules.get("anthropic")
    saved_key = os.environ.get("ANTHROPIC_API_KEY")
    sys.modules["anthropic"] = fake
    os.environ["ANTHROPIC_API_KEY"] = "sk-test-dummy"
    try:
        notes = {"Ana": "Strengths: Great interviewer", "Kai": "Strengths: Fast clean drafts"}
        got = proficiency_suggest.suggest(
            [{"person": "Ana", "skill": "UX research"},
             {"person": "Bo", "skill": "Excel"}],  # Bo has no notes -> skipped
            notes,
        )
    finally:
        if saved_mod is not None:
            sys.modules["anthropic"] = saved_mod
        else:
            sys.modules.pop("anthropic", None)
        if saved_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = saved_key

    assert got == [{"person": "Ana", "skill": "UX research",
                    "answer": "almost_always", "reason": "Great interviewer"}]
    sent = captured["messages"][0]["content"]
    assert "Great interviewer" in sent
    assert "Fast clean drafts" not in sent  # Kai wasn't asked about


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
    print("\nAll proficiency-advice tests passed.")
