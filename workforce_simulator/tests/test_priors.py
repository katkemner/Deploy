"""Tests for the public evidence priors foundation.

Run from the project root with::

    python -m pytest tests/test_priors.py
    # or directly:
    python tests/test_priors.py
"""

import copy
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import priors  # noqa: E402

SEED_PATH = os.path.join(ROOT, "data", "priors", "public_priors_seed.json")


def _write_temp(data) -> str:
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def test_seed_file_loads():
    bundle = priors.load_priors(SEED_PATH)
    assert bundle.representative_seed is True
    assert len(bundle.source_weights) == 5
    assert len(bundle.evidence_priors) == 6
    assert len(bundle.task_routing_priors) == 5
    assert len(bundle.hybrid_guardrail_priors) == 3
    # The five seed source categories are present.
    names = {s.source_name for s in bundle.source_weights}
    assert names == set(priors.SOURCE_CATEGORIES)


def test_to_dict_has_all_sections():
    d = priors.load_priors(SEED_PATH).to_dict()
    for section in (
        "source_weights", "evidence_priors",
        "task_routing_priors", "hybrid_guardrail_priors",
    ):
        assert section in d and isinstance(d[section], list)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _seed_data():
    with open(SEED_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_invalid_source_weight_fails():
    data = _seed_data()
    data["source_weights"][0]["source_weight"] = 1.5  # > 1
    path = _write_temp(data)
    try:
        try:
            priors.load_priors(path)
            assert False, "expected PriorsError for out-of-range source_weight"
        except priors.PriorsError as exc:
            assert "source_weight" in str(exc)
    finally:
        os.remove(path)


def test_negative_source_weight_fails():
    data = _seed_data()
    data["source_weights"][0]["source_weight"] = -0.1
    path = _write_temp(data)
    try:
        try:
            priors.load_priors(path)
            assert False, "expected PriorsError"
        except priors.PriorsError:
            pass
    finally:
        os.remove(path)


def test_invalid_prior_score_fails():
    data = _seed_data()
    data["task_routing_priors"][0]["ai_capability_fit_prior"] = 150  # > 100
    path = _write_temp(data)
    try:
        try:
            priors.load_priors(path)
            assert False, "expected PriorsError for out-of-range prior score"
        except priors.PriorsError as exc:
            assert "ai_capability_fit_prior" in str(exc)
    finally:
        os.remove(path)


def test_invalid_hybrid_score_fails():
    data = _seed_data()
    data["hybrid_guardrail_priors"][0]["human_ai_synergy_prior"] = 200
    path = _write_temp(data)
    try:
        try:
            priors.load_priors(path)
            assert False, "expected PriorsError"
        except priors.PriorsError as exc:
            assert "human_ai_synergy_prior" in str(exc)
    finally:
        os.remove(path)


def test_missing_required_field_fails():
    data = _seed_data()
    del data["task_routing_priors"][0]["skill"]
    path = _write_temp(data)
    try:
        try:
            priors.load_priors(path)
            assert False, "expected PriorsError for missing field"
        except priors.PriorsError as exc:
            assert "skill" in str(exc)
    finally:
        os.remove(path)


def test_missing_file_fails_cleanly():
    try:
        priors.load_priors("/no/such/priors.json")
        assert False, "expected PriorsError"
    except priors.PriorsError as exc:
        assert "not found" in str(exc)


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
    print("\nAll priors tests passed.")
