"""Command-line entry point for the workforce simulator.

Running::

    python src/main.py

will:

1. Load the sample CSV files from ``data/``.
2. Generate every valid team combination (2-5 humans, 0-2 AI agents).
3. Simulate and score each team.
4. Rank and print the top 5 teams to the terminal.
5. Save full results to ``outputs/results.json`` and ``outputs/results.csv``.

No arguments, API keys, or network access are required.
"""

from __future__ import annotations

import os
import sys

# Make the sibling modules importable whether run as ``python src/main.py``
# from the project root or from inside ``src/``.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import load_all          # noqa: E402
from optimizer import generate_teams, rank_teams  # noqa: E402
from exporter import export_json, export_csv      # noqa: E402


# Resolve paths relative to the project root (the parent of ``src/``).
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")


def print_top_teams(results) -> None:
    """Pretty-print the ranked teams to the terminal."""
    print("\n" + "=" * 70)
    print(" TOP {} TEAMS".format(len(results)))
    print("=" * 70)
    for r in results:
        humans = ", ".join(r.team.human_names)
        ais = ", ".join(r.team.ai_names) if r.team.ai_names else "(none)"
        print(f"\n#{r.rank}  total_score = {r.total_score}")
        print(f"   Humans   : {humans}")
        print(f"   AI agents: {ais}")
        print(
            "   coverage={cov}  capacity_fit={cap}  productivity={prod}  "
            "balance={bal}".format(
                cov=r.skill_coverage_score,
                cap=r.capacity_fit_score,
                prod=r.productivity_score,
                bal=r.workload_balance_score,
            )
        )
        print(
            "   cost=${cost}  duration={dur}h  risk={risk}  "
            "confidence={conf}".format(
                cost=r.estimated_cost,
                dur=r.estimated_duration,
                risk=r.risk_score,
                conf=r.confidence_score,
            )
        )
        if r.missing_skills:
            print("   missing skills  : " + ", ".join(r.missing_skills))
        if r.overloaded_members:
            print("   overloaded      : " + ", ".join(r.overloaded_members))
        print("   why: " + r.plain_english_explanation)
    print("\n" + "=" * 70)


def main() -> None:
    print("Loading data from:", DATA_DIR)
    employees, ai_agents, tasks = load_all(DATA_DIR)
    print(
        f"Loaded {len(employees)} employees, {len(ai_agents)} AI agents, "
        f"{len(tasks)} tasks."
    )

    team_count = len(generate_teams(employees, ai_agents))
    print(f"Generated {team_count} unique team combinations. Simulating...")

    results = rank_teams(employees, ai_agents, tasks, top_n=5)
    print_top_teams(results)

    json_path = os.path.join(OUTPUT_DIR, "results.json")
    csv_path = os.path.join(OUTPUT_DIR, "results.csv")
    export_json(results, json_path)
    export_csv(results, csv_path)
    print(f"\nSaved JSON -> {json_path}")
    print(f"Saved CSV  -> {csv_path}")


if __name__ == "__main__":
    main()
