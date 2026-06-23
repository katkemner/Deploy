import React, { useEffect, useState } from 'react';
import { api } from '../api/client.js';

// Read-only view of the loaded public evidence priors (foundation only).
// These are representative seed values and are NOT yet connected to routing
// or scoring — this panel just shows what is loaded.
export default function EvidencePriorsPanel() {
  const [priors, setPriors] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        setPriors(await api.getPriors());
      } catch (err) {
        setError(err.message);
      }
    })();
  }, []);

  if (error) {
    return (
      <div className="card">
        <h2>Evidence Priors</h2>
        <div className="msg msg-error">{error}</div>
      </div>
    );
  }
  if (!priors) {
    return (
      <div className="card">
        <h2>Evidence Priors</h2>
        <p className="muted">Loading priors…</p>
      </div>
    );
  }

  // Count evidence priors citing each source.
  const countFor = (sourceName) =>
    priors.evidence_priors.filter((e) => e.source_name === sourceName).length;

  return (
    <div className="card">
      <h2>
        Evidence Priors{' '}
        {priors.representative_seed && (
          <span className="badge badge-critical">representative seed</span>
        )}
      </h2>
      <div className="msg" style={{ background: 'var(--amber-bg)', color: 'var(--amber)', border: '1px solid var(--border)' }}>
        These are <strong>representative seed</strong> values and are{' '}
        <strong>not yet connected to routing or scoring</strong>. They exist so
        future slices can ground task routing in public evidence.
      </div>

      <p className="section-hint">
        Loaded: {priors.source_weights.length} sources ·{' '}
        {priors.evidence_priors.length} evidence priors ·{' '}
        {priors.task_routing_priors.length} task-routing priors ·{' '}
        {priors.hybrid_guardrail_priors.length} hybrid-guardrail priors.
      </p>

      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Source name</th>
              <th>Source type</th>
              <th>Source weight</th>
              <th>Confidence</th>
              <th>Evidence priors</th>
            </tr>
          </thead>
          <tbody>
            {priors.source_weights.map((s) => (
              <tr key={s.source_name}>
                <td>{s.source_name}</td>
                <td>
                  <span className="tag">{s.source_name}</span>
                </td>
                <td>{s.source_weight}</td>
                <td>{s.source_confidence}</td>
                <td>{countFor(s.source_name)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
