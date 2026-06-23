// Thin client wrapping every backend endpoint.
//
// All functions return parsed JSON on success and throw an Error with a
// user-friendly `.message` on failure. The backend (FastAPI) returns errors
// as { detail: ... } where `detail` may be a string, an object (e.g. unknown
// team names), or a validation array (422). `extractError` flattens all of
// those into one readable message.

export const API_BASE =
  import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000';

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

export const api = {
  getHealth: () => request('/health'),
  getConfig: () => request('/config'),
  saveConfig: (config) => jsonPost('/config', config),
  getEmployees: () => request('/employees'),
  getAIAgents: () => request('/ai-agents'),
  getTasks: () => request('/tasks'),
  getPriors: () => request('/priors'),
  runSimulation: () => request('/simulate', { method: 'POST' }),
  runManualTeam: (humanNames, aiAgentNames) =>
    jsonPost('/simulate/manual-team', {
      human_names: humanNames,
      ai_agent_names: aiAgentNames,
    }),
  runProjectSimulation: (scenario) => jsonPost('/simulate/project', scenario),
  routeTasks: (tasks) => jsonPost('/route/tasks', { tasks }),
  runUncertainty: (payload) => jsonPost('/simulate/uncertainty', payload),
  uploadEmployees: (file) => uploadFile('/upload/employees', file),
  uploadAIAgents: (file) => uploadFile('/upload/ai-agents', file),
  uploadTasks: (file) => uploadFile('/upload/tasks', file),
  getLatestOutputs: () => request('/outputs/latest'),
};
