"""Tests for Employee Digital Twin Seed upload + the gated roster flow.

Covers deterministic parsing/validation (CSV + Excel), sensitive-column
dropping, defaulting with flags, and the in-memory active-roster endpoints.
No data is persisted to disk.

Run from the project root::

    python -m pytest tests/test_employee_seed.py
    # or directly:
    python tests/test_employee_seed.py
"""

import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from fastapi.testclient import TestClient  # noqa: E402

from src.api import employee_seed  # noqa: E402
from src.api import routes  # noqa: E402
from src.api.app import app  # noqa: E402

client = TestClient(app)


def _csv(text: str) -> bytes:
    return text.encode("utf-8")


_GOOD_CSV = (
    "employee_id,name,job_title,department,skills,capacity_hours,workload_hours,cost_rate,quality_score,manager,innovation_capability_tags\n"
    "E1,Dana,Engineer,Platform,Python|API,40,10,90,8,Priya,systems_thinking|curiosity\n"
    "E2,Lee,Designer,Design,UX|Prototype,35,5,85,7,Priya,creative_thinking\n"
)


# ---------------------------------------------------------------------------
# Parsing / validation (pure)
# ---------------------------------------------------------------------------

def test_parse_csv_maps_fields_and_aliases():
    workers, report, preview = employee_seed.parse_seed(_csv(_GOOD_CSV), "team.csv")
    assert [w.name for w in workers] == ["Dana", "Lee"]
    # job_title alias -> role; skills split.
    assert workers[0].role == "Engineer"
    assert workers[0].skills == ["Python", "API"]
    assert workers[0].capacity_hours == 40 and workers[0].workload_hours == 10
    assert report["employee_count"] == 2
    assert report["sensitive_columns_dropped"] == []
    assert "innovation_capability_tags" in report["recommended_present"]
    # No sensitive data in preview.
    assert all("dob" not in p for p in preview[0])


def test_defaults_cost_and_quality_with_flags():
    csv = (
        "name,job_title,department,skills,capacity_hours,workload_hours\n"
        "Sam,Analyst,Data,Data|Strategy,30,8\n"
    )
    workers, report, preview = employee_seed.parse_seed(_csv(csv), "team.csv")
    assert workers[0].cost_rate == employee_seed.DEFAULT_COST_RATE
    assert workers[0].quality_score == employee_seed.DEFAULT_QUALITY_SCORE
    # Flagged in the report and per-row preview (not silent).
    assert any("cost_rate" in d for d in report["defaulted_fields"])
    assert any("quality_score" in d for d in report["defaulted_fields"])
    assert preview[0]["cost_rate_defaulted"] is True
    assert preview[0]["quality_score_defaulted"] is True


def test_sensitive_columns_dropped_and_listed():
    csv = (
        "name,job_title,department,skills,capacity_hours,workload_hours,dob,home_address,ssn,personal_email,gender\n"
        "Ana,Engineer,Platform,Python,40,10,1990-01-01,1 Main St,123-45-6789,a@x.com,F\n"
    )
    workers, report, preview = employee_seed.parse_seed(_csv(csv), "team.csv")
    dropped = set(report["sensitive_columns_dropped"])
    assert {"dob", "home_address", "ssn", "personal_email", "gender"} <= dropped
    # None of the sensitive values appear anywhere in the preview.
    blob = str(preview)
    for bad in ("1990-01-01", "1 Main St", "123-45-6789", "a@x.com"):
        assert bad not in blob


def test_manager_column_not_flagged_sensitive():
    # 'manager' contains the substring 'age' but must NOT be treated as sensitive.
    workers, report, _ = employee_seed.parse_seed(_csv(_GOOD_CSV), "team.csv")
    assert "manager" not in report["sensitive_columns_dropped"]


def test_missing_essential_column_rejected():
    csv = "name,job_title,department,capacity_hours,workload_hours\nA,Eng,Plat,40,10\n"  # no skills
    try:
        employee_seed.parse_seed(_csv(csv), "team.csv")
        assert False, "expected SeedError"
    except employee_seed.SeedError as exc:
        assert exc.status == 400
        assert "skills" in exc.message


def test_employee_id_generated_when_absent():
    csv = "name,job_title,department,skills,capacity_hours,workload_hours\nA,Eng,Plat,Python,40,10\n"
    _, report, preview = employee_seed.parse_seed(_csv(csv), "team.csv")
    assert preview[0]["employee_id"].startswith("EMP-")
    assert any("employee_id" in d for d in report["defaulted_fields"])


def test_row_with_missing_value_is_skipped_and_reported():
    csv = (
        "name,job_title,department,skills,capacity_hours,workload_hours\n"
        "Good,Eng,Plat,Python,40,10\n"
        "Bad,Eng,Plat,Python,,10\n"  # missing capacity
    )
    workers, report, _ = employee_seed.parse_seed(_csv(csv), "team.csv")
    assert [w.name for w in workers] == ["Good"]
    assert report["row_errors"] and "capacity" in report["row_errors"][0]


def test_excel_xlsx_parsing():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["name", "job_title", "department", "skills", "capacity_hours", "workload_hours"])
    ws.append(["Zoe", "Engineer", "Platform", "Python|API", 40, 12])
    buf = io.BytesIO()
    wb.save(buf)
    workers, report, _ = employee_seed.parse_seed(buf.getvalue(), "team.xlsx")
    assert workers[0].name == "Zoe" and workers[0].skills == ["Python", "API"]


# ---------------------------------------------------------------------------
# Endpoints + gated active roster
# ---------------------------------------------------------------------------

def test_active_roster_defaults_to_none():
    routes._reset_active_roster()
    try:
        r = client.get("/employees/active")
        assert r.status_code == 200
        assert r.json()["source"] == "none"
    finally:
        routes._reset_active_roster()


def test_seed_upload_becomes_active_and_drives_simulation():
    routes._reset_active_roster()
    try:
        r = client.post(
            "/employees/seed-upload",
            files={"file": ("team.csv", io.BytesIO(_csv(_GOOD_CSV)), "text/csv")},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"]["source"] == "uploaded"
        assert body["status"]["employee_count"] == 2
        # /employees now returns the uploaded seed set, not the demo 10.
        emps = client.get("/employees").json()
        assert {e["name"] for e in emps} == {"Dana", "Lee"}
        # Project simulation uses the uploaded roster.
        tasks = [{"task": "Build", "required_skill": "Python", "effort_hours": 10,
                  "priority": 1, "dependencies": [], "is_required": True}]
        sim = client.post("/simulate/project", json={
            "tasks": tasks, "optimization_objective": "balanced",
            "current_team_human_names": ["Dana"], "current_team_ai_agent_names": [],
        })
        assert sim.status_code == 200
        assert sim.json()["options"]["current_team"]["team_members"] == ["Dana"]
        # An old demo name is now unknown.
        sim2 = client.post("/simulate/project", json={
            "tasks": tasks, "optimization_objective": "balanced",
            "current_team_human_names": ["Sarah"], "current_team_ai_agent_names": [],
        })
        assert sim2.status_code == 400
    finally:
        routes._reset_active_roster()


def test_use_demo_roster_resets_to_demo():
    routes._reset_active_roster()
    try:
        client.post(
            "/employees/seed-upload",
            files={"file": ("team.csv", io.BytesIO(_csv(_GOOD_CSV)), "text/csv")},
        )
        r = client.post("/employees/use-demo")
        assert r.status_code == 200
        assert r.json()["status"]["source"] == "demo"
        emps = client.get("/employees").json()
        assert len(emps) == 10  # back to the demo roster
        assert "Sarah" in {e["name"] for e in emps}
    finally:
        routes._reset_active_roster()


def test_seed_upload_response_has_no_sensitive_data():
    routes._reset_active_roster()
    try:
        csv = (
            "name,job_title,department,skills,capacity_hours,workload_hours,ssn,medical_notes\n"
            "Ana,Engineer,Platform,Python,40,10,123-45-6789,confidential\n"
        )
        r = client.post(
            "/employees/seed-upload",
            files={"file": ("team.csv", io.BytesIO(_csv(csv)), "text/csv")},
        )
        body = r.json()
        assert "ssn" in body["status"]["report"]["sensitive_columns_dropped"]
        assert "medical_notes" in body["status"]["report"]["sensitive_columns_dropped"]
        assert "123-45-6789" not in str(body)
        assert "confidential" not in str(body)
    finally:
        routes._reset_active_roster()


def test_seed_upload_rejects_bad_type():
    routes._reset_active_roster()
    r = client.post(
        "/employees/seed-upload",
        files={"file": ("team.txt", io.BytesIO(b"hi"), "text/plain")},
    )
    assert r.status_code == 415


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
    print("\nAll employee-seed tests passed.")
