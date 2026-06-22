import React from 'react';

// Task-level human/AI routing table with the nine suitability scores,
// the routing decision, review/rework estimates, and an explanation.

const DECISION_STYLE = {
  AI_ONLY: { background: '#ecfeff', color: '#0e7490' },
  AI_FIRST_HUMAN_REVIEW: { background: '#eff6ff', color: '#1d4ed8' },
  HUMAN_FIRST_AI_ASSIST: { background: '#eef2ff', color: '#4338ca' },
  HUMAN_ONLY: { background: '#fef3e2', color: '#b45309' },
  ESCALATE: { background: '#fdecec', color: '#dc2626' },
};

const SCORE_COLS = [
  ['ai_capability_fit', 'AI fit'],
  ['human_judgment_need', 'Judgment'],
  ['verification_ease', 'Verify'],
  ['error_cost', 'Err cost'],
  ['context_sensitivity', 'Context'],
  ['repetition_level', 'Repeat'],
  ['speed_value', 'Speed'],
  ['human_learning_value', 'Learning'],
  ['collaboration_value', 'Collab'],
];

function DecisionBadge({ decision }) {
  const style = DECISION_STYLE[decision] || {};
  return (
    <span className="badge" style={style}>
      {decision.replace(/_/g, ' ')}
    </span>
  );
}

export default function RoutingTable({ routing, summary }) {
  if (!routing || routing.length === 0) return null;
  return (
    <div>
      {summary && (
        <div
          className="msg"
          style={{
            background: summary.ai_saves_time ? 'var(--green-bg)' : 'var(--amber-bg)',
            color: summary.ai_saves_time ? 'var(--green)' : 'var(--amber)',
            border: '1px solid var(--border)',
          }}
        >
          <strong>
            {summary.ai_saves_time
              ? 'AI saves net time on this project.'
              : 'AI mostly shifts work to reviewers on this project.'}
          </strong>
          <br />
          AI time saved: {summary.total_ai_time_saved}h · Review burden:{' '}
          {summary.total_review_hours}h · Expected rework:{' '}
          {summary.total_expected_rework_hours}h ·{' '}
          <strong>Net: {summary.net_ai_time_saved}h</strong>
        </div>
      )}
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Task</th>
              <th>Routing</th>
              {SCORE_COLS.map(([, label]) => (
                <th key={label} title={label}>
                  {label}
                </th>
              ))}
              <th>Review h</th>
              <th>Rework h</th>
              <th>AI saved h</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            {routing.map((r) => (
              <tr key={r.task}>
                <td>{r.task}</td>
                <td>
                  <DecisionBadge decision={r.routing} />
                </td>
                {SCORE_COLS.map(([key]) => (
                  <td key={key} style={{ textAlign: 'center' }}>
                    {r.scores[key] === null || r.scores[key] === undefined
                      ? '—'
                      : r.scores[key]}
                  </td>
                ))}
                <td>{r.review_hours}</td>
                <td>{r.expected_rework_hours}</td>
                <td>{r.ai_time_saved}</td>
                <td style={{ whiteSpace: 'normal', minWidth: 240 }}>
                  {r.explanation}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
