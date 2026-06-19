"""Seed the ManagerFit store with a couple of demo profiles.

Run once to populate the directory so the app has something to show:

    python seed.py
"""

from managerfit.app import DATA_PATH
from managerfit.storage import Store


def main() -> None:
    store = Store(DATA_PATH)

    sarah = store.save_manager({
        "name": "Sarah Johnson",
        "role": "Senior Product Manager",
        "company": "Company XYZ",
        "philosophy": "I hire curious people, give them room to run, and stay close on outcomes.",
        "scores": {
            "communication": 5, "feedback": 4, "coaching": 4, "pace": 5,
            "decision_making": 4, "autonomy": 5, "structure": 5, "conflict": 5,
        },
        "big_five": {"openness": 5, "conscientiousness": 4, "extraversion": 4,
                     "agreeableness": 3, "neuroticism": 2},
        "strengths": ["Strategic", "Activator", "Command", "Futuristic", "Maximizer"],
    })

    alex = store.save_candidate({
        "name": "Alex Rivera",
        "headline": "Senior Product Manager · fintech",
        "scores": {
            "communication": 4, "feedback": 5, "coaching": 4, "pace": 3,
            "decision_making": 2, "autonomy": 4, "structure": 2, "conflict": 3,
        },
        "big_five": {"openness": 4, "conscientiousness": 5, "extraversion": 3,
                     "agreeableness": 4, "neuroticism": 3},
        "strengths": ["Achiever", "Analytical", "Learner", "Harmony", "Responsibility"],
    })

    print("Seeded manager:", f"/manager/{sarah}")
    print("Seeded candidate:", f"/candidate/{alex}")
    print("Fit:", f"/fit/{sarah}/{alex}")


if __name__ == "__main__":
    main()
