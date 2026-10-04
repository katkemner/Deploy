// Thin client wrapping every backend endpoint.
//
// All functions return parsed JSON on success and throw an Error with a
// user-friendly `.message` on failure. The backend (FastAPI) returns errors
// as { detail: ... } where `detail` may be a string, an object (e.g. unknown
// team names), or a validation array (422). `extractError` flattens all of
// those into one readable message.

// Normalize a configured API base: a bare hostname (e.g. what Render's
// `fromService` injects) is treated as https://; a full URL is used as-is.
// Empty/undefined passes through so the fallback chain below applies.
function normalizeBase(value) {
  if (!value) return value;
  return /^https?:\/\//i.test(value) ? value : `https://${value}`;
}

// API base URL. In deployment set VITE_API_BASE_URL to the backend's URL (or
// bare hostname) at build time. VITE_API_BASE is still accepted for backward
// compatibility, and both fall back to the local dev backend so `npm run dev`
// works unchanged.
export const API_BASE =
  normalizeBase(import.meta.env.VITE_API_BASE_URL) ||
  import.meta.env.VITE_API_BASE ||
  'http://127.0.0.1:8000';

function extractError(status, body) {
  const detail = body && body.detail !== undefined ? body.detail : body;

  if (typeof detail === 'string') return detail;

  // 422 validation errors: array of { loc, msg }.
  if (Array.isArray(detail)) {
    return detail
      .map((e) => {
        const loc = Array.isArray(e.loc) ? e.loc.filter((p) => p !== 'body').join('.') : '';
        return loc ? `${loc}: ${e.msg}` : e.msg;
      })
      .join('; ');
  }

  // Object detail (e.g. unknown member names).
  if (detail && typeof detail === 'object') {
    if (detail.message) {
      const parts = [detail.message];
      if (detail.unknown_humans && detail.unknown_humans.length) {
        parts.push(`Unknown humans: ${detail.unknown_humans.join(', ')}`);
      }
      if (detail.unknown_ai_agents && detail.unknown_ai_agents.length) {
        parts.push(`Unknown AI agents: ${detail.unknown_ai_agents.join(', ')}`);
      }
      return parts.join(' ');
    }
    return JSON.stringify(detail);
  }

  return `Request failed with status ${status}`;
}

// ---------------------------------------------------------------------------
// Sleeping-backend handling. The free hosting plan puts the API to sleep after
// ~15 idle minutes; the first request then fails or gets a hosting-level 502/
// 503/504 while it wakes (30-60s). We retry those - and ONLY those - for up to
// WAKE_LIMIT_MS, telling listeners so the UI can show a "waking up" banner.
// Real errors from our app (JSON bodies with `detail`, e.g. a 502 when the AI
// service fails) are never retried, so an AI call is never repeated/billed twice.
// ---------------------------------------------------------------------------
const WAKE_LIMIT_MS = 90000;
const WAKE_DELAYS_MS = [2000, 3000, 5000, 5000, 8000, 10000, 10000, 10000, 15000];
const isLocal = /127\.0\.0\.1|localhost/.test(API_BASE || '');

const wakeListeners = new Set();
let wakingCount = 0;

function setWaking(delta) {
  const before = wakingCount > 0;
  wakingCount = Math.max(0, wakingCount + delta);
  const after = wakingCount > 0;
  if (before !== after) wakeListeners.forEach((fn) => fn(after));
}

// Subscribe to "server is waking up" changes; returns an unsubscribe function.
export function onWakeChange(listener) {
  wakeListeners.add(listener);
  return () => wakeListeners.delete(listener);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function unreachableMessage(detail) {
  if (isLocal) {
    return (
      `Cannot reach the backend at ${API_BASE}. Is it running ` +
      `(uvicorn src.api.app:app --reload)? [${detail}]`
    );
  }
  return (
    "Couldn't reach the server, even after waiting about a minute for it to " +
    'wake up. Please try again in a moment.'
  );
}

async function request(path, options = {}) {
  const started = Date.now();
  let attempt = 0;
  let waking = false;
  try {
    for (;;) {
      let res = null;
      let networkErr = null;
      try {
        res = await fetch(`${API_BASE}${path}`, options);
      } catch (err) {
        networkErr = err;
      }

      let body = null;
      if (res) {
        const text = await res.text();
        if (text) {
          try {
            body = JSON.parse(text);
          } catch {
            body = text;
          }
        }
      }

      // Hosting-level "not available" (non-JSON 502/503/504) or no connection
      // at all = the server is asleep or restarting. Our own API errors always
      // come back as JSON and fall through to normal handling below.
      const hostUnavailable =
        res && [502, 503, 504].includes(res.status) &&
        !(body && typeof body === 'object');
      if ((networkErr || hostUnavailable) && !isLocal) {
        const delay = WAKE_DELAYS_MS[Math.min(attempt, WAKE_DELAYS_MS.length - 1)];
        if (Date.now() - started + delay <= WAKE_LIMIT_MS) {
          if (!waking) {
            waking = true;
            setWaking(+1);
          }
          attempt += 1;
          await sleep(delay);
          continue;
        }
        throw new Error(unreachableMessage(networkErr ? networkErr.message : `status ${res.status}`));
      }
      if (networkErr) {
        throw new Error(unreachableMessage(networkErr.message));
      }
      if (!res.ok) {
        throw new Error(extractError(res.status, body));
      }
      return body;
    }
  } finally {
    if (waking) setWaking(-1);
  }
}

function jsonPost(path, payload) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

function uploadFile(path, file) {
  const form = new FormData();
  form.append('file', file);
  return request(path, { method: 'POST', body: form });
}

// Only the endpoints the simplified UI uses. The backend still exposes the
// full API (config, manual team, calibration, priors, routing preview, …) for
// direct/API use — the UI just no longer surfaces those panels.
export const api = {
  getHealth: () => request('/health'),
  getEmployees: () => request('/employees'),
  getTasks: () => request('/tasks'),
  runProjectSimulation: (scenario) => jsonPost('/simulate/project', scenario),
  runUncertainty: (payload) => jsonPost('/simulate/uncertainty', payload),
  // Employee Digital Twin Seed: upload a seed file (.csv/.xlsx) as the active
  // in-memory roster, or explicitly choose the demo roster.
  uploadEmployeeSeed: (file) => uploadFile('/employees/seed-upload', file),
  useDemoRoster: () => request('/employees/use-demo', { method: 'POST' }),
  getActiveRoster: () => request('/employees/active'),
  // Brief upload: deterministic text extraction, then (after the user
  // confirms) AI drafting of editable tasks. Two separate calls by design.
  extractBriefText: (file) => uploadFile('/projects/extract-brief-text', file),
  parseBrief: (text) => jsonPost('/projects/parse-brief', { text }),
  // Pre-run strength check: which (person, skill) pairs the tasks need, plus
  // opt-in AI suggestions from roster notes. Answers are sent with the run
  // only; the server never stores them.
  proficiencyCheck: (tasks) =>
    jsonPost('/proficiency/check', {
      tasks: tasks.map((t) => ({ task: t.task, required_skill: t.required_skill })),
    }),
  proficiencySuggest: (pairs) => jsonPost('/proficiency/suggest', { pairs }),
  // Pre-run skill check: suggest a roster skill for each task skill nobody
  // has (by meaning with AI when configured, else by shared words).
  mapSkills: (skills) => jsonPost('/skills/map', { skills }),
};
