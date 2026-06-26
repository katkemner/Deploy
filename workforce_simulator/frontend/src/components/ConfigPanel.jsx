import React, { useEffect, useState } from 'react';
import { api } from '../api/client.js';

const WEIGHT_KEYS = [
  'skill_coverage',
  'capacity_fit',
  'productivity',
  'workload_balance',
  'cost_efficiency',
  'low_risk',
];

const CONSTRAINTS = [
  ['min_humans_per_team', 'Min humans'],
  ['max_humans_per_team', 'Max humans'],
  ['min_ai_agents_per_team', 'Min AI agents'],
  ['max_ai_agents_per_team', 'Max AI agents'],
];

export default function ConfigPanel({ config, onSaved }) {
  const [draft, setDraft] = useState(config);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  // Re-sync the editable draft whenever a fresh config arrives.
  useEffect(() => setDraft(config), [config]);

  if (!draft) return <p className="muted">Loading config…</p>;

  const setWeight = (key, value) =>
    setDraft({ ...draft, weights: { ...draft.weights, [key]: value } });

  const setField = (key, value) => setDraft({ ...draft, [key]: value });

  async function handleSave() {
    setBusy(true);
    setMessage(null);
    // Coerce numeric strings to numbers before sending.
    const payload = {
      ...draft,
      weights: Object.fromEntries(
        WEIGHT_KEYS.map((k) => [k, Number(draft.weights[k])])
      ),
      min_humans_per_team: Number(draft.min_humans_per_team),
      max_humans_per_team: Number(draft.max_humans_per_team),
      min_ai_agents_per_team: Number(draft.min_ai_agents_per_team),
      max_ai_agents_per_team: Number(draft.max_ai_agents_per_team),
    };
    try {
      const saved = await api.saveConfig(payload);
      setMessage({ type: 'success', text: 'Config saved.' });
      onSaved(saved);
    } catch (err) {
      setMessage({ type: 'error', text: err.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Scoring Config</h2>
      <p className="section-hint">
        Weights are relative (normalised by the backend). Higher = more
        important.
      </p>

      <h3>Weights</h3>
      <div className="checkbox-list">
        {WEIGHT_KEYS.map((k) => (
          <label className="field" key={k}>
            <span>{k.replace(/_/g, ' ')}</span>
            <input
              type="number"
              min="0"
              value={draft.weights[k]}
              onChange={(e) => setWeight(k, e.target.value)}
            />
          </label>
        ))}
      </div>

      <h3>Team constraints</h3>
      <div className="checkbox-list">
        {CONSTRAINTS.map(([key, label]) => (
          <label className="field" key={key}>
            <span>{label}</span>
            <input
              type="number"
              min="0"
              value={draft[key]}
              onChange={(e) => setField(key, e.target.value)}
            />
          </label>
        ))}
      </div>

      <label className="checkbox-row" style={{ marginBottom: 12 }}>
        <input
          type="checkbox"
          checked={!!draft.require_full_required_skill_coverage}
          onChange={(e) =>
            setField('require_full_required_skill_coverage', e.target.checked)
          }
        />
        require_full_required_skill_coverage (exclude teams missing a required
        skill)
      </label>

      <h3>Scoring data sources (all optional, all off by default)</h3>
      <p className="section-hint">
        These three toggles are independent. Each one decides whether an
        <em> extra data source</em> is allowed to influence the 1–5 task-routing
        suitability scores (and therefore the routing decision and recommended
        team). With all three off, scoring uses only your manual inputs and the
        built-in skill heuristics — the default, deterministic behaviour.
      </p>

      <label className="checkbox-row" style={{ marginBottom: 4 }}>
        <input
          type="checkbox"
          checked={!!draft.use_public_priors_for_scoring}
          onChange={(e) =>
            setField('use_public_priors_for_scoring', e.target.checked)
          }
        />
        Use public priors for scoring
      </label>
      <p className="section-hint" style={{ margin: '0 0 12px 26px' }}>
        <strong>Default: off.</strong> Data source: built-in{' '}
        <strong>representative seed</strong> priors (illustrative values, not
        exact published figures). When on, a matched public prior may
        supply/blend a task's routing scores, so it <strong>can change the
        recommended team</strong>. Every affected score is labelled
        “public prior” in the routing Why? panel.
      </p>

      <label className="checkbox-row" style={{ marginBottom: 4 }}>
        <input
          type="checkbox"
          checked={!!draft.use_workbank_for_scoring}
          onChange={(e) =>
            setField('use_workbank_for_scoring', e.target.checked)
          }
        />
        Use WORKBank for scoring
      </label>
      <p className="section-hint" style={{ margin: '0 0 12px 26px' }}>
        <strong>Default: off.</strong> Data source: your{' '}
        <strong>imported &amp; normalized WORKBank data</strong>
        (<code>data/priors/workbank_normalized.json</code>). When on, a matched
        WORKBank task may supply/blend routing scores and takes precedence over
        public priors, so it <strong>can change the recommended team</strong>.
        If the toggle is on but nothing has been imported, scoring safely falls
        back to public priors / heuristics and a warning is shown.
      </p>

      <p className="section-hint" style={{ marginTop: 0 }}>
        The third data source — <strong>approved calibration multipliers</strong>
        {' '}(from your own historical calibration) — is managed in the{' '}
        <strong>Calibration</strong> panel, including its own “Use approved
        calibration multipliers” toggle.
      </p>

      <button className="btn btn-primary" onClick={handleSave} disabled={busy}>
        {busy ? 'Saving…' : 'Save Config'}
      </button>
      {message && (
        <div className={`msg ${message.type === 'error' ? 'msg-error' : 'msg-success'}`}>
          {message.text}
        </div>
      )}
    </div>
  );
}
