import React from 'react';

export default function EmployeeTable({ employees }) {
  if (!employees || employees.length === 0) {
    return <p className="muted">No employees loaded.</p>;
  }
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Role</th>
            <th>Skills</th>
            <th>Capacity</th>
            <th>Workload</th>
            <th>Available</th>
            <th>Rate</th>
            <th>Quality</th>
          </tr>
        </thead>
        <tbody>
          {employees.map((e) => (
            <tr key={e.name}>
              <td>{e.name}</td>
              <td>{e.role}</td>
              <td style={{ whiteSpace: 'normal' }}>
                {e.skills.map((s) => (
                  <span key={s} className="tag">
                    {s}
                  </span>
                ))}
              </td>
              <td>{e.capacity_hours}</td>
              <td>{e.workload_hours}</td>
              <td>{e.available_hours}</td>
              <td>${e.cost_rate}</td>
              <td>{e.quality_score}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
