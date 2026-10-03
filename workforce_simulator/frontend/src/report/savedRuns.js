// Saved runs, kept ONLY in this browser (localStorage) - never on the server,
// which stores nothing about employees. Survives server restarts/deploys.
//
// Before saving, person-level strength detail (who was rated how) is removed:
// the strength answers are a one-time input, so no per-employee rating is
// ever kept - only the task-level advice. Bulky provenance is trimmed too.

const KEY = 'wfs.savedRuns.v1';
const MAX_RUNS = 10;

function readAll() {
  try {
    const raw = window.localStorage.getItem(KEY);
    const runs = raw ? JSON.parse(raw) : [];
    return Array.isArray(runs) ? runs : [];
  } catch {
    return [];
  }
}

function writeAll(runs) {
  // Drop the oldest runs until it fits (browser storage is limited).
  let list = runs.slice(0, MAX_RUNS);
  while (list.length) {
    try {
      window.localStorage.setItem(KEY, JSON.stringify(list));
      return true;
    } catch {
      list = list.slice(0, -1);
    }
  }
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // Storage unavailable (private mode etc.) - nothing to do.
  }
  return false;
}

// Copy of a result safe to keep: no person-level strength details, no
// per-score provenance (large, and only needed while exploring "Why?").
export function sanitizeResult(result) {
  const r = JSON.parse(JSON.stringify(result || {}));
  const advice = r.checkpoint_plan && r.checkpoint_plan.capability_advice;
  if (advice && Array.isArray(advice.items)) {
    advice.items = advice.items.map(({ details, ...rest }) => rest);
  }
  if (Array.isArray(r.task_routing)) {
    r.task_routing = r.task_routing.map(
      ({ score_provenance, route_provenance, ...rest }) => rest
    );
  }
  return r;
}

export function listRuns() {
  return readAll();
}

export function saveRun({ name, settings, roster, tasks, result, mc }) {
  const run = {
    id: `run-${Date.now()}`,
    name: name || settings.projectName || 'Untitled run',
    savedAt: new Date().toISOString(),
    settings,
    roster,
    tasks,
    result: sanitizeResult(result),
    mc: mc || null,
  };
  const ok = writeAll([run, ...readAll()]);
  return ok ? run : null;
}

export function deleteRun(id) {
  writeAll(readAll().filter((r) => r.id !== id));
}
