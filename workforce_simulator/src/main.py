"""Command-line entry point for the workforce simulator.

Running::

    python src/main.py

will:

1. Load the sample CSV files from ``data/`` and the config from
   ``config/scoring_weights.json``.
2. Generate every valid team within the configured size limits.
3. Simulate, schedule (critical path), and score each team.
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

from data_loader import load_all                  # noqa: E402
from config_loader import load_config             # noqa: E402
from optimizer import generate_teams, rank_teams  # noqa: E402
from exporter import export_json, export_csv      # noqa: E402


# Resolve paths relative to the project root (the parent of ``src/``).
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "scoring_weights.json")


def print_top_teams(results) -> None:
    """Pretty-print the ranked teams to the terminal."""
    print("\n" + "=" * 72)
    print(" TOP {} TEAMS".format(len(results)))
    print("=" * 72)
    for r in results:
        humans = ", ".join(r.team.human_names)
        ais = ", ".join(r.team.ai_names) if r.team.ai_names else "(none)"
        valid = "VALID" if r.is_valid_team else "INVALID"
        print(f"\n#{r.rank}  total_score = {r.total_score}   [{valid}]")
        print(f"   Humans   : {humans}")
        print(f"   AI agents: {ais}")
        print(
            "   required_coverage={rc}  optional_coverage={oc}  "
            "capacity_fit={cap}".format(
                rc=r.required_skill_coverage_score,
                oc=r.optional_skill_coverage_score,
                cap=r.capacity_fit_score,
            )
        )
        print(
            "   productivity={prod}  balance={bal}  risk={risk}  "
            "confidence={conf}".format(
                prod=r.productivity_score,
                bal=r.workload_balance_score,
                risk=r.risk_score,
                conf=r.confidence_score,
            )
        )
        print(
            "   cost=${cost}  duration={dur}h".format(
                cost=r.estimated_cost, dur=r.estimated_duration
            )
        )
        print("   critical path: " + " -> ".join(r.critical_path))
        if r.missing_required_skills:
            print("   missing REQUIRED: " + ", ".join(r.missing_required_skills))
        if r.missing_optional_skills:
            print("   missing optional: " + ", ".join(r.missing_optional_skills))
        if r.overloaded_members:
            print("   overloaded      : " + ", ".join(r.overloaded_members))
        print("   why: " + r.plain_english_explanation)
    print("\n" + "=" * 72)


def main() -> None:
    print("Loading config from:", CONFIG_PATH)
    config = load_config(CONFIG_PATH)
    print(
        "  require_full_required_skill_coverage = "
        f"{config.require_full_required_skill_coverage}"
    )
    print(
        f"  team size: humans {config.min_humans_per_team}-"
        f"{config.max_humans_per_team}, AI agents "
        f"{config.min_ai_agents_per_team}-{config.max_ai_agents_per_team}"
    )

    print("Loading data from:", DATA_DIR)
    employees, ai_agents, tasks = load_all(DATA_DIR)
    print(
        f"Loaded {len(employees)} employees, {len(ai_agents)} AI agents, "
        f"{len(tasks)} tasks."
    )

    team_count = len(generate_teams(employees, ai_agents, config))
    print(f"Generated {team_count} unique team combinations. Simulating...")

    results = rank_teams(employees, ai_agents, tasks, config, top_n=5)
    print_top_teams(results)

    json_path = os.path.join(OUTPUT_DIR, "results.json")
    csv_path = os.path.join(OUTPUT_DIR, "results.csv")
    export_json(results, json_path)
    export_csv(results, csv_path)
    print(f"\nSaved JSON -> {json_path}")
    print(f"Saved CSV  -> {csv_path}")


if __name__ == "__main__":
    main()
