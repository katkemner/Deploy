import React, { useMemo } from 'react';

// Lets the manager pick the team they would normally use, and shows a quick
// client-side preview of required-skill coverage before running the
// simulation. (The authoritative numbers come from the backend.)
function toggle(set, name) {
  const next = new Set(set);
  next.has(name) ? next.delete(name) : next.add(name);
  return next;
}

export default function CurrentTeamSelector({
  employees,
  aiAgents,
  tasks,
  selectedHumans,
  selectedAis,
  onHumansChange,
  onAisChange,
}) {
  const preview = useMemo(() => {
    const skills = new Set();
    employees
      .filter((e) => selectedHumans.has(e.name))
      .forEach((e) => e.skills.forEach((s) => skills.add(s.toLowerCase())));
    aiAgents
      .filter((a) => selectedAis.has(a.name))
      .forEach((a) => a.capabilities.forEach((s) => skills.add(s.toLowerCase())));

    const required = tasks.filter((t) => t.is_required);
    const requiredSkills = [...new Set(required.map((t) => t.required_skill))];
    const missing = requiredSkills.filter((s) => !skills.has(s.toLowerCase()));
    const covered = requiredSkills.length - missing.length;
    const pct = requiredSkills.length
      ? Math.round((covered / requiredSkills.length) * 100)
      : 100;
    return { pct, missing, total: requiredSkills.length, covered };
  }, [employees, aiAgents, tasks, selectedHumans, selectedAis]);

  return (
    <div>
      <h3>Current team</h3>
      <p className="section-hint">
        Select the team you would normally use for this project.
      </p>

      <div className="grid-2">
        <div>
          <strong>Humans</strong>
          <div className="checkbox-list" style={{ gridTemplateColumns: '1fr' }}>
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
        </div>
        <div>
          <strong>AI agents</strong>
          <div className="checkbox-list" style={{ gridTemplateColumns: '1fr' }}>
            {aiAgents.map((a) => (
              <label className="checkbox-row" key={a.name}>
                <input
                  type="checkbox"
                  checked={selectedAis.has(a.name)}
                  onChange={() => onAisChange(toggle(selectedAis, a.name))}
                />
                {a.name} <span className="muted">· {a.agent_type}</span>
              </label>
            ))}
          </div>
        </div>
      </div>

      <div
        className="msg"
        style={{
          background: preview.missing.length ? 'var(--amber-bg)' : 'var(--green-bg)',
          color: preview.missing.length ? 'var(--amber)' : 'var(--green)',
          border: '1px solid var(--border)',
        }}
      >
        <strong>
          Selected: {selectedHumans.size} humans · {selectedAis.size} AI agents
        </strong>
        <br />
        Required skill coverage preview: <strong>{preview.pct}%</strong>{' '}
        ({preview.covered}/{preview.total} required skills)
        {preview.missing.length > 0 && (
          <>
            {' '}— missing: <strong>{preview.missing.join(', ')}</strong>
          </>
        )}
      </div>
    </div>
  );
}
