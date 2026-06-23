"""Tests for opt-in prior-backed routing scores.

Run from the project root with::

    python -m pytest tests/test_prior_scoring.py
    # or directly:
    python tests/test_prior_scoring.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import routing  # noqa: E402
import provenance  # noqa: E402


def _binding(confidence, **prior_overrides):
    """A controlled prior-score binding (forces a known confidence)."""
    prior_fields = {
        "ai_capability_fit": 50, "human_judgment_need": 50,
        "verification_ease": 50, "error_cost": 50, "context_sensitivity": 50,
        "repetition_level": 50, "speed_value": 50, "collaboration_value": 50,
    }
    prior_fields.update(prior_overrides)
    return {
        "matched_prior_id": "TRP-TEST",
        "match_confidence": confidence,
        "match_score": 0.9,
        "prior_fields": prior_fields,
    }


def _task(**kw):
    base = {"task": "T", "required_skill": "qa", "effort_hours": 10,
            "priority": 2, "is_required": True}
    base.update(kw)
    return base


def _by_field(record):
    return {p["field_name"]: p for p in record["score_provenance"]}


def test_prior_to_1to5_conversion():
    assert routing._prior_to_1to5(0) == 1
    assert routing._prior_to_1to5(50) == 3
    assert routing._prior_to_1to5(100) == 5


def test_disabled_matches_baseline_even_with_binding():
    task = _task()
    baseline = routing.route_task(task)
    # A binding present but use_priors False must NOT change scores/decision.
    with_binding_off = routing.route_task(task, _binding("HIGH", human_judgment_need=90), False)
    assert with_binding_off["scores"] == baseline["scores"]
    assert with_binding_off["routing"] == baseline["routing"]
    assert with_binding_off["public_priors_enabled"] is False
    # No prior provenance when disabled.
    assert all(
        p["source_type"] != provenance.MATCHED_PUBLIC_PRIOR
        for p in with_binding_off["score_provenance"]
    )


def test_high_prior_influences_score_when_enabled():
    task = _task()
    baseline = routing.route_task(task)
    rec = routing.route_task(task, _binding("HIGH", human_judgment_need=90), True)
    item = _by_field(rec)["human_judgment_need"]
    assert item["source_type"] == provenance.MATCHED_PUBLIC_PRIOR
    assert item["blend_ratio"] == 0.8
    assert item["matched_prior_id"] == "TRP-TEST"
    assert item["match_confidence"] == "HIGH"
    # The blended value differs from the pure heuristic baseline.
    assert rec["scores"]["human_judgment_need"] != baseline["scores"]["human_judgment_need"]
    assert rec["matched_prior_used"] == "TRP-TEST"


def test_medium_prior_blends_and_warns():
    task = _task()
    rec = routing.route_task(task, _binding("MEDIUM", human_judgment_need=90), True)
    item = _by_field(rec)["human_judgment_need"]
    assert item["source_type"] == provenance.MATCHED_PUBLIC_PRIOR
    assert item["blend_ratio"] == 0.5
    assert rec["prior_match_confidence"] == "MEDIUM"
    assert rec["prior_warning"]  # MEDIUM emits a warning


def test_low_prior_is_ignored():
    task = _task()
    baseline = routing.route_task(task)
    rec = routing.route_task(task, _binding("LOW", human_judgment_need=90), True)
    assert rec["scores"] == baseline["scores"]
    assert rec["matched_prior_used"] is None
    assert all(
        p["source_type"] != provenance.MATCHED_PUBLIC_PRIOR
        for p in rec["score_provenance"]
    )


def test_manual_input_overrides_matched_public_prior():
    task = _task(routing_scores={"human_judgment_need": 1})
    rec = routing.route_task(task, _binding("HIGH", human_judgment_need=90), True)
    item = _by_field(rec)["human_judgment_need"]
    # Manual wins over the prior.
    assert item["source_type"] == provenance.MANUAL_INPUT
    assert rec["scores"]["human_judgment_need"] == 1


def test_provenance_includes_matched_public_prior_when_used():
    rec = routing.route_task(_task(), _binding("HIGH", ai_capability_fit=10), True)
    used = [p for p in rec["score_provenance"]
            if p["source_type"] == provenance.MATCHED_PUBLIC_PRIOR]
    assert used
    for p in used:
        assert set(["matched_prior_id", "match_confidence", "blend_ratio"]).issubset(p)
        assert provenance.MATCHED_PUBLIC_PRIOR in provenance.VALID_SOURCE_TYPES


def test_human_learning_value_never_prior_backed():
    # There is no prior for human_learning_value, so it stays heuristic.
    rec = routing.route_task(_task(), _binding("HIGH"), True)
    item = _by_field(rec)["human_learning_value"]
    assert item["source_type"] == provenance.EXISTING_HEURISTIC


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
    print("\nAll prior-scoring tests passed.")
