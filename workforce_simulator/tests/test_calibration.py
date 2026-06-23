"""Tests for the historical calibration scaffold.

Run from the project root with::

    python -m pytest tests/test_calibration.py
    # or directly:
    python tests/test_calibration.py
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import calibration as cal  # noqa: E402


def _actual(**kw):
    base = {
        "project_id": "P1", "project_name": "Launch", "project_type": "software",
        "predicted_duration": 100, "actual_duration": 120,
        "predicted_cost": 10000, "actual_cost": 9000,
        "predicted_human_hours": 200, "actual_human_hours": 220,
        "predicted_review_hours": 20, "actual_review_hours": 35,
        "predicted_rework_hours": 10, "actual_rework_hours": 25,
        "predicted_bottleneck": "Alex", "actual_bottleneck": "Maya",
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_validation_requires_identity_fields():
    bad = _actual()
    del bad["project_name"]
    try:
        cal.validate_actual(bad)
        assert False, "expected CalibrationError"
    except cal.CalibrationError as exc:
        assert "project_name" in str(exc)


def test_validation_rejects_negative_numeric():
    try:
        cal.validate_actual(_actual(actual_cost=-1))
        assert False, "expected CalibrationError"
    except cal.CalibrationError as exc:
        assert "actual_cost" in str(exc)


def test_validation_rejects_non_numeric():
    try:
        cal.validate_actual(_actual(actual_duration="soon"))
        assert False, "expected CalibrationError"
    except cal.CalibrationError:
        pass


# ---------------------------------------------------------------------------
# Error calculations
# ---------------------------------------------------------------------------

def test_duration_error_calculation():
    c = cal.compare(_actual())
    assert c.duration_error_pct == 20.0  # 120 vs 100


def test_cost_error_calculation():
    c = cal.compare(_actual())
    assert c.cost_error_pct == -10.0  # 9000 vs 10000


def test_review_error_calculation():
    c = cal.compare(_actual())
    assert c.review_hours_error_pct == 75.0  # 35 vs 20


def test_rework_error_calculation():
    c = cal.compare(_actual())
    assert c.rework_hours_error_pct == 150.0  # 25 vs 10


def test_error_pct_handles_zero_predicted():
    assert cal.error_pct(0, 5) is None


def test_bottleneck_correctness():
    assert cal.compare(_actual()).bottleneck_correct is False
    assert cal.compare(_actual(actual_bottleneck="Alex")).bottleneck_correct is True


def test_quality_error_optional():
    assert cal.compare(_actual()).quality_error is None
    c = cal.compare(_actual(predicted_quality_score=8, actual_quality_score=7))
    assert c.quality_error == -1.0


# ---------------------------------------------------------------------------
# Suggested multipliers (generated, never applied)
# ---------------------------------------------------------------------------

def test_suggested_multipliers_generated_not_applied():
    c = cal.compare(_actual())
    sm = c.suggested_multiplier_updates
    # All six suggestion fields exist and are numeric.
    for f in ("task_duration_multiplier", "review_time_multiplier",
              "rework_multiplier", "dependency_buffer_multiplier",
              "skill_gap_penalty", "context_switching_penalty"):
        assert isinstance(getattr(sm, f), (int, float))
    assert sm.task_duration_multiplier == 1.2   # 120/100
    assert sm.review_time_multiplier == 1.75     # 35/20
    # Wrong bottleneck -> a non-zero skill-gap penalty is suggested.
    assert sm.skill_gap_penalty > 0
    # Nothing is ever auto-applied.
    assert c.applied is False


# ---------------------------------------------------------------------------
# Store + summary
# ---------------------------------------------------------------------------

def test_store_and_summary_roundtrip():
    d = tempfile.mkdtemp()
    store = os.path.join(d, "actuals.json")
    cal.save_actual(store, _actual(project_id="A"))
    cal.save_actual(store, _actual(project_id="B", actual_duration=100))
    summary = cal.summarize(store)
    assert summary["project_count"] == 2
    assert summary["mean_absolute_error_pct"]["duration_error_pct"] is not None
    assert summary["biggest_misses"]  # at least one miss listed
    # Re-saving the same project_id replaces (no duplicate).
    cal.save_actual(store, _actual(project_id="A", actual_duration=110))
    assert cal.summarize(store)["project_count"] == 2


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
    print("\nAll calibration tests passed.")
