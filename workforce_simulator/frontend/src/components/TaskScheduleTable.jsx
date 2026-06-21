import React from 'react';

// Renders a team's computed schedule. Critical-path rows are highlighted.
const fmt = (v) => (v === null || v === undefined ? '—' : v);

export default function TaskScheduleTable({ schedule }) {
  if (!schedule || schedule.length === 0) {
    return <p className="muted">No schedule available.</p>;
  }
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th>Task</th>
            <th>Assigned to</th>
            <th>Skill</th>
            <th>Effort</th>
            <th>Adj. effort</th>
            <th>Start</th>
            <th>Finish</th>
            <th>Dependencies</th>
            <th>Critical?</th>
          </tr>
        </thead>
        <tbody>
          {schedule.map((s) => (
            <tr
              key={s.task}
              className={s.is_on_critical_path ? 'critical-row' : undefined}
            >
              <td>{s.task}</td>
              <td>{fmt(s.assigned_to)}</td>
              <td>{s.required_skill}</td>
              <td>{s.effort_hours}h</td>
              <td>{s.adjusted_effort_hours}h</td>
              <td>{fmt(s.start_time)}</td>
              <td>{fmt(s.finish_time)}</td>
              <td style={{ whiteSpace: 'normal' }}>
                {s.dependencies.length ? s.dependencies.join(', ') : '—'}
              </td>
              <td>
                {s.is_on_critical_path ? (
                  <span className="badge badge-critical">critical</span>
                ) : (
                  ''
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
