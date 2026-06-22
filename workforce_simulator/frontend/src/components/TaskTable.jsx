import React from 'react';

export default function TaskTable({ tasks }) {
  if (!tasks || tasks.length === 0) {
    return <p className="muted">No tasks loaded.</p>;
  }
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th>Task</th>
            <th>Required skill</th>
            <th>Effort</th>
            <th>Priority</th>
            <th>Dependencies</th>
            <th>Required?</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t) => (
            <tr key={t.task}>
              <td>{t.task}</td>
              <td>{t.required_skill}</td>
              <td>{t.effort_hours}h</td>
              <td>{t.priority}</td>
              <td style={{ whiteSpace: 'normal' }}>
                {t.dependencies.length ? t.dependencies.join(', ') : '—'}
              </td>
              <td>
                {t.is_required ? (
                  <span className="badge badge-valid">required</span>
                ) : (
                  <span className="badge badge-critical">optional</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
