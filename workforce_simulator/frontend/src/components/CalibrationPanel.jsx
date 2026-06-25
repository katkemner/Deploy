import React, { useEffect, useState } from 'react';
import { api } from '../api/client.js';

// Read/enter historical project actuals and compare them to predictions.
// Suggested multiplier updates are shown but NEVER applied automatically.

// Numeric prediction/actual pairs to collect.
const PAIRS = [
  ['duration', 'Duration (h)'],
  ['cost', 'Cost ($)'],
  ['human_hours', 'Human hours'],
  ['review_hours', 'Review hours'],
  ['rework_hours', 'Rework hours'],
];

const BLANK = {
  project_id: 'P-001',
  project_name: 'Sample completed project',
  project_type: 'software',
  predicted_duration: 96, actual_duration: 120,
  predicted_cost: 17000, actual_cost: 19500,
  predicted_human_hours: 180, actual_human_hours: 205,
  predicted_review_hours: 22, actual_review_hours: 33,
  predicted_rework_hours: 12, actual_rework_hours: 20,
  predicted_bottleneck: 'Alex', actual_bottleneck: 'Maya',
};

const ERROR_ROWS = [
  ['duration_error_pct', 'Duration'],
  ['cost_error_pct', 'Cost'],
  ['human_hours_error_pct', 'Human hours'],
  ['review_hours_error_pct', 'Review hours'],
  ['rework_hours_error_pct', 'Rework hours'],
];

export default function CalibrationPanel() {
  const [form, setForm] = useState(BLANK);
  const [result, setResult] = useState(null);
  const [summary, setSummary] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [proposals, setProposals] = useState([]);
  const [selected, setSelected] = useState(() => new Set());
  const [applyNotes, setApplyNotes] = useState('');
  const [applyMsg, setApplyMsg] = useState(null);
  const [active, setActive] = useState(null);
  const [toggleBusy, setToggleBusy] = useState(false);

  async function loadSummary() {
    try {
      setSummary(await api.getCalibrationSummary());
    } catch {
      /* best-effort */
    }
  }
  async function loadProposals() {
    try {
      const res = await api.getCalibrationProposals();
      setProposals(res.proposals || []);
    } catch {
      /* best-effort */
    }
  }
  async function loadActive() {
    try {
      setActive(await api.getCalibrationActive());
    } catch {
      /* best-effort */
    }
  }
  useEffect(() => { loadSummary(); loadProposals(); loadActive(); }, []);

  // Flip the config's use_calibration_multipliers flag without touching the
  // applied config itself, so the user can disable calibration and re-enable it.
  async function setUseCalibration(enabled) {
    setToggleBusy(true);
    try {
      const cfg = await api.getConfig();
      delete cfg.weight_provenance;
      cfg.use_calibration_multipliers = enabled;
      await api.saveConfig(cfg);
      await loadActive();
    } catch (err) {
      setApplyMsg({ type: 'error', text: err.message });
    } finally {
      setToggleBusy(false);
    }
  }

  function toggleSel(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function applySelected() {
    if (selected.size === 0) return;
    setApplyMsg(null);
    try {
      const res = await api.applyCalibration([...selected], applyNotes);
      setApplyMsg({ type: 'success',
        text: `Applied ${res.applied_proposals.length}, skipped ${res.rejected_or_skipped_proposals.length}.` });
      setSelected(new Set());
      await loadProposals();
      await loadActive();
    } catch (err) {
      setApplyMsg({ type: 'error', text: err.message });
    }
  }

  async function rejectSelected() {
    if (selected.size === 0) return;
    setApplyMsg(null);
    try {
      const res = await api.rejectCalibration([...selected]);
      setApplyMsg({ type: 'success', text: `Rejected ${res.rejected_proposals.length}.` });
      setSelected(new Set());
      await loadProposals();
      await loadActive();
    } catch (err) {
      setApplyMsg({ type: 'error', text: err.message });
    }
  }

  const setField = (k, v) => setForm({ ...form, [k]: v });

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const payload = { ...form };
      PAIRS.forEach(([k]) => {
        payload[`predicted_${k}`] = Number(form[`predicted_${k}`]);
        payload[`actual_${k}`] = Number(form[`actual_${k}`]);
      });
      const res = await api.submitActuals(payload);
      setResult(res.comparison);
      await loadSummary();
      await loadProposals();
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  const sm = result && result.suggested_multiplier_updates;

  return (
    <div className="card">
      <h2>Calibration</h2>
      <p className="section-hint">
        Enter the actual outcomes of a completed project to compare them with
        the simulator's predictions.
      </p>
      <div className="msg" style={{ background: '#eef2ff', color: '#4338ca', border: '1px solid var(--border)' }}>
        <strong>Calibration suggestions are not applied automatically.</strong>
      </div>

      {active && (
        <div style={{ marginTop: 14 }}>
          <h3 style={{ fontSize: 15 }}>Approved calibration multipliers</h3>
          <div className="msg" style={{ background: 'var(--amber-bg)', color: 'var(--amber)', border: '1px solid var(--border)' }}>
            ⚠ {active.warning}
          </div>
          <label className="field" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <input
              type="checkbox"
              checked={!!active.calibration_multipliers_enabled}
              disabled={toggleBusy}
              onChange={(e) => setUseCalibration(e.target.checked)}
            />
            <span>Use approved calibration multipliers</span>
          </label>
          {!active.config_exists && (
            <p className="section-hint">
              No approved calibration multipliers yet — apply a proposal below to
              create them. Until then, simulations are unaffected.
            </p>
          )}
          {active.config_exists && (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Multiplier</th>
                    <th>Active value</th>
                    <th>Source project</th>
                    <th>Previous</th>
                    <th>What it does</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(active.multipliers || {}).map(([name, value]) => {
                    const prov = (active.calibration_provenance || [])
                      .find((p) => p.multiplier_name === name);
                    return (
                      <tr key={name}>
                        <td>{name.replace(/_/g, ' ')}</td>
                        <td>{value}</td>
                        <td>{prov ? prov.source_project_id : '—'}</td>
                        <td>{prov ? prov.previous_value : '—'}</td>
                        <td style={{ whiteSpace: 'normal', minWidth: 220 }}>
                          {(active.descriptions || {})[name] || ''}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p className="section-hint">
            {active.calibration_multipliers_enabled
              ? 'Approved multipliers are currently applied to new simulations.'
              : 'Approved multipliers are saved but NOT applied to simulations.'}
          </p>
        </div>
      )}

      {/* Identity */}
      <div className="checkbox-list" style={{ gridTemplateColumns: '1fr 1fr 1fr' }}>
        <label className="field"><span>Project id</span>
          <input value={form.project_id} onChange={(e) => setField('project_id', e.target.value)} />
        </label>
        <label className="field"><span>Project name</span>
          <input value={form.project_name} onChange={(e) => setField('project_name', e.target.value)} />
        </label>
        <label className="field"><span>Project type</span>
          <input value={form.project_type} onChange={(e) => setField('project_type', e.target.value)} />
        </label>
      </div>

      {/* Predicted vs actual numeric pairs */}
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr><th>Metric</th><th>Predicted</th><th>Actual</th></tr>
          </thead>
          <tbody>
            {PAIRS.map(([k, label]) => (
              <tr key={k}>
                <td>{label}</td>
                <td>
                  <input type="number" min="0" style={{ width: 110 }}
                    value={form[`predicted_${k}`]}
                    onChange={(e) => setField(`predicted_${k}`, e.target.value)} />
                </td>
                <td>
                  <input type="number" min="0" style={{ width: 110 }}
                    value={form[`actual_${k}`]}
                    onChange={(e) => setField(`actual_${k}`, e.target.value)} />
                </td>
              </tr>
            ))}
            <tr>
              <td>Bottleneck</td>
              <td>
                <input value={form.predicted_bottleneck}
                  onChange={(e) => setField('predicted_bottleneck', e.target.value)} />
              </td>
              <td>
                <input value={form.actual_bottleneck}
                  onChange={(e) => setField('actual_bottleneck', e.target.value)} />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card-actions" style={{ marginTop: 8 }}>
        <button className="btn btn-primary" onClick={submit} disabled={busy}>
          {busy ? 'Comparing…' : 'Compare actuals to prediction'}
        </button>
      </div>
      {error && <div className="msg msg-error">{error}</div>}

      {result && (
        <div style={{ marginTop: 14 }}>
          <h3 style={{ fontSize: 15 }}>Prediction vs actual — error summary</h3>
          <div className="table-scroll">
            <table className="table">
              <thead><tr><th>Metric</th><th>Error %</th></tr></thead>
              <tbody>
                {ERROR_ROWS.map(([k, label]) => (
                  <tr key={k}>
                    <td>{label}</td>
                    <td>{result[k] === null ? '—' : `${result[k]}%`}</td>
                  </tr>
                ))}
                <tr>
                  <td>Bottleneck predicted correctly?</td>
                  <td>{result.bottleneck_correct ? 'yes' : 'no'}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <h3 style={{ fontSize: 15 }}>Suggested multiplier updates</h3>
          <p className="section-hint">
            Informational only — these are <strong>not</strong> applied to
            scoring or simulation.
          </p>
          {sm && (
            <div className="table-scroll">
              <table className="table">
                <tbody>
                  {Object.entries(sm).map(([k, v]) => (
                    <tr key={k}>
                      <td>{k.replace(/_/g, ' ')}</td>
                      <td>{v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="explanation">{result.explanation}</div>
        </div>
      )}

      {proposals.length > 0 && (
        <div style={{ marginTop: 18 }}>
          <h3 style={{ fontSize: 15 }}>Suggested multiplier updates (proposals)</h3>
          <div className="msg" style={{ background: 'var(--amber-bg)', color: 'var(--amber)', border: '1px solid var(--border)' }}>
            ⚠ Applying calibration updates may change future simulation outputs.
          </div>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Select</th>
                  <th>Project</th>
                  <th>Multiplier</th>
                  <th>Current</th>
                  <th>Suggested</th>
                  <th>Confidence</th>
                  <th>Status</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {proposals.map((p) => (
                  <tr key={p.proposal_id}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selected.has(p.proposal_id)}
                        onChange={() => toggleSel(p.proposal_id)}
                      />
                    </td>
                    <td>{p.project_id}</td>
                    <td>{p.current_multiplier_name}</td>
                    <td>{p.current_value}</td>
                    <td>{p.suggested_value}</td>
                    <td>{p.confidence}</td>
                    <td>
                      {p.applied ? (
                        <span className="badge badge-valid">applied</span>
                      ) : p.rejected ? (
                        <span className="badge badge-invalid">rejected</span>
                      ) : (
                        <span className="muted">pending</span>
                      )}
                    </td>
                    <td style={{ whiteSpace: 'normal', minWidth: 240 }}>{p.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <label className="field" style={{ maxWidth: 420 }}>
            <span>Apply notes (optional)</span>
            <input value={applyNotes} onChange={(e) => setApplyNotes(e.target.value)} />
          </label>
          <div className="card-actions" style={{ marginTop: 4 }}>
            <button className="btn btn-primary" onClick={applySelected} disabled={selected.size === 0}>
              Apply selected updates
            </button>
            <button className="btn" onClick={rejectSelected} disabled={selected.size === 0}>
              Reject selected updates
            </button>
            <span className="muted">{selected.size} selected</span>
          </div>
          {applyMsg && (
            <div className={`msg ${applyMsg.type === 'error' ? 'msg-error' : 'msg-success'}`}>
              {applyMsg.text}
            </div>
          )}
        </div>
      )}

      {summary && summary.project_count > 0 && (
        <p className="section-hint" style={{ marginTop: 12 }}>
          History: {summary.project_count} project(s) recorded · mean absolute
          duration error {summary.mean_absolute_error_pct.duration_error_pct ?? '—'}% ·
          bottleneck accuracy {summary.bottleneck_accuracy ?? '—'}.
        </p>
      )}
    </div>
  );
}
