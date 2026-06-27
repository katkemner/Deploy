"""Project Mode orchestration.

Implements the project-first decision flow behind ``POST /simulate/project``.
Given a project scenario (goal, tasks, the manager's current team, an
objective, and constraints), it produces five decision options and a
deterministic recommendation:

* Current Team               - exactly what the manager selected
* AI-Assisted Current Team   - their humans + greedily chosen AI agents
* Recommended Balanced Team  - highest total-score valid team
* Fastest Valid Team         - shortest duration valid team
* Lowest-Cost Valid Team     - cheapest valid team

It reuses the existing engine (``optimizer``, ``simulator``, ``scoring``,
``exporter``) - no scoring or scheduling logic is reimplemented here.
Everything is deterministic; no LLM is used.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional, Tuple

from dataclasses import replace as _replace

import exporter
import optimizer
import pareto
import routing
import staffing_strategies
from config_loader import SimConfig
from models import Task, Team, Worker
from simulator import SimulationResult, simulate_team


# Objective keys accepted from the frontend.
OBJECTIVES = {
    "balanced",
    "fastest",
    "lowest_cost",
    "best_skill_coverage",
    "best_workload_balance",
    "lowest_risk",
    "most_innovative",
}

# Maps each decision option to a human-friendly label. The order here is also
# the display order. AI agents are dynamic (conjured per plan, no fixed
# catalog); the human/AI split differs per staffing strategy.
OPTION_LABELS = {
    "current_team": "Current Team",
    "human_core_ai_gap_fill": "Human-Core + AI Gap Fill",
    "ai_first_eligible": "AI-First Eligible Tasks",
    "human_first_ai_assist": "Human-First + AI Assist",
    "recommended_balanced_team": "Recommended Balanced Team",
    "fastest_valid_team": "Fastest Valid Team",
    "lowest_cost_valid_team": "Lowest-Cost Valid Team",
    "lowest_risk_valid_team": "Lowest-Risk Valid Team",
}

# Which options are AI-assignment strategies (carry conjured-agent detail).
_STRATEGY_OPTION = {
    "human_core_ai_gap_fill": staffing_strategies.HUMAN_CORE,
    "ai_first_eligible": staffing_strategies.AI_FIRST,
    "human_first_ai_assist": staffing_strategies.HUMAN_FIRST,
}


class ProjectModeError(ValueError):
    """Raised for user-fixable problems (unknown names, empty team)."""


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def tasks_from_request(task_dicts: List[dict]) -> List[Task]:
    """Build engine ``Task`` objects from request JSON (not from CSV)."""
    tasks: List[Task] = []
    for t in task_dicts:
        tasks.append(
            Task(
                task=str(t["task"]).strip(),
                required_skill=str(t["required_skill"]).strip(),
                effort_hours=float(t["effort_hours"]),
                priority=int(t.get("priority", 1)),
                dependencies=list(t.get("dependencies", []) or []),
                is_required=bool(t.get("is_required", True)),
            )
        )
    return tasks


def apply_constraints(config: SimConfig, constraints: Optional[dict]) -> SimConfig:
    """Return a copy of ``config`` with team-size constraints overridden."""
    if not constraints:
        return config
    fields = {}
    for key in (
        "min_humans_per_team",
        "max_humans_per_team",
        "min_ai_agents_per_team",
        "max_ai_agents_per_team",
    ):
        if constraints.get(key) is not None:
            fields[key] = int(constraints[key])
    return replace(config, **fields) if fields else config


def _is_valid(result: SimulationResult) -> bool:
    """A team is valid for project decisions if it covers all required skills.

    This is independent of the ``require_full_required_skill_coverage`` config
    flag so the Fastest/Cheapest/Balanced picks are always fully staffed.
    """
    return not result.missing_required_skills


# ---------------------------------------------------------------------------
# AI-assisted current team (deterministic greedy)
# ---------------------------------------------------------------------------

def build_ai_assisted_team(
    human_team: List[Worker],
    available_ai: List[Worker],
    tasks: List[Task],
    require_full: bool,
    max_ai: int,
    calibration: dict = None,
) -> Tuple[List[Worker], List[str]]:
    """Greedily add AI agents that improve the human team's outcome.

    Deterministic: at each step it evaluates every remaining agent and keeps
    the one whose addition most improves the team, where "better" is the
    lexicographic tuple (required coverage up, then shorter duration, then
    lower cost, then lower risk). It stops at ``max_ai`` agents or when no
    agent improves the outcome. Returns the chosen agents and a note per
    agent explaining why it was added.

    ``calibration`` (optional) is threaded into the per-candidate simulations so
    the greedy choice is consistent with the calibrated metrics shown elsewhere.
    """
    chosen: List[Worker] = []
    notes: List[str] = []
    if max_ai <= 0 or not available_ai:
        return chosen, notes

    remaining = list(available_ai)

    def metrics(team_ai: List[Worker]) -> SimulationResult:
        return simulate_team(
            Team(list(human_team), team_ai), tasks, require_full, calibration
        )

    def quality(r: SimulationResult) -> Tuple[float, float, float, float]:
        # Higher is better: coverage up, duration down, cost down, risk down.
        return (
            r.required_skill_coverage_score,
            -r.estimated_duration,
            -r.estimated_cost,
            -r.risk_score,
        )

    base = metrics(chosen)
    while len(chosen) < max_ai and remaining:
        base_q = quality(base)
        best_agent = None
        best_res = None
        best_q = base_q
        # Evaluate candidates in a stable (name) order for determinism.
        for agent in sorted(remaining, key=lambda w: w.name):
            res = metrics(chosen + [agent])
            q = quality(res)
            if q > best_q:
                best_q = q
                best_agent = agent
                best_res = res
        if best_agent is None:
            break  # nothing improves the outcome
        notes.append(_assist_note(best_agent, base, best_res))
        chosen.append(best_agent)
        remaining.remove(best_agent)
        base = best_res
    return chosen, notes


def _assist_note(agent: Worker, before: SimulationResult, after: SimulationResult) -> str:
    """Explain why an AI agent was added, citing the dimension it improved."""
    if after.required_skill_coverage_score > before.required_skill_coverage_score:
        gained = sorted(set(before.missing_required_skills) - set(after.missing_required_skills))
        skills = ", ".join(gained) if gained else "required work"
        return f"{agent.name}: covers previously missing {skills}."
    if after.estimated_duration < before.estimated_duration:
        return (
            f"{agent.name}: shortens duration from "
            f"{before.estimated_duration:.0f}h to {after.estimated_duration:.0f}h."
        )
    if after.estimated_cost < before.estimated_cost:
        return (
            f"{agent.name}: lowers cost from ${before.estimated_cost:.0f} "
            f"to ${after.estimated_cost:.0f}."
        )
    if after.risk_score < before.risk_score:
        return (
            f"{agent.name}: reduces risk from {before.risk_score:.0f} "
            f"to {after.risk_score:.0f}."
        )
    return f"{agent.name}: improves the overall outcome."


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------

def _objective_key(objective: str):
    """Return a ``(key_fn, phrase)`` used to pick the best option for an objective.

    ``key_fn(result, burden)`` maps a scored option (and its review/rework burden)
    to a sort value; the option with the *max* key wins (so "lower is better"
    metrics are negated). ``burden`` lets AI-aware objectives (e.g. Most
    Innovative) use the net AI benefit without touching the scorer.
    """
    table = {
        "balanced": (lambda r, b: r.total_score, "highest overall score"),
        "fastest": (lambda r, b: -r.estimated_duration, "shortest duration"),
        "lowest_cost": (lambda r, b: -r.estimated_cost, "lowest cost"),
        "best_skill_coverage": (
            lambda r, b: (r.required_skill_coverage_score, r.optional_skill_coverage_score),
            "best skill coverage",
        ),
        "best_workload_balance": (
            lambda r, b: r.workload_balance_score,
            "best workload balance",
        ),
        "lowest_risk": (lambda r, b: -r.risk_score, "lowest risk"),
        # Most Innovative = the boldest lean into AI: the valid plan that puts the
        # most work on AI (most AI-owned tasks), tie-broken toward the plan where
        # that AI pays off best. The recommendation's AI-time verdict still states
        # honestly whether the AI saves time or shifts it to reviewers.
        "most_innovative": (
            lambda r, b: (len(r.team.ai_agents), b["net_time_saved"]),
            "the boldest use of AI",
        ),
    }
    return table.get(objective, table["balanced"])


# Final, fully-deterministic preference order used only to break otherwise
# exact ties. Lower number = preferred.
_TIE_PRIORITY = {
    "human_core_ai_gap_fill": 0,
    "ai_first_eligible": 1,
    "current_team": 2,
    "recommended_balanced_team": 3,
    "human_first_ai_assist": 4,
    "fastest_valid_team": 5,
    "lowest_cost_valid_team": 6,
    "lowest_risk_valid_team": 7,
}


def _net_burden(burden: dict) -> float:
    """Hidden work a plan adds: review + rework minus AI time saved (lower=better)."""
    return (
        burden["review_burden_hours"]
        + burden["expected_rework_hours"]
        - burden["ai_time_saved"]
    )


def choose_recommendation(
    options: Dict[str, SimulationResult], objective: str, burdens: Dict[str, dict]
) -> str:
    """Pick the recommended option key for the given objective.

    Only valid (fully-staffed) options are eligible. Ties are broken in the
    approved order: objective metric, then higher confidence, then lower net
    review+rework burden, then lower risk, then lower cost, then the simplest
    (fewest-member) team, then a fixed static order. If no option is valid, the
    one with the highest required coverage is returned as the least-bad choice.
    """
    key_fn, _ = _objective_key(objective)
    valid_keys = [k for k, r in options.items() if _is_valid(r)]
    if not valid_keys:
        return max(
            options,
            key=lambda k: (
                options[k].required_skill_coverage_score,
                options[k].total_score,
                -_TIE_PRIORITY[k],
            ),
        )

    def sort_key(k: str):
        r = options[k]
        return (
            key_fn(r, burdens[k]),           # 1. chosen objective (higher better)
            r.confidence_score,              # 2. most likely to deliver
            -_net_burden(burdens[k]),        # 3. least hidden review+rework
            -r.risk_score,                   # 4. lower risk
            -r.estimated_cost,               # 5. lower cost
            -len(r.team.members),            # 6. simplest team
            -_TIE_PRIORITY[k],               # 7. fixed deterministic order
        )

    return max(valid_keys, key=sort_key)


def _bottleneck(result: SimulationResult) -> Tuple[Optional[str], float, List[str]]:
    """Return (busiest member, their hours, their critical-path task names)."""
    if not result.member_hours:
        return None, 0.0, []
    name, hours = max(result.member_hours.items(), key=lambda kv: (kv[1], kv[0]))
    crit_tasks = [
        a.task
        for a in result.assignments
        if a.assigned_to == name and a.is_on_critical_path
    ]
    return name, hours, crit_tasks


def _next_action(
    rec: SimulationResult,
    rec_key: str,
    options: Dict[str, SimulationResult],
    deadline_target_hours: Optional[float],
    budget_target: Optional[float],
    objective: str,
) -> str:
    """Deterministic 'what to change next' suggestion."""
    busiest, hours, crit_tasks = _bottleneck(rec)

    if rec.missing_required_skills:
        return f"add a {rec.missing_required_skills[0]}-capable person to close the skill gap"
    if deadline_target_hours and rec.estimated_duration > deadline_target_hours:
        if crit_tasks and busiest:
            return (
                f"extend the deadline or move {crit_tasks[0]} away from {busiest} "
                f"to shorten the {rec.estimated_duration:.0f}h critical path"
            )
        return f"extend the deadline (currently {rec.estimated_duration:.0f}h needed)"
    if budget_target and rec.estimated_cost > budget_target:
        return "reduce optional scope or increase the budget to fit the cost"
    if rec.overloaded_members and busiest:
        skill = rec.missing_required_skills[0] if rec.missing_required_skills else (
            crit_tasks[0] if crit_tasks else "key work"
        )
        return (
            f"add another person to share {busiest}'s load "
            f"(move {skill} off the critical path)"
        )
    # If sticking with the current team but a gap-fill plan is strictly better,
    # nudge toward it.
    if rec_key == "current_team":
        gap_fill = options.get("human_core_ai_gap_fill")
        if gap_fill is not None and _is_valid(gap_fill) and (
            gap_fill.estimated_duration < rec.estimated_duration
            or gap_fill.total_score > rec.total_score
        ):
            return "use the Human-Core + AI Gap Fill plan to add AI where it helps"
    if objective != "lowest_cost" and budget_target and rec.estimated_cost > budget_target * 0.9:
        return "change objective to lowest cost if budget matters more"
    return "reduce optional scope or proceed as planned"


def _ai_time_verdict(burden: dict) -> str:
    """Deterministic note on whether AI saves time or shifts it to reviewers."""
    saved = burden["ai_time_saved"]
    review = burden["review_burden_hours"]
    rework = burden["expected_rework_hours"]
    net = burden["net_time_saved"]
    if saved <= 0:
        return (
            "This option uses no AI agents, so there is no AI time saving or "
            "review burden to weigh."
        )
    if net > 0:
        return (
            f"AI genuinely saves time here: ~{saved:.0f}h saved against "
            f"{review:.0f}h review + {rework:.0f}h rework, a net ~{net:.0f}h gain."
        )
    return (
        f"AI mostly shifts work to reviewers here: ~{saved:.0f}h saved but "
        f"{review:.0f}h review + {rework:.0f}h rework, a net ~{net:.0f}h "
        "(consider routing fewer tasks to AI or adding reviewer capacity)."
    )


def build_recommendation(
    rec_key: str,
    options: Dict[str, SimulationResult],
    objective: str,
    ai_added: List[Worker],
    ai_notes: List[str],
    deadline_target_hours: Optional[float],
    budget_target: Optional[float],
    burden: dict,
) -> dict:
    """Assemble the deterministic recommendation summary."""
    rec = options[rec_key]
    label = OPTION_LABELS[rec_key]
    _, why_phrase = _objective_key(objective)
    busiest, hours, crit_tasks = _bottleneck(rec)

    # Biggest risk.
    if rec.missing_required_skills:
        biggest_risk = "missing required skills: " + ", ".join(rec.missing_required_skills)
    elif rec.overloaded_members:
        biggest_risk = "overloaded members: " + ", ".join(rec.overloaded_members)
    elif rec.missing_optional_skills:
        biggest_risk = "uncovered optional work: " + ", ".join(rec.missing_optional_skills)
    else:
        biggest_risk = f"low (risk score {rec.risk_score})"

    bottleneck_text = "none"
    if busiest:
        if crit_tasks:
            bottleneck_text = f"{busiest} on {', '.join(crit_tasks)} ({hours:.0f}h)"
        else:
            bottleneck_text = f"{busiest} ({hours:.0f}h of work)"

    ai_contribution = (
        "; ".join(ai_notes)
        if ai_notes
        else "no AI agents improved the outcome for this team"
    )

    next_action = _next_action(
        rec, rec_key, options, deadline_target_hours, budget_target, objective
    )

    # Cost/duration tradeoff phrasing vs targets.
    tradeoff_bits = [
        f"costs ${rec.estimated_cost:.0f}",
        f"finishes in {rec.estimated_duration:.0f}h",
    ]
    if budget_target:
        tradeoff_bits.append(
            "within budget" if rec.estimated_cost <= budget_target else "over budget"
        )
    if deadline_target_hours:
        tradeoff_bits.append(
            "meets the deadline"
            if rec.estimated_duration <= deadline_target_hours
            else "misses the deadline"
        )

    ai_time_verdict = _ai_time_verdict(burden)
    reviewer_note = burden["reviewer_bottleneck"]["message"]

    summary_text = (
        f"Recommended: {label}. It wins on {why_phrase}, covering "
        f"{rec.required_skill_coverage_score:.0f}% of required skills "
        f"({rec.optional_skill_coverage_score:.0f}% optional), {', '.join(tradeoff_bits)}. "
        f"AI contribution: {ai_contribution}. "
        f"{ai_time_verdict} "
        f"Main bottleneck: {bottleneck_text}. "
        f"Biggest risk: {biggest_risk}. "
        f"Next: {next_action}."
    )

    return {
        "recommended_option": rec_key,
        "recommended_label": label,
        "why": f"It has the {why_phrase} among the valid options for this objective.",
        "main_bottleneck": bottleneck_text,
        "critical_path": rec.critical_path,
        "biggest_risk": biggest_risk,
        "ai_contribution": ai_contribution,
        "ai_time_verdict": ai_time_verdict,
        "reviewer_bottleneck_note": reviewer_note,
        "what_to_change_next": next_action,
        "summary_text": summary_text,
    }


# ---------------------------------------------------------------------------
# Output packaging
# ---------------------------------------------------------------------------

def _burden(result: SimulationResult, records: List[dict]) -> dict:
    """Reviewer burden + bottleneck for an option's team, from the routing."""
    return routing.reviewer_burden_for_team(
        records, result.team.humans, len(result.team.ai_agents) > 0
    )


def _option_dict(
    key: str,
    result: SimulationResult,
    burden: dict,
    ai_added: Optional[List[Worker]] = None,
    ai_notes: Optional[List[str]] = None,
) -> dict:
    """Wrap a result with its option label (+ AI-assist detail where relevant)."""
    result.plain_english_explanation = optimizer.explain(result)
    data = exporter.result_to_dict(result)
    data["option"] = key
    data["option_label"] = OPTION_LABELS[key]
    data["review_burden_hours"] = burden["review_burden_hours"]
    data["expected_rework_hours"] = burden["expected_rework_hours"]
    data["ai_time_saved"] = burden["ai_time_saved"]
    data["net_time_saved"] = burden["net_time_saved"]
    data["reviewer_bottleneck"] = burden["reviewer_bottleneck"]
    if ai_added is not None:
        data["ai_agents_added"] = [w.name for w in ai_added]
        data["ai_assist_notes"] = ai_notes or []
    return data


def _comparison_row(key: str, result: SimulationResult, burden: dict) -> dict:
    return {
        "option": OPTION_LABELS[key],
        "team_members": result.team.human_names,
        "ai_agents": result.team.ai_names,
        "total_score": result.total_score,
        "cost": result.estimated_cost,
        "duration": result.estimated_duration,
        "required_coverage": result.required_skill_coverage_score,
        "optional_coverage": result.optional_skill_coverage_score,
        "workload_balance": result.workload_balance_score,
        "productivity": result.productivity_score,
        "risk": result.risk_score,
        "confidence": result.confidence_score,
        "review_burden_hours": burden["review_burden_hours"],
        "expected_rework_hours": burden["expected_rework_hours"],
        "net_ai_time_saved": burden["net_time_saved"],
        "reviewer_bottleneck": burden["reviewer_bottleneck"]["is_bottleneck"],
        "critical_path": result.critical_path,
    }


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

def run_project_simulation(
    employees: List[Worker],
    ai_agents: List[Worker],
    request: dict,
    config: SimConfig,
    prior_bindings: dict = None,
    calibration: dict = None,
    workbank_bindings: dict = None,
    use_workbank: bool = False,
) -> dict:
    """Run the full Project Mode comparison and return the response payload.

    ``request`` is the validated project scenario (see the API schema). Raises
    ``ProjectModeError`` for user-fixable input problems.

    ``prior_bindings`` (optional) enables prior-backed routing scores when
    ``config.use_public_priors_for_scoring`` is true. When the flag is off (the
    default) the routing is computed exactly as before.

    ``workbank_bindings`` + ``use_workbank`` (optional) enable WORKBank-backed
    routing scores (WORKBank takes precedence over public priors). Off by
    default, leaving routing unchanged.

    ``calibration`` (optional) is a dict of approved multipliers applied to every
    option's simulation and to the task routing's review/rework estimates. When
    ``None`` the comparison is computed exactly as before.
    """
    objective = request.get("optimization_objective", "balanced")
    if objective not in OBJECTIVES:
        raise ProjectModeError(
            f"Unknown optimization_objective '{objective}'. "
            f"Allowed: {sorted(OBJECTIVES)}"
        )

    tasks = tasks_from_request(request["tasks"])
    if not tasks:
        raise ProjectModeError("At least one task is required.")

    cfg = apply_constraints(config, request.get("team_constraints"))
    require_full = cfg.require_full_required_skill_coverage

    humans_by = {w.name: w for w in employees}

    current_human_names = request.get("current_team_human_names", []) or []
    unknown_h = [n for n in current_human_names if n not in humans_by]
    if unknown_h:
        raise ProjectModeError(
            f"Current team contains unknown humans: {unknown_h}."
        )
    if not current_human_names:
        raise ProjectModeError("Select at least one team member.")

    current_humans = [humans_by[n] for n in current_human_names]

    # Task-level routing first - the strategies READ these decisions (they never
    # change the routing rules). Build a task -> {decision, scores} map.
    use_priors = bool(getattr(config, "use_public_priors_for_scoring", False))
    routing_records = routing.route_tasks(
        tasks, bindings=prior_bindings, use_priors=use_priors, calibration=calibration,
        workbank_bindings=workbank_bindings, use_workbank=use_workbank,
    )
    routing_summary = routing.summarize_routing(routing_records)
    routing_by_task = {
        r["task"]: {"decision": r["routing"], "scores": r["scores"]}
        for r in routing_records
    }

    # 1. Current team: exactly the humans selected (AI is dynamic, never a fixed
    #    pick), assigned with no forced human/AI split.
    current_res = simulate_team(
        Team(current_humans, []), tasks, require_full, calibration
    )

    # 2. The three AI-assignment strategies over the selected humans. Each
    #    conjures the agents its plan needs and pins the per-task human/AI split,
    #    then runs through the same scheduler + scorer.
    strategy_results: Dict[str, SimulationResult] = {}
    strategy_agents: Dict[str, List[Worker]] = {}
    strategy_notes: Dict[str, List[str]] = {}
    for opt_key, strat in _STRATEGY_OPTION.items():
        team, allowed, agents, notes = staffing_strategies.build_plan(
            strat, current_humans, tasks, routing_by_task
        )
        strategy_results[opt_key] = simulate_team(
            team, tasks, require_full, calibration, allowed_types=allowed
        )
        strategy_agents[opt_key] = agents
        strategy_notes[opt_key] = notes

    # 3. Optimizer options over the FULL human roster, human-only. AI value is
    #    offered by the strategies above, not by enumerating a fixed catalog, so
    #    these are the best HUMAN teams per objective.
    human_only_cfg = _replace(cfg, min_ai_agents_per_team=0, max_ai_agents_per_team=0)
    all_results = optimizer.simulate_all_teams(
        employees, [], tasks, human_only_cfg, calibration
    )

    # Score everything together so totals/cost-efficiency are comparable.
    combined = all_results + [current_res] + list(strategy_results.values())
    optimizer.finalize_scores(combined, cfg)

    valid = [r for r in all_results if _is_valid(r)]
    if valid:
        balanced = sorted(
            valid,
            key=lambda r: (-r.total_score, r.risk_score, r.estimated_cost, r.team.signature()),
        )[0]
        fastest = sorted(
            valid,
            key=lambda r: (r.estimated_duration, -r.total_score, r.estimated_cost, r.team.signature()),
        )[0]
        cheapest = sorted(
            valid,
            key=lambda r: (r.estimated_cost, -r.total_score, r.estimated_duration, r.team.signature()),
        )[0]
        lowest_risk = sorted(
            valid,
            key=lambda r: (r.risk_score, -r.total_score, r.estimated_cost, r.team.signature()),
        )[0]
    else:
        # No fully-staffed human team possible; fall back to the current team so
        # the response is still well-formed (marked invalid downstream).
        balanced = fastest = cheapest = lowest_risk = current_res

    options: Dict[str, SimulationResult] = {
        "current_team": current_res,
        "human_core_ai_gap_fill": strategy_results["human_core_ai_gap_fill"],
        "ai_first_eligible": strategy_results["ai_first_eligible"],
        "human_first_ai_assist": strategy_results["human_first_ai_assist"],
        "recommended_balanced_team": balanced,
        "fastest_valid_team": fastest,
        "lowest_cost_valid_team": cheapest,
        "lowest_risk_valid_team": lowest_risk,
    }

    # Per-option review/rework burden from the (team-independent) routing.
    burdens = {k: _burden(options[k], routing_records) for k in OPTION_LABELS}

    rec_key = choose_recommendation(options, objective, burdens)
    recommendation = build_recommendation(
        rec_key, options, objective,
        strategy_agents.get(rec_key, []), strategy_notes.get(rec_key, []),
        request.get("deadline_target_hours"), request.get("budget_target"),
        burdens[rec_key],
    )

    option_payload: Dict[str, dict] = {}
    for k in OPTION_LABELS:
        if k in _STRATEGY_OPTION:
            option_payload[k] = _option_dict(
                k, options[k], burdens[k], strategy_agents[k], strategy_notes[k]
            )
        else:
            option_payload[k] = _option_dict(k, options[k], burdens[k])

    # Equivalence: when two options yield the same team AND the same key metrics
    # (e.g. an all-human current team vs the Human-First plan), label the later
    # one as equivalent to the first rather than presenting it as distinct.
    _seen: Dict[tuple, str] = {}
    equivalent_to: Dict[str, Optional[str]] = {}
    for k in OPTION_LABELS:
        r = options[k]
        sig = (r.team.signature(), r.total_score, r.estimated_cost, r.estimated_duration)
        equivalent_to[k] = _seen.get(sig)  # label of the first match, or None
        _seen.setdefault(sig, OPTION_LABELS[k])
    for k in OPTION_LABELS:
        option_payload[k]["equivalent_to"] = equivalent_to[k]

    comparison_table = [
        {**_comparison_row(k, options[k], burdens[k]), "equivalent_to": equivalent_to[k]}
        for k in OPTION_LABELS
    ]

    # Read-only Pareto-front preview over the same options/burdens. Computed
    # last and added as two extra keys; it does not affect the recommendation,
    # options, scoring, or routing above.
    ordered_options = {k: options[k] for k in OPTION_LABELS}
    pareto_preview = pareto.pareto_preview(
        ordered_options, burdens, OPTION_LABELS, rec_key
    )

    return {
        "project_name": request.get("project_name", ""),
        "project_goal": request.get("project_goal", ""),
        "optimization_objective": objective,
        "recommendation": recommendation,
        "options": option_payload,
        "comparison_table": comparison_table,
        "task_routing": routing_records,
        "routing_summary": routing_summary,
        "pareto_front": pareto_preview["pareto_front"],
        "pareto_explanation": pareto_preview["pareto_explanation"],
    }
