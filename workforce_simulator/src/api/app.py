"""FastAPI application for the workforce simulator.

Run locally with::

    cd workforce_simulator
    uvicorn src.api.app:app --reload

Then open:

* API root  -> http://127.0.0.1:8000
* Swagger UI -> http://127.0.0.1:8000/docs

The app is a thin HTTP wrapper around the existing engine; all simulation
work happens in the engine modules under ``src/``.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router

app = FastAPI(
    title="Workforce Simulator API",
    description=(
        "HTTP API around the deterministic workforce simulation engine. "
        "Compare combinations of people and AI agents for a project and "
        "predict duration, cost, skill coverage, workload balance, "
        "productivity, and risk."
    ),
    version="1.0.0",
)


def _normalize_origin(origin: str) -> str:
    """Normalize one CORS origin: a bare hostname becomes ``https://host``.

    ``*`` is left as-is. A full ``http(s)://`` origin is used unchanged (minus a
    trailing slash). This lets the env var hold either a full URL or just a
    hostname (e.g. what Render's ``fromService`` injects).
    """
    origin = origin.strip()
    if not origin or origin == "*":
        return origin
    if not origin.lower().startswith(("http://", "https://")):
        origin = "https://" + origin
    return origin.rstrip("/")


def _cors_origins() -> list[str]:
    """Allowed CORS origins, from ``CORS_ALLOW_ORIGINS`` (comma-separated).

    Defaults to ``["*"]`` when the variable is unset or blank, which preserves
    the original permissive local-dev behaviour. In staging/production set it to
    the deployed frontend origin(s), e.g.
    ``CORS_ALLOW_ORIGINS=https://workforce-simulator-web.onrender.com`` (a bare
    hostname is also accepted).
    """
    raw = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
    if not raw:
        return ["*"]
    return [_normalize_origin(o) for o in raw.split(",") if o.strip()]


# CORS so the frontend (local on any port, or the deployed static site) can call
# the API. Origins are configurable by environment variable; default is "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/", tags=["meta"])
def root() -> dict:
    """Friendly landing payload pointing at the docs."""
    return {
        "name": "Workforce Simulator API",
        "docs": "/docs",
        "health": "/health",
    }
