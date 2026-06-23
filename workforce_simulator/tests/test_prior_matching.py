"""Tests for deterministic task-to-prior matching (preview only).

Run from the project root with::

    python -m pytest tests/test_prior_matching.py
    # or directly:
    python tests/test_prior_matching.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import prior_matching as pm  # noqa: E402
import priors  # noqa: E402

SEED_PATH = os.path.join(ROOT, "data", "priors", "public_priors_seed.json")
_BUNDLE = priors.load_priors(SEED_PATH)
_CANDS = pm.build_candidates(_BUNDLE)


def test_confidence_thresholds():
    assert pm.confidence_for(0.70) == pm.HIGH
    assert pm.confidence_for(0.69) == pm.MEDIUM
    assert pm.confidence_for(0.45) == pm.MEDIUM
    assert pm.confidence_for(0.44) == pm.LOW


def test_exact_match_is_high():
    task = {
        "task": "QA", "required_skill": "QA", "task_type": "qa",
        "description": "qa", "expected_output": "qa",
    }
    m = pm.match_task(task, _CANDS)
    assert m.matched_prior_id == "TRP-QA"
    assert m.match_confidence == pm.HIGH
    assert m.match_score >= 0.70


def test_similar_wording_is_medium_or_high():
    task = {"task": "Quality assurance testing of the service", "required_skill": "QA"}
    m = pm.match_task(task, _CANDS)
    assert m.match_confidence in (pm.MEDIUM, pm.HIGH)
    assert m.match_score >= 0.45


def test_unrelated_task_is_low():
    task = {"task": "Cook dinner for the office party", "required_skill": "Cooking"}
    m = pm.match_task(task, _CANDS)
    assert m.match_confidence == pm.LOW
    assert m.match_score < 0.45


def test_returns_top_candidates():
    task = {"task": "User research interviews", "required_skill": "Research"}
    m = pm.match_task(task, _CANDS)
    assert 1 <= len(m.candidates) <= 3
    # Candidates are sorted by descending score.
    scores = [c["match_score"] for c in m.candidates]
    assert scores == sorted(scores, reverse=True)
    assert m.match_method == pm.MATCH_METHOD


def test_matching_is_deterministic():
    task = {"task": "Write the API documentation", "required_skill": "Writing"}
    a = pm.match_task(task, _CANDS).as_dict()
    b = pm.match_task(task, _CANDS).as_dict()
    assert a == b


def test_normalize_removes_punctuation_and_stopwords():
    toks = pm.normalize("The QA-testing, of the API!")
    assert "the" not in toks and "of" not in toks
    assert "qa" in toks and "testing" in toks and "api" in toks


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
    print("\nAll prior-matching tests passed.")
