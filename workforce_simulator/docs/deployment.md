# Staging deployment (Render)

This guide deploys the Workforce Simulator MVP to a **staging** environment on
[Render](https://render.com): the FastAPI backend as a **Web Service** and the
Vite/React frontend as a **Static Site**.

> ⚠️ **This is a staging demo. Do not enter sensitive company data.**
> Authentication, access control, a persistent database, production security
> hardening, and tenant isolation are **not built yet**. Anything entered here
> is for demonstration only and is not protected or isolated.

---

## Architecture

| Service | Render type | Root dir | Serves |
|---|---|---|---|
| `workforce-simulator-api` | Web Service (Python) | `workforce_simulator` | FastAPI app via uvicorn |
| `workforce-simulator-web` | Static Site | `workforce_simulator/frontend` | Built Vite `dist/` |

The frontend is a static bundle that calls the backend over HTTPS. The backend
URL is baked into the frontend at **build time** via `VITE_API_BASE_URL`, and
the backend restricts browser origins via `CORS_ALLOW_ORIGINS`.

A [`render.yaml`](../../render.yaml) Blueprint at the repository root declares
both services. You can deploy via the Blueprint (recommended) or create each
service manually.

The frontend is **preconfigured** with the backend's public URL: `render.yaml`
sets the frontend's `VITE_API_BASE_URL` to
`https://workforce-simulator-api.onrender.com` (the default backend service
name), so there is **nothing to copy/paste**. If you rename the backend service
or add a custom domain, update that value in `render.yaml` (or in the dashboard)
and redeploy the frontend.

---

## Option A — One-click Blueprint (recommended)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/katkemner/Deploy)

1. Click the **Deploy to Render** button above (or, in the Render dashboard:
   **New → Blueprint**, then select this repository).
2. Sign in / sign up for Render and authorize access to the repository if asked.
3. Render reads `render.yaml` and shows the two services. Click **Apply**.
4. Wait ~5 minutes for both to build and go live. Done — the frontend already
   knows the backend's URL, and CORS defaults to permissive for staging, so
   there's nothing else to set.

When it finishes, open the **workforce-simulator-web** URL Render shows you.

> Lock-down (optional, later): to restrict the API to only the frontend, add a
> `CORS_ALLOW_ORIGINS` variable on the backend set to the frontend's URL, then
> redeploy. Not needed for a staging demo.

---

## Option B — Create the services manually

### Backend — Render Web Service

- **New → Web Service**, connect this repo.
- **Root Directory:** `workforce_simulator`
- **Runtime:** Python
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn src.api.app:app --host 0.0.0.0 --port $PORT`
- **Health Check Path:** `/health`
- **Environment variables:**
  - `PYTHON_VERSION` = `3.11.9`
  - `CORS_ALLOW_ORIGINS` = the frontend URL (see below)

### Frontend — Render Static Site

- **New → Static Site**, connect this repo.
- **Root Directory:** `workforce_simulator/frontend`
- **Build Command:** `npm ci && npm run build`
- **Publish Directory:** `dist`
- **Environment variable:**
  - `VITE_API_BASE_URL` = the backend URL (see below)
- **Redirect/Rewrite rule:** rewrite `/*` → `/index.html` (single-page app).

---

## Environment variables

| Service | Variable | Set by | Purpose |
|---|---|---|---|
| Frontend | `VITE_API_BASE_URL` | Blueprint (preset value) | Backend's public URL, baked into the build. Preset in `render.yaml` to `https://workforce-simulator-api.onrender.com`. Update only if you rename the backend or add a custom domain. A bare hostname is treated as `https://`. |
| Backend | `PYTHON_VERSION` | Blueprint (`3.11.9`) | Python version Render builds with. |
| Backend | `CORS_ALLOW_ORIGINS` | **Optional**, you (later) | Comma-separated browser origins allowed to call the API. Unset → `*` (works for staging). Set to the frontend URL to lock down; a bare hostname is accepted. |
| Backend | `ANTHROPIC_API_KEY` | **Optional secret**, you (dashboard) | Enables AI task drafting from an uploaded brief. Declared `sync: false` in `render.yaml` so Render prompts for it and stores it as a secret. Unset → the brief-upload feature returns `503` and the rest of the app works normally. See [Enabling AI task drafting](#enabling-ai-task-drafting-optional). |

With the Blueprint, **no environment variables need to be entered by hand** for a
staging deploy — the frontend↔backend wiring is automatic and CORS defaults to
permissive. The optional steps are restricting CORS later (above) and enabling
AI task drafting (below).

If you create the services manually (Option B) instead of using the Blueprint,
set `VITE_API_BASE_URL` on the frontend to the backend's URL yourself, then
redeploy the frontend (the value is compiled in at build time).

For multiple allowed CORS origins, comma-separate them:
`CORS_ALLOW_ORIGINS=https://app.example.com,https://staging.example.com`.

### Enabling AI task drafting (optional)

Project Mode can draft editable tasks from an uploaded project brief (a Word
`.docx` or a text-based PDF). The brief's text is extracted on the backend and,
**only after you confirm**, sent to Anthropic's API, which proposes a draft task
list. The AI never picks the team, scores options, or runs the simulation — it
only fills in the editable task list, which you review and change before running
anything. The deterministic engine is untouched.

To turn it on:

1. Create an API key at the [Anthropic Console](https://console.anthropic.com/).
2. In Render: **backend service → Environment → Add Environment Variable** →
   key `ANTHROPIC_API_KEY`, value your key. (The Blueprint already declares it
   as `sync: false`, so it may appear there awaiting a value.)
3. Save; Render redeploys the backend. The **Start from a project brief** panel
   in Project Mode now works.

If the key is **not** set, the panel's “Generate draft tasks” step returns a
clear `503` message and everything else keeps working — manual task entry is
always available.

> ⚠️ **Privacy:** with a key set, the extracted brief text is sent to Anthropic.
> This is a staging demo — **do not upload sensitive company data.** v1 supports
> `.docx` and text-based PDFs only (no OCR for scanned PDFs), and uploaded files
> are **not persisted** — only the extracted text is processed in memory.

---

## Health check

The backend already exposes a liveness endpoint used by Render:

```
GET /health  ->  200  {"status": "ok"}
```

`render.yaml` sets `healthCheckPath: /health` for the backend, so Render marks
the service healthy only once this returns `200`. You can verify manually:

```bash
curl https://workforce-simulator-api.onrender.com/health
# {"status":"ok"}
```

Interactive API docs are at `/docs` (Swagger UI) on the backend service.

---

## Verifying the deploy

1. Open the frontend URL. The **Project Mode** dashboard loads.
2. The header health indicator should show **OK** (it calls `GET /health`).
3. Click **Fill current best team → Run Project Simulation**. Results, routing,
   uncertainty, and the tradeoff view should render — confirming the frontend
   reached the backend and CORS is configured correctly.

If requests fail with a CORS error in the browser console, double-check that
`CORS_ALLOW_ORIGINS` on the backend exactly matches the frontend origin
(scheme + host, no trailing slash), and that `VITE_API_BASE_URL` points at the
backend.

---

## Notes & limitations

- **Free plan cold starts:** on Render's free tier the backend may sleep when
  idle and take ~30–60s to wake on the first request. That's expected for
  staging.
- **No persistence:** data lives in the repo's CSV/JSON files inside the
  container. Uploaded CSVs, calibration actuals, and imported WORKBank data are
  **ephemeral** — they reset when the service restarts or redeploys. This is a
  staging demo, not a system of record.
- **Not built yet (by design):** auth, access control, a database, payments,
  and external API integrations. See the staging warning at the top.
- **AI task drafting (optional):** the only LLM call in the app is the
  opt-in brief-upload drafting step, off unless `ANTHROPIC_API_KEY` is set. It
  drafts editable tasks only — it never scores, routes, or runs the
  deterministic engine. See [Enabling AI task drafting](#enabling-ai-task-drafting-optional).
