"""Risk-tiered human checkpoint plan for a staffing recommendation (no LLM).

Turns the routing records + the recommended option into a concrete oversight
plan, following the evidence that oversight works when it is *episodic and
risk-tiered* rather than constant (OP-9, Electronic Markets 2026) and that AI
autonomy should be dialed to error cost and reversibility (104-study PRISMA
review, Frontiers in Robotics and AI 2026):

* **No-delegate zone** - tasks routed HUMAN_ONLY, named with their reasons.
* **Checkpoints** - one entry per AI-involved task, tiered by risk:
  - ``sampling_audit``  : low-risk, repetitive AI_ONLY volume work - spot-check
    a sample instead of reviewing everything.
  - ``final_review``    : standard full review before hand-off.
  - ``midstream_and_final`` : high-risk (high error cost, hard to undo, or on
    the critical path) - check direction mid-way, then full review.
  - ``release_gate``    : hard human sign-off before anything irreversible
    ships (added for irreversible tasks whatever their routing).
* **Undecided** - ESCALATE tasks a human still needs to make the call on.
* **Rubber-stamping warning** - review load concentrated enough that review
  quality realistically collapses (humans are poor sustained monitors).

Pure functions over existing data; scoring, routing, and schedules unchanged.
"""

from __future__ import annotations

from typing import Dict, List, Optional

AI_INVOLVED = {"AI_ONLY", "AI_FIRST_HUMAN_REVIEW", "HUMAN_FIRST_AI_ASSIST"}

# Review load above this share of the team's human capacity invites
# rubber-stamping (softer than the hard reviewer-bottleneck check at 35%).
RUBBER_STAMP_SHARE = 0.20


def _risk_signals(rec: dict, critical_tasks: set) -> List[str]:
    """Why an AI-involved task counts as high-risk (empty = not high-risk)."""
    signals = []
    scores = rec.get("scores") or {}
    if (scores.get("error_cost") or 0) >= 3:
        signals.append("meaningful error cost")
    if rec.get("irreversible"):
        signals.append("hard to undo")
    if rec.get("task") in critical_tasks:
        signals.append("on the critical path")
    return signals


def _checkpoint_for(rec: dict, critical_tasks: set) -> dict:
    scores = rec.get("scores") or {}
    signals = _risk_signals(rec, critical_tasks)
    if signals:
        kind = "midstream_and_final"
        label = "Mid-stream check + full review"
        why = "High-risk AI work (" + ", ".join(signals) + "): check direction mid-way, then review fully before hand-off."
    elif rec.get("routing") == "AI_ONLY" and (scores.get("repetition_level") or 0) >= 4:
        kind = "sampling_audit"
        label = "Sampling audit"
        why = "Low-risk repetitive AI output: spot-check a sample (~1 in 5) instead of reviewing every piece."
    else:
        kind = "final_review"
        label = "Full review before hand-off"
        why = "Standard human review of the AI output before it is used downstream."
    return {
        "task": rec.get("task"),
        "routing": rec.get("routing"),
        "checkpoint": kind,
        "checkpoint_label": label,
        "why": why,
        "check_against": rec.get("acceptance_criteria"),
        "review_hours": rec.get("review_hours", 0.0),
    }


def build_checkpoint_plan(
    routing_records: List[dict],
    burden: Optional[dict] = None,
    critical_tasks=None,
) -> Dict:
    """Build the risk-tiered checkpoint plan from routing records + burden.

    ``burden`` is the recommended option's reviewer-burden dict (used only for
    the rubber-stamping warning); ``critical_tasks`` the recommended option's
    critical-path task names. Records alone still produce a useful plan.
    """
    critical_tasks = set(critical_tasks or [])

    no_delegate = []
    undecided = []
    checkpoints = []
    release_gates = []

    for rec in routing_records:
        routing = rec.get("routing")
        if routing == "HUMAN_ONLY":
            no_delegate.append({
                "task": rec.get("task"),
                "why": rec.get("explanation", ""),
            })
        elif routing == "ESCALATE":
            undecided.append({
                "task": rec.get("task"),
                "why": rec.get("explanation", ""),
            })
        elif routing in AI_INVOLVED:
            checkpoints.append(_checkpoint_for(rec, critical_tasks))
        if rec.get("irreversible"):
            release_gates.append({
                "task": rec.get("task"),
                "why": (
                    "Hard to undo once shipped - a named human signs off "
                    "before release, whatever did the work."
                ),
            })

    # Rubber-stamping warning: enough concentrated review load that humans
    # realistically stop reviewing and start approving.
    warning = None
    if burden:
        review = float(burden.get("review_burden_hours") or 0.0)
        capacity = float(
            (burden.get("reviewer_bottleneck") or {}).get("human_capacity_hours")
            or 0.0
        )
        if capacity > 0 and review / capacity >= RUBBER_STAMP_SHARE:
            pct = round(review / capacity * 100)
            warning = (
                f"Review load is {review:g}h - {pct}% of the team's human "
                "capacity. Sustained review at this level invites "
                "rubber-stamping: batch the reviews, rotate reviewers, and "
                "lean on the acceptance criteria instead of full re-reads."
            )

    summary = (
        f"{len(no_delegate)} task(s) stay human-only, "
        f"{len(checkpoints)} AI-involved task(s) get checkpoints "
        f"({sum(1 for c in checkpoints if c['checkpoint'] == 'midstream_and_final')} high-risk, "
        f"{sum(1 for c in checkpoints if c['checkpoint'] == 'sampling_audit')} sampling audits), "
        f"{len(release_gates)} release gate(s), "
        f"{len(undecided)} still need a human call."
    )

    return {
        "summary": summary,
        "no_delegate": no_delegate,
        "checkpoints": checkpoints,
        "release_gates": release_gates,
        "undecided": undecided,
        "rubber_stamping_warning": warning,
    }
