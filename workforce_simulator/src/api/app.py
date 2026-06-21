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

# Permissive CORS so a future local frontend (any port) can call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
