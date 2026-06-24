"""Tests for the manual calibration apply flow.

Run from the project root with::

    python -m pytest tests/test_calibration_apply.py
    # or directly:
    python tests/test_calibration_apply.py
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import calibration as cal  # noqa: E402


def _actual(project_id="P1", **kw):
    base = {
        "project_id": project_id, "project_name": "X", "project_type": "sw",
        "predicted_duration": 100, "actual_duration": 130,
        "predicted_cost": 10000, "actual_cost": 10500,
        "predicted_human_hours": 200, "actual_human_hours": 230,
        "predicted_review_hours": 20, "actual_review_hours": 35,
        "predicted_rework_hours": 10, "actual_rework_hours": 25,
        "predicted_bottleneck": "Alex", "actual_bottleneck": "Maya",
    }
    base.update(kw)
    return base


def _paths():
    d = tempfile.mkdtemp()
    actuals = os.path.join(d, "actuals.json")
    cfg = os.path.join(d, "applied.json")
    state = os.path.join(d, "state.json")
    cal.save_actual(actuals, _actual())
    return actuals, cfg, state


def test_proposals_generated_but_not_applied():
    actuals, cfg, state = _paths()
    proposals = cal.all_proposals(actuals, cfg, state)
    assert len(proposals) == 6
    assert all(not p["applied"] and not p["rejected"] for p in proposals)
    # Config is still neutral (nothing applied automatically).
    mults = cal.load_calibration_config(cfg)["multipliers"]
    assert mults["task_duration_multiplier"] == 1.0
    assert mults["skill_gap_penalty"] == 0.0


def test_selected_proposal_updates_config():
    actuals, cfg, state = _paths()
    res = cal.apply_proposals(["P1::task_duration_multiplier"], "n", actuals, cfg, state)
    assert len(res["applied_proposals"]) == 1
    assert res["updated_config"]["task_duration_multiplier"] == 1.3  # 130/100
    # Persisted.
    assert cal.load_calibration_config(cfg)["multipliers"]["task_duration_multiplier"] == 1.3


def test_unselected_proposal_does_not_update_config():
    actuals, cfg, state = _paths()
    cal.apply_proposals(["P1::task_duration_multiplier"], "", actuals, cfg, state)
    mults = cal.load_calibration_config(cfg)["multipliers"]
    # review/rework were not selected -> still neutral.
    assert mults["review_time_multiplier"] == 1.0
    assert mults["rework_multiplier"] == 1.0


def test_rejected_proposal_does_not_update_config():
    actuals, cfg, state = _paths()
    cal.reject_proposals(["P1::review_time_multiplier"], actuals, state)
    # Applying a rejected proposal is skipped (config unchanged).
    res = cal.apply_proposals(["P1::review_time_multiplier"], "", actuals, cfg, state)
    assert res["applied_proposals"] == []
    assert res["rejected_or_skipped_proposals"][0]["reason"] == "previously rejected"
    assert cal.load_calibration_config(cfg)["multipliers"]["review_time_multiplier"] == 1.0


def test_invalid_proposal_id_is_handled_safely():
    actuals, cfg, state = _paths()
    res = cal.apply_proposals(["does-not-exist"], "", actuals, cfg, state)
    assert res["applied_proposals"] == []
    assert res["rejected_or_skipped_proposals"][0]["reason"] == "unknown proposal id"
    # No config change.
    assert cal.load_calibration_config(cfg)["multipliers"]["task_duration_multiplier"] == 1.0


def test_apply_changes_future_config_values():
    actuals, cfg, state = _paths()
    before = cal.load_calibration_config(cfg)["multipliers"]["task_duration_multiplier"]
    cal.apply_proposals(["P1::task_duration_multiplier"], "", actuals, cfg, state)
    after = cal.load_calibration_config(cfg)["multipliers"]["task_duration_multiplier"]
    assert before == 1.0 and after == 1.3 and after != before


def test_apply_records_traceable_provenance():
    actuals, cfg, state = _paths()
    cal.apply_proposals(["P1::task_duration_multiplier"], "Q3 review", actuals, cfg, state)
    prov = cal.load_calibration_config(cfg)["provenance"]
    assert len(prov) == 1
    entry = prov[0]
    assert entry["updated_by"] == cal.CALIBRATION_APPLY_SOURCE
    assert entry["source_project_id"] == "P1"
    assert entry["previous_value"] == 1.0
    assert entry["new_value"] == 1.3
    assert entry["multiplier_name"] == "task_duration_multiplier"
    assert "reason" in entry


def test_applied_proposal_marked_applied_in_state():
    actuals, cfg, state = _paths()
    cal.apply_proposals(["P1::task_duration_multiplier"], "", actuals, cfg, state)
    proposals = {p["proposal_id"]: p for p in cal.all_proposals(actuals, cfg, state)}
    assert proposals["P1::task_duration_multiplier"]["applied"] is True
    assert proposals["P1::review_time_multiplier"]["applied"] is False


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
    print("\nAll calibration-apply tests passed.")
