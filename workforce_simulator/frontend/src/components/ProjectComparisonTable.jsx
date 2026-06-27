import React from 'react';

// Side-by-side comparison of the five Project Mode staffing options.
export default function ProjectComparisonTable({ rows }) {
  if (!rows || rows.length === 0) return null;
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th>Option</th>
            <th>Team members</th>
            <th>AI agents</th>
            <th>Total</th>
            <th>Cost</th>
            <th>Duration</th>
            <th>Req. cov.</th>
            <th>Opt. cov.</th>
            <th>Balance</th>
            <th>Productivity</th>
            <th>Risk</th>
            <th>Confidence</th>
            <th>Innovation</th>
            <th>Review h</th>
            <th>Rework h</th>
            <th>Net AI h</th>
            <th>Reviewer bottleneck</th>
            <th>Critical path</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.option}>
              <td style={{ fontWeight: 600 }}>{r.option}</td>
              <td style={{ whiteSpace: 'normal' }}>
                {r.team_members.length ? r.team_members.join(', ') : '—'}
              </td>
              <td style={{ whiteSpace: 'normal' }}>
                {r.ai_agents.length ? r.ai_agents.join(', ') : '—'}
              </td>
              <td>{r.total_score}</td>
              <td>${r.cost}</td>
              <td>{r.duration}h</td>
              <td>{r.required_coverage}%</td>
              <td>{r.optional_coverage}%</td>
              <td>{r.workload_balance}</td>
              <td>{r.productivity}</td>
              <td>{r.risk}</td>
              <td>{r.confidence}</td>
              <td>{r.innovation_score}</td>
              <td>{r.review_burden_hours}</td>
              <td>{r.expected_rework_hours}</td>
              <td>{r.net_ai_time_saved}</td>
              <td>
                {r.reviewer_bottleneck ? (
                  <span className="badge badge-invalid">yes</span>
                ) : (
                  <span className="muted">no</span>
                )}
              </td>
              <td style={{ whiteSpace: 'normal' }}>
                {r.critical_path && r.critical_path.length
                  ? r.critical_path.join(' → ')
                  : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
