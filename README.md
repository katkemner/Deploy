# ManagerFit

> A talent attraction layer where the **manager becomes part of the job product** — helping
> candidates evaluate their future manager and the candidate-manager fit *before* they apply.

Most hiring platforms surface the company, the role, comp, and benefits. But the manager is
the single greatest determinant of employee experience, engagement, and retention. ManagerFit
makes the manager visible up front so candidates self-select into teams where they'll thrive.

This repo is a runnable **MVP** of the concept described in the ManagerFit PRD.

## What it does

1. **Managers** complete a work-style assessment (communication, feedback, coaching vs.
   directing, pace, decision-making, autonomy, structure vs. ambiguity, conflict) plus a Big
   Five snapshot and CliftonStrengths picks → a shareable **manager profile**.
2. **Candidates** describe the manager style they do their best work under → a **candidate
   profile**.
3. The **fit engine** compares the two and produces a fit analysis:
   - ✅ **Strong alignment**
   - 💬 **Areas to discuss**
   - **Suggested interview questions** for both the candidate and the manager.

Following the PRD's guiding principle, the engine **never scores a manager as "good" or
"bad"** — it only identifies likely alignment and potential friction, framed as a
conversation starter.

## Architecture

```
managerfit/
  assessments.py   # shared work-style dimensions + Big Five / CliftonStrengths definitions
  matching.py      # the fit engine (pure, fully unit-tested logic)
  storage.py       # tiny atomic JSON-file store, keyed by shareable token
  app.py           # Flask routes + form handling
  templates/       # Jinja2 templates (landing, assessments, profiles, fit report)
  static/style.css
tests/             # pytest suite for the engine and the web flow
seed.py            # populate demo profiles (Sarah the manager × Alex the candidate)
```

The matching math is deliberately simple and explainable: each side rates the same 1-5 axis,
the engine compares the gap per dimension (small gap = alignment, large gap = discuss), and
the overall score is the average closeness across dimensions.

## Run it

```bash
pip install -r requirements.txt
python seed.py          # optional: adds two demo profiles
python -m managerfit.app
# open http://127.0.0.1:5000
```

## Test it

```bash
pip install -r requirements.txt
pytest -q
```

## Mapping to the PRD

| PRD element | Where it lives |
|---|---|
| Manager profile (work style, Big Five, CliftonStrengths, philosophy) | `assess/manager` → `manager_profile.html` |
| Candidate profile (preferred manager style) | `assess/candidate` → `candidate_profile.html` |
| AI matching engine (alignment / friction, no good-vs-bad scoring) | `matching.py` |
| Suggested interview questions | `matching.py` → `fit.html` |
| Shareable profile link | `storage.py` token + `/manager/<token>`, `/candidate/<token>` |

## Roadmap (post-MVP)

- Swap the rule-based engine for an LLM-generated narrative fit summary over the same signals.
- Real assessment integrations (validated Big Five / CliftonStrengths instruments).
- ATS / job-board integrations (Greenhouse, Lever, Workday, LinkedIn, Indeed).
- Auth, persistence beyond the JSON demo store, and success-metric instrumentation
  (apply conversion, offer acceptance, retention).
