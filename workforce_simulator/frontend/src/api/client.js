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

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, options);
  } catch (networkErr) {
    throw new Error(
      `Cannot reach the backend at ${API_BASE}. Is it running ` +
        `(uvicorn src.api.app:app --reload)? [${networkErr.message}]`
    );
  }

  // Some endpoints (uploads) return JSON; all our endpoints do.
  let body = null;
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!res.ok) {
    throw new Error(extractError(res.status, body));
  }
  return body;
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
};
