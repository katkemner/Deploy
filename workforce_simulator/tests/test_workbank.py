"""Tests for the read-only WORKBank importer.

Run from the project root with::

    python -m pytest tests/test_workbank.py
    # or directly:
    python tests/test_workbank.py
"""

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

import workbank  # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures", "workbank")


def _fixture_dir() -> str:
    """Copy the fixture CSVs into a fresh temp dir so tests can mutate them."""
    d = tempfile.mkdtemp()
    for name in workbank.REQUIRED_FILES:
        shutil.copy(os.path.join(FIXTURES, name), os.path.join(d, name))
    return d


# ---------------------------------------------------------------------------
# Importer happy path
# ---------------------------------------------------------------------------

def test_importer_loads_fixture_files():
    result = workbank.normalize_workbank(FIXTURES)
    assert result["import_status"] == "imported"
    assert result["task_count"] == 2
    assert result["occupation_count"] == 2
    assert len(result["normalized_priors"]) == 2
    assert result["source_name"] == "WORKBank"


def test_normalized_record_has_all_fields():
    result = workbank.normalize_workbank(FIXTURES)
    rec = next(r for r in result["normalized_priors"] if r["workbank_task_id"] == "WB-1")
    expected = {
        "workbank_task_id", "task_text", "occupation_title", "onet_soc_code",
        "task_type", "avg_worker_automation_desire", "avg_expert_ai_capability",
        "avg_worker_desired_has", "avg_expert_feasible_has",
        "physical_action_requirement", "uncertainty_or_high_stakes_requirement",
        "domain_expertise_requirement", "interpersonal_communication_requirement",
        "worker_sample_count", "expert_sample_count", "source_name",
        "source_confidence", "notes",
    }
    assert set(rec.keys()) == expected
    assert rec["source_name"] == "WORKBank"
    assert rec["occupation_title"] == "Software Developer"
    assert rec["onet_soc_code"] == "15-1252.00"


def test_averages_are_computed_correctly():
    result = workbank.normalize_workbank(FIXTURES)
    by_id = {r["workbank_task_id"]: r for r in result["normalized_priors"]}

    wb1 = by_id["WB-1"]
    # worker: (0.8 + 0.6) / 2 = 0.7 ; (0.4 + 0.6) / 2 = 0.5 ; n = 2
    assert wb1["avg_worker_automation_desire"] == 0.7
    assert wb1["avg_worker_desired_has"] == 0.5
    assert wb1["worker_sample_count"] == 2
    # expert: (0.9 + 0.7) / 2 = 0.8 ; (0.5 + 0.3) / 2 = 0.4 ; n = 2
    assert wb1["avg_expert_ai_capability"] == 0.8
    assert wb1["avg_expert_feasible_has"] == 0.4
    assert wb1["expert_sample_count"] == 2
    # both sources present -> confidence 1.0
    assert wb1["source_confidence"] == 1.0
    # requirement metadata carried through from the task file
    assert wb1["domain_expertise_requirement"] == 0.6

    wb2 = by_id["WB-2"]
    # worker: (0.2 + 0.3 + 0.1) / 3 = 0.2 ; n = 3
    assert wb2["avg_worker_automation_desire"] == 0.2
    assert wb2["worker_sample_count"] == 3
    # expert: single row 0.4 ; n = 1
    assert wb2["avg_expert_ai_capability"] == 0.4
    assert wb2["expert_sample_count"] == 1


def test_import_writes_normalized_json():
    out = os.path.join(tempfile.mkdtemp(), "workbank_normalized.json")
    result = workbank.import_workbank(FIXTURES, out)
    assert os.path.exists(out)
    loaded = workbank.load_normalized(out)
    assert loaded["task_count"] == result["task_count"] == 2
    assert loaded["normalized_priors"][0]["source_name"] == "WORKBank"


def test_text_fallback_join_when_task_id_absent():
    # A desires file keyed by task text (no task_id) still joins via the
    # stable-text fallback.
    d = _fixture_dir()
    with open(os.path.join(d, workbank.DESIRES_FILE), "w", encoding="utf-8") as fh:
        fh.write("task_id,task_statement,worker_automation_desire,worker_desired_has\n")
        fh.write(",Write unit tests for a module,0.5,0.5\n")
    result = workbank.normalize_workbank(d)
    wb1 = next(r for r in result["normalized_priors"] if r["workbank_task_id"] == "WB-1")
    assert wb1["worker_sample_count"] == 1
    assert wb1["avg_worker_automation_desire"] == 0.5
    shutil.rmtree(d)


# ---------------------------------------------------------------------------
# Clear failures
# ---------------------------------------------------------------------------

def test_missing_file_error_is_clear():
    d = _fixture_dir()
    os.remove(os.path.join(d, workbank.CAPABILITY_FILE))
    try:
        workbank.normalize_workbank(d)
        assert False, "expected WorkbankImportError for the missing file"
    except workbank.WorkbankImportError as exc:
        assert workbank.CAPABILITY_FILE in str(exc)
        assert "Missing required WORKBank file" in str(exc)
    finally:
        shutil.rmtree(d)


def test_malformed_column_error_is_clear():
    d = _fixture_dir()
    # Drop a required column (onet_soc_code) from the task file header + rows.
    path = os.path.join(d, workbank.TASK_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("task_id,task_statement,occupation_title,task_type,"
                 "physical_action_requirement,uncertainty_or_high_stakes_requirement,"
                 "domain_expertise_requirement,interpersonal_communication_requirement\n")
        fh.write("WB-1,Write unit tests,Software Developer,coding,0,0.2,0.6,0.3\n")
    try:
        workbank.normalize_workbank(d)
        assert False, "expected WorkbankImportError for the missing column"
    except workbank.WorkbankImportError as exc:
        assert "missing required column" in str(exc)
        assert "onet_soc_code" in str(exc)
    finally:
        shutil.rmtree(d)


def test_non_numeric_value_error_is_clear():
    d = _fixture_dir()
    path = os.path.join(d, workbank.DESIRES_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("task_id,worker_automation_desire,worker_desired_has\n")
        fh.write("WB-1,not_a_number,0.4\n")
    try:
        workbank.normalize_workbank(d)
        assert False, "expected WorkbankImportError for a non-numeric value"
    except workbank.WorkbankImportError as exc:
        assert "worker_automation_desire" in str(exc)
        assert "non-numeric" in str(exc)
    finally:
        shutil.rmtree(d)


# ---------------------------------------------------------------------------
# workbank_status (never raises) - drives the API
# ---------------------------------------------------------------------------

def test_status_imported_from_fixtures():
    out = os.path.join(tempfile.mkdtemp(), "workbank_normalized.json")
    status = workbank.workbank_status(FIXTURES, out)
    assert status["import_status"] == "imported"
    assert status["task_count"] == 2


def test_status_not_imported_when_files_missing():
    empty = tempfile.mkdtemp()
    out = os.path.join(empty, "workbank_normalized.json")
    status = workbank.workbank_status(empty, out)
    assert status["import_status"] == "not_imported"
    assert status["task_count"] == 0
    assert status["normalized_priors"] == []
    assert status["validation_warnings"]  # names the missing files


def test_status_error_on_malformed():
    d = _fixture_dir()
    # Malform the expert file by removing a required column.
    path = os.path.join(d, workbank.CAPABILITY_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("task_id,expert_feasible_has\nWB-1,0.5\n")
    out = os.path.join(d, "workbank_normalized.json")
    status = workbank.workbank_status(d, out)
    assert status["import_status"] == "error"
    assert any("expert_ai_capability" in w for w in status["validation_warnings"])
    shutil.rmtree(d)


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from src.api.app import app  # noqa: E402

client = TestClient(app)


def test_get_workbank_endpoint_structure():
    r = client.get("/priors/workbank")
    assert r.status_code == 200
    body = r.json()
    for key in ("import_status", "task_count", "occupation_count",
                "normalized_priors", "validation_warnings"):
        assert key in body, key
    assert body["import_status"] in ("imported", "not_imported", "error")
    assert isinstance(body["normalized_priors"], list)
    assert isinstance(body["validation_warnings"], list)


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
    print("\nAll WORKBank tests passed.")
