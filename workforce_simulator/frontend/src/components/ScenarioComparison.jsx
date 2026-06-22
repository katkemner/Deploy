import React from 'react';

// Side-by-side comparison of two or more selected teams.
const teamLabel = (r) => {
  const all = [...r.team_members, ...r.ai_agents];
  return `#${r.rank}: ${all.join(', ')}`;
};

const ROWS = [
  ['Total score', (r) => r.total_score],
  ['Estimated cost', (r) => `$${r.estimated_cost}`],
  ['Estimated duration', (r) => `${r.estimated_duration}h`],
  ['Required coverage', (r) => `${r.required_skill_coverage_score}%`],
  ['Workload balance', (r) => r.workload_balance_score],
  ['Productivity', (r) => r.productivity_score],
  ['Risk', (r) => r.risk_score],
  ['Confidence', (r) => r.confidence_score],
];

export default function ScenarioComparison({ teams }) {
  if (!teams || teams.length < 2) {
    return (
      <p className="muted">
        Select two or more teams (the “Compare” checkbox on each card) to see a
        side-by-side comparison.
      </p>
    );
  }
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th>Metric</th>
            {teams.map((r) => (
              <th key={r.rank}>{teamLabel(r)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map(([label, get]) => (
            <tr key={label}>
              <td style={{ fontWeight: 600 }}>{label}</td>
              {teams.map((r) => (
                <td key={r.rank}>{get(r)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
