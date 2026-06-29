import React, { useMemo } from 'react';

// Lets the manager pick the people for this project from the active roster
// (uploaded seed or demo), and shows a quick client-side preview of required-
// skill coverage before running the simulation. AI agents are NOT picked here —
// the simulation recommends them. (Authoritative numbers come from the backend.)
function toggle(set, name) {
  const next = new Set(set);
  next.has(name) ? next.delete(name) : next.add(name);
  return next;
}

export default function CurrentTeamSelector({
  employees,
  tasks,
  selectedHumans,
  onHumansChange,
}) {
  const preview = useMemo(() => {
    const skills = new Set();
    employees
      .filter((e) => selectedHumans.has(e.name))
      .forEach((e) => e.skills.forEach((s) => skills.add(s.toLowerCase())));

    const required = tasks.filter((t) => t.is_required);
    const requiredSkills = [...new Set(required.map((t) => t.required_skill))];
    const missing = requiredSkills.filter((s) => !skills.has(s.toLowerCase()));
    const covered = requiredSkills.length - missing.length;
    const pct = requiredSkills.length
      ? Math.round((covered / requiredSkills.length) * 100)
      : 100;
    return { pct, missing, total: requiredSkills.length, covered };
  }, [employees, tasks, selectedHumans]);

  return (
    <div>
      <h3>Your team</h3>
      <p className="section-hint">
        Pick the people for this project from your active roster. The simulation
        recommends where AI agents help — you don’t add them.
      </p>

      <div className="checkbox-list" style={{ gridTemplateColumns: '1fr 1fr' }}>
        {employees.map((e) => (
          <label className="checkbox-row" key={e.name}>
            <input
              type="checkbox"
              checked={selectedHumans.has(e.name)}
              onChange={() => onHumansChange(toggle(selectedHumans, e.name))}
            />
            {e.name} <span className="muted">· {e.role}</span>
          </label>
        ))}
      </div>

      <div
        className="msg"
        style={{
          background: preview.missing.length ? 'var(--amber-bg)' : 'var(--green-bg)',
          color: preview.missing.length ? 'var(--amber)' : 'var(--green)',
          border: '1px solid var(--border)',
        }}
      >
        <strong>Selected: {selectedHumans.size} people</strong>
        <br />
        Required skill coverage from people alone: <strong>{preview.pct}%</strong>{' '}
        ({preview.covered}/{preview.total} required skills)
        {preview.missing.length > 0 && (
          <>
            {' '}— gaps AI may fill: <strong>{preview.missing.join(', ')}</strong>
          </>
        )}
      </div>
    </div>
  );
}
