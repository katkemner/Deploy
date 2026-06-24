import React from 'react';

// Read-only "Tradeoff View": shows which staffing options are non-dominated
// (Pareto-optimal) across the ten objectives. It never changes the
// recommendation - if the recommended option is dominated, it only warns.

// Objective keys -> short labels, in display order.
const OBJ_LABELS = [
  ['duration', 'Duration'],
  ['cost', 'Cost'],
  ['human_hours', 'Human hrs'],
  ['review_hours', 'Review hrs'],
  ['rework_hours', 'Rework hrs'],
  ['risk', 'Risk'],
  ['skill_coverage', 'Coverage'],
  ['productivity', 'Productivity'],
  ['workload_balance', 'Balance'],
  ['confidence', 'Confidence'],
];

export default function TradeoffView({ paretoFront, paretoExplanation, recommendedKey }) {
  if (!paretoFront || paretoFront.length === 0) return null;

  const byId = Object.fromEntries(paretoFront.map((p) => [p.option_id, p]));
  const recommended = recommendedKey ? byId[recommendedKey] : null;
  const recDominated = recommended && !recommended.is_pareto_optimal;
  const optimal = paretoFront.filter((p) => p.is_pareto_optimal);

  return (
    <div style={{ marginTop: 18 }}>
      <h3 style={{ fontSize: 16 }}>Tradeoff View (Pareto front)</h3>
      <p className="section-hint">
        Which options are non-dominated across all objectives — you cannot
        improve one objective without giving up another. This view is
        informational and does not change the recommendation.
      </p>

      {recDominated && (
        <div className="msg msg-error">
          ⚠ The recommended option (<strong>{recommended.option_name}</strong>) is
          NOT Pareto-optimal — it is dominated by{' '}
          {recommended.dominated_by.map((id) => byId[id]?.option_name || id).join(', ')}.
          The recommendation is unchanged, but a dominating option improves some
          metrics at no cost to others.
        </div>
      )}

      {/* Current recommended option callout. */}
      {recommended && (
        <div className="explanation" style={{ borderLeftColor: 'var(--primary)' }}>
          <strong>Recommended:</strong> {recommended.option_name}{' '}
          {recommended.is_pareto_optimal ? (
            <span className="badge badge-valid">on the frontier</span>
          ) : (
            <span className="badge badge-invalid">dominated</span>
          )}
          <div style={{ marginTop: 4 }}>{recommended.tradeoff_summary}</div>
        </div>
      )}

      {/* Pareto-optimal options and the tradeoff each represents. */}
      <h4 style={{ fontSize: 14, margin: '12px 0 6px' }}>
        Pareto-optimal options ({optimal.length})
      </h4>
      <div className="result-grid">
        {optimal.map((p) => (
          <div
            key={p.option_id}
            className={`result-card ${p.option_id === recommendedKey ? 'selected' : ''}`}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong>{p.option_name}</strong>
              <span className="badge badge-valid">Pareto-optimal</span>
            </div>
            <div className="explanation" style={{ borderLeftColor: 'var(--green)' }}>
              {p.tradeoff_summary}
            </div>
            {p.strengths.length > 0 && (
              <div className="tag-group" style={{ margin: '6px 0' }}>
                {p.strengths.map((s) => (
                  <span key={s} className="tag tag-ai">best: {s}</span>
                ))}
              </div>
            )}
            {p.weaknesses.length > 0 && (
              <div className="tag-group" style={{ margin: '6px 0' }}>
                {p.weaknesses.map((w) => (
                  <span key={w} className="tag">weak: {w}</span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Objective matrix for every option (read-only). */}
      <div className="table-scroll" style={{ marginTop: 12 }}>
        <table className="table">
          <thead>
            <tr>
              <th>Option</th>
              <th>Frontier?</th>
              {OBJ_LABELS.map(([, label]) => (
                <th key={label}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paretoFront.map((p) => (
              <tr key={p.option_id}>
                <td>
                  {p.option_name}
                  {p.option_id === recommendedKey && (
                    <span className="badge badge-critical" style={{ marginLeft: 6 }}>
                      recommended
                    </span>
                  )}
                </td>
                <td>
                  {p.is_pareto_optimal ? (
                    <span className="badge badge-valid">yes</span>
                  ) : (
                    <span className="muted">dominated</span>
                  )}
                </td>
                {OBJ_LABELS.map(([key]) => (
                  <td key={key}>{p.objective_values[key]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="section-hint" style={{ marginTop: 8 }}>{paretoExplanation}</p>
    </div>
  );
}
