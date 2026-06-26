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

---

## Option A — Deploy with the Blueprint (recommended)

1. Push this repository to GitHub (already done if you're reading this on
   GitHub).
2. In the Render dashboard: **New → Blueprint**, and select this repository.
   Render reads `render.yaml` and proposes the two services.
3. Click **Apply**. Render creates `workforce-simulator-api` and
   `workforce-simulator-web`.
4. Set the two environment variables that are intentionally left blank (see
   [Environment variables](#environment-variables) below), then trigger a
   redeploy of each service so the values take effect.

That's it — Render builds and starts both services.

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

| Service | Variable | Example | Purpose |
|---|---|---|---|
| Backend | `CORS_ALLOW_ORIGINS` | `https://workforce-simulator-web.onrender.com` | Comma-separated list of browser origins allowed to call the API. Unset → `*` (local-dev default). |
| Backend | `PYTHON_VERSION` | `3.11.9` | Python version Render builds with. |
| Frontend | `VITE_API_BASE_URL` | `https://workforce-simulator-api.onrender.com` | Backend base URL, baked into the build. |

**Order of operations (because each service needs the other's URL):**

1. Deploy both services once (with the variables blank). Render assigns each a
   URL like `https://<name>.onrender.com`.
2. Set `VITE_API_BASE_URL` on the frontend to the backend's URL, and
   `CORS_ALLOW_ORIGINS` on the backend to the frontend's URL.
3. Redeploy both services so the new values take effect (the frontend value is
   compiled in at build time, so a rebuild is required).

For multiple allowed origins, comma-separate them:
`CORS_ALLOW_ORIGINS=https://app.example.com,https://staging.example.com`.

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
  LLM calls, and external API integrations. See the staging warning at the top.
