import React, { useState } from 'react';

// Risk-tiered human checkpoint plan for the recommended option: what stays
// human-only, where the checkpoints and release gates go, and whether the
// review load invites rubber-stamping. Compact by default; details expand.
const KIND_BADGE = {
  midstream_and_final: ['badge-invalid', 'mid-stream + review'],
  final_review: ['badge-critical', 'review before hand-off'],
  sampling_audit: ['badge-valid', 'spot-check sample'],
};

// Relative-capability advice kinds -> badge style + short label.
const ADVICE_BADGE = {
  person_leads: ['badge-valid', 'person leads'],
  spot_check: ['badge-critical', 'spot-check is enough'],
  keep_review: ['badge-invalid', 'keep full review'],
  keep_for_growth: ['badge-valid', 'keep them on it'],
};

function CapabilityAdvice({ advice }) {
  const [why, setWhy] = useState(false);
  if (!advice || (!advice.items.length && !advice.unknown_tasks)) return null;
  return (
    <div style={{ margin: '8px 0' }}>
      <strong>Team-strength advice</strong>
      {advice.items.length === 0 ? (
        <p className="section-hint" style={{ marginTop: 2 }}>
          No clear person-vs-AI difference on the tasks you answered for.
        </p>
      ) : (
        <ul style={{ margin: '4px 0 0 18px', padding: 0 }}>
          {advice.items.map((a) => {
            const [cls, label] = ADVICE_BADGE[a.kind] || ['badge-critical', a.kind];
            return (
              <li key={a.task} style={{ marginBottom: 4 }}>
                <strong>{a.task}</strong>{' '}
                <span className={`badge ${cls}`}>{label}</span> — {a.advice}
                {why && a.details && (
                  <div className="muted" style={{ fontSize: 12 }}>
                    Why: {a.details.person}’s {a.details.skill} work —{' '}
                    {a.details.person_answer.toLowerCase()} approved without
                    changes ({a.details.person_pass_rate}); AI on this task is
                    estimated at {a.details.ai_pass_rate_estimate}. Basis:{' '}
                    {a.details.basis}.
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <p className="section-hint" style={{ marginTop: 4 }}>
        {advice.note}{' '}
        {advice.items.length > 0 && (
          <button
            type="button"
            onClick={() => setWhy((w) => !w)}
            style={{ border: 'none', background: 'none', padding: 0, color: 'var(--primary)', cursor: 'pointer', font: 'inherit', textDecoration: 'underline' }}
          >
            {why ? 'Hide why' : 'Why?'}
          </button>
        )}
      </p>
    </div>
  );
}

export default function CheckpointPlan({ plan }) {
  const [open, setOpen] = useState(false);
  if (!plan) return null;

  return (
    <div className="card" style={{ borderLeft: '4px solid var(--amber, #d97706)', marginTop: 12 }}>
      <h3 style={{ fontSize: 16, marginTop: 0 }}>Human checkpoint plan</h3>
      <p className="section-hint" style={{ marginTop: 2 }}>
        Oversight placed where it changes the outcome — not constant
        supervision. {plan.summary}
      </p>

      {plan.rubber_stamping_warning && (
        <div className="msg" style={{ background: 'var(--amber-bg)', color: 'var(--amber)', border: '1px solid var(--border)' }}>
          ⚠ {plan.rubber_stamping_warning}
        </div>
      )}

      <CapabilityAdvice advice={plan.capability_advice} />

      {plan.no_delegate.length > 0 && (
        <p style={{ margin: '6px 0', fontSize: 14 }}>
          <strong>Do not delegate:</strong>{' '}
          {plan.no_delegate.map((n) => (
            <span key={n.task} className="tag" title={n.why} style={{ marginRight: 4 }}>
              {n.task}
            </span>
          ))}
        </p>
      )}

      {plan.release_gates.length > 0 && (
        <p style={{ margin: '6px 0', fontSize: 14 }}>
          <strong>Sign-off before release:</strong>{' '}
          {plan.release_gates.map((g) => (
            <span key={g.task} className="tag" title={g.why} style={{ marginRight: 4 }}>
              {g.task}
            </span>
          ))}
        </p>
      )}

      <button className="btn" type="button" onClick={() => setOpen((o) => !o)}>
        {open ? 'Hide checkpoint details' : `Checkpoint details (${plan.checkpoints.length} AI-involved tasks)`}
      </button>

      {open && (
        <div className="table-scroll" style={{ marginTop: 8 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Task</th>
                <th>Checkpoint</th>
                <th>Check against</th>
                <th>Review h</th>
              </tr>
            </thead>
            <tbody>
              {plan.checkpoints.map((c) => {
                const [cls, label] = KIND_BADGE[c.checkpoint] || ['badge-critical', c.checkpoint_label];
                return (
                  <tr key={c.task}>
                    <td style={{ whiteSpace: 'normal' }} title={c.why}>
                      {c.task}
                      {c.advice && (
                        <div className="muted" style={{ fontSize: 12 }}>{c.advice}</div>
                      )}
                    </td>
                    <td>
                      <span className={`badge ${cls}`} title={c.why}>{label}</span>
                    </td>
                    <td style={{ whiteSpace: 'normal', maxWidth: 280 }}>
                      {c.check_against || <span className="muted">no acceptance criteria set</span>}
                    </td>
                    <td>{c.review_hours}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {plan.undecided.length > 0 && (
            <p className="section-hint">
              Still needs a human call on the approach:{' '}
              {plan.undecided.map((u) => u.task).join(', ')}.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
