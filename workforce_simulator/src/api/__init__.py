"""FastAPI layer for the workforce simulator.

This package wraps the existing simulation engine in an HTTP API. It does
**not** re-implement any simulation logic - every route delegates to the
engine modules (``data_loader``, ``config_loader``, ``simulator``,
``optimizer``, ``scheduler``, ``scoring``, ``exporter``).

Those engine modules live one directory up (in ``src/``) and use flat
imports (``import simulator`` etc.). To let both the engine and this package
import them the same way, we add the ``src`` directory to ``sys.path`` here,
so simply importing ``src.api`` wires everything up regardless of how the app
is launched.
"""

from __future__ import annotations

import os
import sys

# Directory containing the engine modules (the parent of this ``api`` package).
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
