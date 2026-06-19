"""The ManagerFit fit engine.

Given a manager assessment and a candidate assessment, produce a structured fit
analysis. The engine follows the PRD's guiding principle:

    The platform does not score managers as good or bad.
    The platform identifies likely areas of alignment and potential friction.

So the output is intentionally framed as *alignment* and *areas to discuss*,
each with concrete, suggested interview questions for both sides — never a
verdict on whether a manager is "good".

The math is deliberately simple and explainable: for each shared work-style
dimension we compare the manager's operating value to the candidate's preferred
value on the same 1-5 scale. A small gap means alignment; a large gap means an
area worth discussing. The overall "fit" percentage is the average closeness
across all dimensions, surfaced as a conversation starter rather than a grade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .assessments import DIMENSIONS, DIMENSIONS_BY_KEY, Dimension

# A gap of 0-1 points on the 1-5 scale is treated as alignment; 3-4 as friction.
ALIGNMENT_THRESHOLD = 1
FRICTION_THRESHOLD = 2
MAX_GAP = 4  # max possible distance on a 1-5 scale


@dataclass
class DimensionFit:
    """The comparison result for a single work-style dimension."""

    dimension: Dimension
    manager_value: int
    candidate_value: int

    @property
    def gap(self) -> int:
        return abs(self.manager_value - self.candidate_value)

    @property
    def closeness(self) -> float:
        """1.0 == identical styles, 0.0 == opposite ends of the scale."""
        return 1.0 - (self.gap / MAX_GAP)

    @property
    def category(self) -> str:
        if self.gap <= ALIGNMENT_THRESHOLD:
            return "alignment"
        if self.gap >= FRICTION_THRESHOLD:
            return "discuss"
        return "minor"

    @property
    def summary(self) -> str:
        """Plain-language description of how the two sides line up."""
        dim = self.dimension
        if self.category == "alignment":
            return f"Both lean toward {dim.label_for(self.manager_value).lower()}."
        return (
            f"Manager operates as “{dim.label_for(self.manager_value)}”, "
            f"while the candidate prefers “{dim.label_for(self.candidate_value)}”."
        )

    def questions_for(self, side: str) -> List[str]:
        """Suggested interview questions for ``side`` ('candidate' or 'manager')."""
        return self.dimension.discuss_questions.get(side, [])


@dataclass
class FitReport:
    """The full fit analysis between one manager and one candidate."""

    dimension_fits: List[DimensionFit]
    manager_name: str = "Manager"
    candidate_name: str = "Candidate"

    # -- headline numbers --------------------------------------------------- #
    @property
    def overall_fit(self) -> int:
        """Average closeness across dimensions, as a 0-100 conversation score."""
        if not self.dimension_fits:
            return 0
        avg = sum(f.closeness for f in self.dimension_fits) / len(self.dimension_fits)
        return round(avg * 100)

    @property
    def headline(self) -> str:
        score = self.overall_fit
        if score >= 80:
            return "Strong natural alignment — a few things still worth exploring."
        if score >= 60:
            return "Promising fit with some meaningful areas to discuss."
        return "Notable style differences — worth an honest conversation early."

    # -- grouped views ------------------------------------------------------ #
    @property
    def alignments(self) -> List[DimensionFit]:
        return [f for f in self.dimension_fits if f.category == "alignment"]

    @property
    def to_discuss(self) -> List[DimensionFit]:
        # Largest gaps first — the most important conversations surface at the top.
        return sorted(
            (f for f in self.dimension_fits if f.category == "discuss"),
            key=lambda f: f.gap,
            reverse=True,
        )

    @property
    def minor(self) -> List[DimensionFit]:
        return [f for f in self.dimension_fits if f.category == "minor"]

    # -- suggested questions ------------------------------------------------ #
    def suggested_questions(self, side: str) -> List[str]:
        """De-duplicated questions for a side, drawn from the friction areas."""
        seen: set[str] = set()
        ordered: List[str] = []
        for fit in self.to_discuss:
            for q in fit.questions_for(side):
                if q not in seen:
                    seen.add(q)
                    ordered.append(q)
        return ordered


def build_fit_report(
    manager_scores: Dict[str, int],
    candidate_scores: Dict[str, int],
    *,
    manager_name: str = "Manager",
    candidate_name: str = "Candidate",
) -> FitReport:
    """Compare a manager's and candidate's work-style scores into a FitReport.

    Missing dimensions on either side default to a neutral 3 so the engine never
    crashes on a partially completed assessment.
    """
    fits: List[DimensionFit] = []
    for dim in DIMENSIONS:
        m = int(manager_scores.get(dim.key, 3))
        c = int(candidate_scores.get(dim.key, 3))
        fits.append(DimensionFit(dimension=dim, manager_value=m, candidate_value=c))
    return FitReport(
        dimension_fits=fits,
        manager_name=manager_name,
        candidate_name=candidate_name,
    )
