"""Assessment definitions for ManagerFit.

The heart of the matching engine is a set of *shared work-style dimensions*.
Both managers and candidates rate themselves on the same 1-5 scale, but the
prompt is framed differently for each side:

* A manager describes **how they operate** ("I give feedback in the moment").
* A candidate describes **what they prefer** ("I like feedback in the moment").

Because both answer on the same axis, we can directly compare a manager's
operating style to a candidate's preference and surface alignment vs. friction.

We deliberately do NOT model these as "good" or "bad". A 1 is not worse than a
5 — they are simply different working styles, and fit is about *match*, not rank.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


# --------------------------------------------------------------------------- #
# Work-style dimensions (the comparable axis)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Dimension:
    """A single comparable work-style axis.

    ``low_label`` / ``high_label`` anchor the two ends of the 1-5 scale.
    ``manager_prompt`` and ``candidate_prompt`` frame the same axis for each side.
    ``discuss_questions`` are surfaced as suggested interview questions when a
    manager and candidate diverge on this dimension.
    """

    key: str
    name: str
    low_label: str
    high_label: str
    manager_prompt: str
    candidate_prompt: str
    discuss_questions: Dict[str, List[str]] = field(default_factory=dict)

    def label_for(self, value: int) -> str:
        """Return a human-readable label for a 1-5 score on this dimension."""
        if value <= 2:
            return self.low_label
        if value >= 4:
            return self.high_label
        return f"Balanced ({self.low_label} / {self.high_label})"


DIMENSIONS: List[Dimension] = [
    Dimension(
        key="communication",
        name="Communication style",
        low_label="Diplomatic & measured",
        high_label="Direct & candid",
        manager_prompt="How direct is your day-to-day communication with your team?",
        candidate_prompt="How direct do you want your manager's communication to be?",
        discuss_questions={
            "candidate": [
                "How is difficult feedback usually delivered on your team?",
                "When something isn't working, how direct will you be with me?",
            ],
            "manager": [
                "How do you like to receive candid feedback?",
                "What communication style helps you do your best work?",
            ],
        },
    ),
    Dimension(
        key="feedback",
        name="Feedback cadence",
        low_label="Feedback as needed",
        high_label="Frequent, ongoing feedback",
        manager_prompt="How often do you give your team feedback?",
        candidate_prompt="How often do you want feedback from your manager?",
        discuss_questions={
            "candidate": [
                "How and how often is feedback delivered on this team?",
                "What does your feedback rhythm look like in a typical month?",
            ],
            "manager": [
                "How much ongoing feedback helps you stay on track?",
                "Would you prefer scheduled check-ins or in-the-moment notes?",
            ],
        },
    ),
    Dimension(
        key="coaching",
        name="Coaching vs. directing",
        low_label="Directing (clear instruction)",
        high_label="Coaching (questions & growth)",
        manager_prompt="Do you tend to direct the work or coach people to find the answer?",
        candidate_prompt="Do you prefer clear direction or a coach who helps you find the answer?",
        discuss_questions={
            "candidate": [
                "When I'm stuck, will you point me to the answer or coach me to it?",
                "How do you balance giving direction with developing people?",
            ],
            "manager": [
                "Do you want me to give you the answer or help you work it out?",
                "How much guidance do you want when tackling something new?",
            ],
        },
    ),
    Dimension(
        key="pace",
        name="Pace of work",
        low_label="Deliberate & considered",
        high_label="Fast & high-tempo",
        manager_prompt="What pace does your team typically operate at?",
        candidate_prompt="What pace of work do you do your best work at?",
        discuss_questions={
            "candidate": [
                "How often do priorities change week to week?",
                "What does a typical sprint or cycle feel like in terms of tempo?",
            ],
            "manager": [
                "What pace lets you produce your best work?",
                "How do you handle fast context-switching?",
            ],
        },
    ),
    Dimension(
        key="decision_making",
        name="Decision-making approach",
        low_label="Consensus-driven",
        high_label="Decisive & top-down",
        manager_prompt="How are decisions usually made on your team?",
        candidate_prompt="How do you want decisions to be made on your team?",
        discuss_questions={
            "candidate": [
                "How are decisions made and how much input will I have?",
                "When we disagree on a call, how do you want to resolve it?",
            ],
            "manager": [
                "How much do you want to be involved in team decisions?",
                "How do you react when a decision is made without full consensus?",
            ],
        },
    ),
    Dimension(
        key="autonomy",
        name="Autonomy level",
        low_label="Hands-on guidance",
        high_label="High autonomy",
        manager_prompt="How much autonomy do you give your team?",
        candidate_prompt="How much autonomy do you want in your work?",
        discuss_questions={
            "candidate": [
                "How much independence will I have in the first 90 days?",
                "How do you stay informed without being hands-on?",
            ],
            "manager": [
                "How much check-in cadence helps you feel supported?",
                "What does the right level of autonomy look like for you?",
            ],
        },
    ),
    Dimension(
        key="structure",
        name="Structure vs. ambiguity",
        low_label="Prefers structure",
        high_label="Thrives in ambiguity",
        manager_prompt="Does your environment lean toward structure or ambiguity?",
        candidate_prompt="Do you do your best work with structure or in ambiguity?",
        discuss_questions={
            "candidate": [
                "How defined are roles, goals, and processes on the team?",
                "How do you support people who prefer more structure?",
            ],
            "manager": [
                "How do you create structure for yourself when things are ambiguous?",
                "What kind of structure helps you do your best work?",
            ],
        },
    ),
    Dimension(
        key="conflict",
        name="Conflict style",
        low_label="Smooth & harmonize",
        high_label="Address head-on",
        manager_prompt="When conflict arises, do you smooth it over or address it head-on?",
        candidate_prompt="When conflict arises, how do you want it handled?",
        discuss_questions={
            "candidate": [
                "How does the team handle disagreement and tension?",
                "When we don't see eye to eye, how will you raise it with me?",
            ],
            "manager": [
                "How do you prefer to work through disagreement?",
                "What helps you feel safe raising a concern?",
            ],
        },
    ),
]

DIMENSIONS_BY_KEY: Dict[str, Dimension] = {d.key: d for d in DIMENSIONS}


# --------------------------------------------------------------------------- #
# Lightweight profile inputs (enrich the profile, not the match score)
# --------------------------------------------------------------------------- #

BIG_FIVE = [
    ("openness", "Openness", "Curiosity, imagination, openness to new ideas"),
    ("conscientiousness", "Conscientiousness", "Organization, dependability, follow-through"),
    ("extraversion", "Extraversion", "Energy from people, assertiveness, enthusiasm"),
    ("agreeableness", "Agreeableness", "Warmth, cooperation, consideration of others"),
    ("neuroticism", "Emotional sensitivity", "Sensitivity to stress and emotional reactivity"),
]

# A representative slice of the CliftonStrengths 34 themes for the demo selector.
CLIFTON_STRENGTHS = [
    "Achiever", "Activator", "Analytical", "Arranger", "Belief", "Command",
    "Communication", "Competition", "Connectedness", "Consistency", "Context",
    "Deliberative", "Developer", "Discipline", "Empathy", "Focus", "Futuristic",
    "Harmony", "Ideation", "Includer", "Individualization", "Input", "Intellection",
    "Learner", "Maximizer", "Positivity", "Relator", "Responsibility", "Restorative",
    "Self-Assurance", "Significance", "Strategic", "Woo",
]


def default_scores() -> Dict[str, int]:
    """Return a neutral (3 = balanced) score for every work-style dimension."""
    return {d.key: 3 for d in DIMENSIONS}


def default_big_five() -> Dict[str, int]:
    """Return a neutral (3) score for each Big Five trait."""
    return {key: 3 for key, _, _ in BIG_FIVE}
