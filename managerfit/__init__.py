"""ManagerFit — a talent attraction layer where the manager is part of the job product.

This package contains the MVP domain logic:

* ``assessments`` — the shared work-style dimensions managers and candidates rate,
  plus the lighter-weight profile inputs (Big Five, CliftonStrengths).
* ``matching``    — the fit engine that turns two assessments into areas of
  alignment, areas to discuss, and suggested interview questions.
* ``storage``     — a tiny JSON-file persistence layer for the demo.

The web layer lives in :mod:`managerfit.app`.
"""

__all__ = ["assessments", "matching", "storage"]
__version__ = "0.1.0"
