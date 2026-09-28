import React, { useState } from 'react';

// Risk-tiered human checkpoint plan for the recommended option: what stays
// human-only, where the checkpoints and release gates go, and whether the
// review load invites rubber-stamping. Compact by default; details expand.
const KIND_BADGE = {
  midstream_and_final: ['badge-invalid', 'mid-stream + review'],
  final_review: ['badge-critical', 'review before hand-off'],
  sampling_audit: ['badge-valid', 'spot-check sample'],
};

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
                    <td style={{ whiteSpace: 'normal' }} title={c.why}>{c.task}</td>
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
