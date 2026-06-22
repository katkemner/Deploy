import React, { useState } from 'react';
import { api } from '../api/client.js';

// Monte-Carlo uncertainty: samples each task's effort from an optimistic/
// likely/pessimistic range and runs the real scheduler many times, reporting
// P10/P50/P90 duration & cost and the probability of hitting deadline/budget.

function StatBlock({ title, stats, unit, baseline }) {
  return (
    <div>
      <h4 style={{ margin: '6px 0' }}>{title}</h4>
      <div className="metric-row">
        <span className="label">Likely (baseline)</span>
        <span>
          {unit}
          {baseline}
        </span>
      </div>
      <div className="metric-row">
        <span className="label">P10 (optimistic)</span>
        <span>{unit}{stats.p10}</span>
      </div>
      <div className="metric-row">
        <span className="label">P50 (median)</span>
        <span><strong>{unit}{stats.p50}</strong></span>
      </div>
      <div className="metric-row">
        <span className="label">P90 (conservative)</span>
        <span>{unit}{stats.p90}</span>
      </div>
      <div className="metric-row">
        <span className="label">Range (min–max)</span>
        <span>
          {unit}{stats.min} – {unit}{stats.max}
        </span>
      </div>
    </div>
  );
}

function Histogram({ stats, unit }) {
  const max = Math.max(...stats.histogram.map((b) => b.count), 1);
  return (
    <div style={{ marginTop: 8 }}>
      {stats.histogram.map((b, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
          <span style={{ width: 110, textAlign: 'right', color: 'var(--muted)' }}>
            {unit}{b.lo}–{unit}{b.hi}
          </span>
          <span
            style={{
              display: 'inline-block',
              height: 12,
              width: `${(b.count / max) * 100}%`,
              minWidth: b.count ? 2 : 0,
              background: 'var(--primary)',
              borderRadius: 2,
            }}
          />
          <span className="muted">{b.count}</span>
        </div>
      ))}
    </div>
  );
}

function Probability({ label, value }) {
  if (value === null || value === undefined) return null;
  const pct = Math.round(value * 100);
  const good = pct >= 80;
  const ok = pct >= 50;
  const color = good ? 'var(--green)' : ok ? 'var(--amber)' : 'var(--red)';
  return (
    <div className="metric-row">
      <span className="label">{label}</span>
      <span style={{ color, fontWeight: 600 }}>{pct}%</span>
    </div>
  );
}

export default function UncertaintyPanel({
  selectedHumans,
  selectedAis,
  tasks,
  deadlineHours,
  budget,
}) {
  const [iterations, setIterations] = useState(500);
  const [seed, setSeed] = useState(42);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const teamEmpty = selectedHumans.size === 0 && selectedAis.size === 0;

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const payload = {
        tasks,
        human_names: [...selectedHumans],
        ai_agent_names: [...selectedAis],
        iterations: Number(iterations),
        seed: Number(seed),
        deadline_target_hours: deadlineHours ? Number(deadlineHours) : null,
        budget_target: budget ? Number(budget) : null,
      };
      setResult(await api.runUncertainty(payload));
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h3 style={{ fontSize: 16 }}>Uncertainty analysis (Monte Carlo)</h3>
      <p className="section-hint">
        Runs the scheduler many times with each task's effort sampled from an
        optimistic/likely/pessimistic range, for the <strong>current team</strong>{' '}
        selected above. Reproducible for a given seed.
      </p>

      <div className="checkbox-list" style={{ gridTemplateColumns: '1fr 1fr' }}>
        <label className="field">
          <span>Iterations (1–5000)</span>
          <input
            type="number"
            min="1"
            max="5000"
            value={iterations}
            onChange={(e) => setIterations(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Seed (for reproducibility)</span>
          <input
            type="number"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
          />
        </label>
      </div>

      <div className="card-actions" style={{ marginTop: 0 }}>
        <button
          className="btn btn-primary"
          onClick={run}
          disabled={busy || teamEmpty || tasks.length === 0}
        >
          {busy ? 'Running iterations…' : 'Run uncertainty analysis'}
        </button>
        {teamEmpty && (
          <span className="muted">Select a current team above first.</span>
        )}
      </div>

      {error && <div className="msg msg-error">{error}</div>}

      {result && (
        <div style={{ marginTop: 12 }}>
          <p className="muted">
            {result.iterations} iterations · seed {result.seed} ·{' '}
            {result.effort_model.distribution} sampling (band{' '}
            {result.effort_model.default_low_factor}×–
            {result.effort_model.default_high_factor}×)
          </p>

          <div className="grid-2">
            <StatBlock
              title="Project duration (hours)"
              stats={result.duration}
              unit=""
              baseline={result.baseline.duration}
            />
            <StatBlock
              title="Project cost ($)"
              stats={result.cost}
              unit="$"
              baseline={result.baseline.cost}
            />
          </div>

          <div style={{ marginTop: 10 }}>
            <Probability
              label={`Probability of meeting deadline (${result.deadline_target_hours ?? '—'}h)`}
              value={result.probability_meets_deadline}
            />
            <Probability
              label={`Probability of staying within budget ($${result.budget_target ?? '—'})`}
              value={result.probability_within_budget}
            />
          </div>

          <h4 style={{ margin: '12px 0 4px' }}>Duration distribution</h4>
          <Histogram stats={result.duration} unit="" />
        </div>
      )}
    </div>
  );
}
