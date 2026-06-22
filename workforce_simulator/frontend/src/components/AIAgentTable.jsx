import React from 'react';

export default function AIAgentTable({ agents }) {
  if (!agents || agents.length === 0) {
    return <p className="muted">No AI agents loaded.</p>;
  }
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Capabilities</th>
            <th>Capacity</th>
            <th>Rate</th>
            <th>Quality</th>
            <th>Speed×</th>
          </tr>
        </thead>
        <tbody>
          {agents.map((a) => (
            <tr key={a.name}>
              <td>{a.name}</td>
              <td>{a.agent_type}</td>
              <td style={{ whiteSpace: 'normal' }}>
                <div className="tag-group">
                  {a.capabilities.map((s) => (
                    <span key={s} className="tag tag-ai">
                      {s}
                    </span>
                  ))}
                </div>
              </td>
              <td>{a.capacity_hours}</td>
              <td>${a.cost_rate}</td>
              <td>{a.quality_score}</td>
              <td>{a.speed_multiplier}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
