"""Tests for the ManagerFit fit engine."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from managerfit import assessments
from managerfit.matching import (
    ALIGNMENT_THRESHOLD,
    FRICTION_THRESHOLD,
    build_fit_report,
)


def test_identical_styles_are_full_alignment():
    scores = {d.key: 4 for d in assessments.DIMENSIONS}
    report = build_fit_report(scores, dict(scores))

    assert report.overall_fit == 100
    assert len(report.alignments) == len(assessments.DIMENSIONS)
    assert report.to_discuss == []
    assert report.suggested_questions("candidate") == []


def test_opposite_styles_are_low_fit_and_all_discuss():
    manager = {d.key: 1 for d in assessments.DIMENSIONS}
    candidate = {d.key: 5 for d in assessments.DIMENSIONS}
    report = build_fit_report(manager, candidate)

    assert report.overall_fit == 0
    assert report.alignments == []
    assert len(report.to_discuss) == len(assessments.DIMENSIONS)
    # Every friction dimension should yield suggested questions for both sides.
    assert report.suggested_questions("candidate")
    assert report.suggested_questions("manager")


def test_gap_thresholds_categorize_correctly():
    # one aligned (gap 0), one minor (gap 1->actually alignment), one discuss (gap 3)
    dims = assessments.DIMENSIONS
    manager = {dims[0].key: 3, dims[1].key: 3, dims[2].key: 1}
    candidate = {dims[0].key: 3, dims[1].key: 4, dims[2].key: 4}
    report = build_fit_report(manager, candidate)

    by_key = {f.dimension.key: f for f in report.dimension_fits}
    assert by_key[dims[0].key].category == "alignment"  # gap 0
    assert by_key[dims[1].key].category == "alignment"  # gap 1 <= threshold
    assert by_key[dims[2].key].category == "discuss"     # gap 3 >= friction


def test_to_discuss_sorted_by_largest_gap_first():
    dims = assessments.DIMENSIONS
    manager = {dims[0].key: 1, dims[1].key: 2}
    candidate = {dims[0].key: 5, dims[1].key: 5}  # gaps: 4 and 3
    report = build_fit_report(manager, candidate)

    discuss = report.to_discuss
    gaps = [f.gap for f in discuss]
    assert gaps == sorted(gaps, reverse=True)
    assert discuss[0].dimension.key == dims[0].key


def test_missing_dimensions_default_to_neutral():
    # Empty assessments should not crash and should be perfectly aligned (both 3).
    report = build_fit_report({}, {})
    assert report.overall_fit == 100
    assert len(report.dimension_fits) == len(assessments.DIMENSIONS)


def test_suggested_questions_are_deduplicated():
    manager = {d.key: 1 for d in assessments.DIMENSIONS}
    candidate = {d.key: 5 for d in assessments.DIMENSIONS}
    report = build_fit_report(manager, candidate)
    qs = report.suggested_questions("candidate")
    assert len(qs) == len(set(qs))


def test_headline_reflects_score_bands():
    high = build_fit_report({d.key: 4 for d in assessments.DIMENSIONS},
                            {d.key: 4 for d in assessments.DIMENSIONS})
    low = build_fit_report({d.key: 1 for d in assessments.DIMENSIONS},
                           {d.key: 5 for d in assessments.DIMENSIONS})
    assert "alignment" in high.headline.lower()
    assert "honest conversation" in low.headline.lower()


@pytest.mark.parametrize("gap,expected", [(0, True), (1, True), (2, False)])
def test_alignment_threshold_boundary(gap, expected):
    dim = assessments.DIMENSIONS[0]
    report = build_fit_report({dim.key: 1}, {dim.key: 1 + gap})
    fit = report.dimension_fits[0]
    assert (fit.category == "alignment") is expected
