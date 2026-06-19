"""ManagerFit web app (Flask).

Routes
------
* ``/``                          — landing page + directory of profiles
* ``/assess/manager``            — manager assessment form
* ``/assess/candidate``          — candidate assessment form
* ``/manager/<token>``           — manager profile page (the "job product")
* ``/candidate/<token>``         — candidate profile page
* ``/fit/<manager>/<candidate>`` — candidate-manager fit analysis

The app is deliberately dependency-light: Flask + the pure-Python domain logic
in this package. Run it with ``python -m managerfit.app`` or via ``flask``.
"""

from __future__ import annotations

import os
from pathlib import Path

from flask import (
    Flask,
    abort,
    redirect,
    render_template,
    request,
    url_for,
)

from . import assessments
from .matching import build_fit_report
from .storage import Store

DATA_PATH = os.environ.get("MANAGERFIT_DATA", str(Path(__file__).parent.parent / "data" / "store.json"))


def create_app(store: Store | None = None) -> Flask:
    app = Flask(__name__)
    app.config["STORE"] = store or Store(DATA_PATH)

    def get_store() -> Store:
        return app.config["STORE"]

    # ------------------------------------------------------------------ #
    # Form parsing helpers
    # ------------------------------------------------------------------ #
    def parse_scores(form) -> dict[str, int]:
        scores = assessments.default_scores()
        for dim in assessments.DIMENSIONS:
            raw = form.get(f"dim_{dim.key}")
            if raw is not None:
                scores[dim.key] = max(1, min(5, int(raw)))
        return scores

    def parse_big_five(form) -> dict[str, int]:
        bf = assessments.default_big_five()
        for key, _, _ in assessments.BIG_FIVE:
            raw = form.get(f"bf_{key}")
            if raw is not None:
                bf[key] = max(1, min(5, int(raw)))
        return bf

    # ------------------------------------------------------------------ #
    # Pages
    # ------------------------------------------------------------------ #
    @app.route("/")
    def index():
        store = get_store()
        return render_template(
            "index.html",
            managers=store.list_managers(),
            candidates=store.list_candidates(),
        )

    @app.route("/assess/manager", methods=["GET", "POST"])
    def assess_manager():
        if request.method == "POST":
            profile = {
                "name": request.form.get("name", "").strip() or "Unnamed Manager",
                "role": request.form.get("role", "").strip(),
                "company": request.form.get("company", "").strip(),
                "philosophy": request.form.get("philosophy", "").strip(),
                "scores": parse_scores(request.form),
                "big_five": parse_big_five(request.form),
                "strengths": request.form.getlist("strengths")[:5],
            }
            token = get_store().save_manager(profile)
            return redirect(url_for("manager_profile", token=token))
        return render_template(
            "assess_manager.html",
            dimensions=assessments.DIMENSIONS,
            big_five=assessments.BIG_FIVE,
            strengths=assessments.CLIFTON_STRENGTHS,
        )

    @app.route("/assess/candidate", methods=["GET", "POST"])
    def assess_candidate():
        if request.method == "POST":
            profile = {
                "name": request.form.get("name", "").strip() or "Unnamed Candidate",
                "headline": request.form.get("headline", "").strip(),
                "scores": parse_scores(request.form),
                "big_five": parse_big_five(request.form),
                "strengths": request.form.getlist("strengths")[:5],
            }
            token = get_store().save_candidate(profile)
            return redirect(url_for("candidate_profile", token=token))
        return render_template(
            "assess_candidate.html",
            dimensions=assessments.DIMENSIONS,
            big_five=assessments.BIG_FIVE,
            strengths=assessments.CLIFTON_STRENGTHS,
        )

    @app.route("/manager/<token>")
    def manager_profile(token: str):
        store = get_store()
        manager = store.get_manager(token)
        if not manager:
            abort(404)
        return render_template(
            "manager_profile.html",
            manager=manager,
            dimensions=assessments.DIMENSIONS,
            dimensions_by_key=assessments.DIMENSIONS_BY_KEY,
            big_five=assessments.BIG_FIVE,
            candidates=store.list_candidates(),
        )

    @app.route("/candidate/<token>")
    def candidate_profile(token: str):
        store = get_store()
        candidate = store.get_candidate(token)
        if not candidate:
            abort(404)
        return render_template(
            "candidate_profile.html",
            candidate=candidate,
            dimensions=assessments.DIMENSIONS,
            dimensions_by_key=assessments.DIMENSIONS_BY_KEY,
            big_five=assessments.BIG_FIVE,
            managers=store.list_managers(),
        )

    @app.route("/fit/<manager_token>/<candidate_token>")
    def fit(manager_token: str, candidate_token: str):
        store = get_store()
        manager = store.get_manager(manager_token)
        candidate = store.get_candidate(candidate_token)
        if not manager or not candidate:
            abort(404)
        report = build_fit_report(
            manager["scores"],
            candidate["scores"],
            manager_name=manager["name"],
            candidate_name=candidate["name"],
        )
        return render_template(
            "fit.html",
            report=report,
            manager=manager,
            candidate=candidate,
        )

    @app.template_filter("pct_class")
    def pct_class(value: int) -> str:
        if value >= 80:
            return "good"
        if value >= 60:
            return "ok"
        return "watch"

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=True)
