import React, { useState } from 'react';
import { api } from '../api/client.js';
import TaskScheduleTable from './TaskScheduleTable.jsx';

function Metric({ label, value }) {
  return (
    <div className="metric-row">
      <span className="label">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function toggle(set, name) {
  const next = new Set(set);
  next.has(name) ? next.delete(name) : next.add(name);
  return next;
}

export default function ManualTeamBuilder({ employees, aiAgents }) {
  const [humans, setHumans] = useState(new Set());
  const [ais, setAis] = useState(new Set());
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.runManualTeam([...humans], [...ais]);
      setResult(res);
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  function quickPickBest() {
    setHumans(new Set(['Sarah', 'Maya', 'Priya', 'Alex', 'Casey']));
    setAis(new Set(['AI Research Agent', 'AI QA Reviewer']));
  }

  return (
    <div className="card">
      <h2>Manual Team Builder</h2>
      <p className="section-hint">
        Pick humans and AI agents, then simulate just that team.
      </p>

      <div className="grid-2">
        <div>
          <h3>Humans</h3>
          <div className="checkbox-list" style={{ gridTemplateColumns: '1fr' }}>
            {employees.map((e) => (
              <label className="checkbox-row" key={e.name}>
                <input
                  type="checkbox"
                  checked={humans.has(e.name)}
                  onChange={() => setHumans((s) => toggle(s, e.name))}
                />
                {e.name} <span className="muted">· {e.role}</span>
              </label>
            ))}
          </div>
        </div>
        <div>
          <h3>AI agents</h3>
          <div className="checkbox-list" style={{ gridTemplateColumns: '1fr' }}>
            {aiAgents.map((a) => (
              <label className="checkbox-row" key={a.name}>
                <input
                  type="checkbox"
                  checked={ais.has(a.name)}
                  onChange={() => setAis((s) => toggle(s, a.name))}
                />
                {a.name} <span className="muted">· {a.agent_type}</span>
              </label>
            ))}
          </div>
        </div>
      </div>

      <div className="card-actions">
        <button className="btn btn-primary" onClick={run} disabled={busy}>
          {busy ? 'Simulating…' : 'Run Manual Team Simulation'}
        </button>
        <button className="btn" onClick={quickPickBest} type="button">
          Fill current best team
        </button>
        <span className="muted">
          {humans.size} humans · {ais.size} AI agents selected
        </span>
      </div>

      {error && <div className="msg msg-error">{error}</div>}

      {result && (
        <div style={{ marginTop: 18 }}>
          <h3>
            Result{' '}
            {result.is_valid_team ? (
              <span className="badge badge-valid">valid team</span>
            ) : (
              <span className="badge badge-invalid">invalid team</span>
            )}
          </h3>

          {!result.is_valid_team && result.invalid_reasons.length > 0 && (
            <div className="msg msg-error">
              {result.invalid_reasons.join(' ')}
            </div>
          )}

          <div className="grid-2">
            <div>
              <Metric label="Total score" value={result.total_score} />
              <Metric
                label="Required coverage"
                value={`${result.required_skill_coverage_score}%`}
              />
              <Metric
                label="Optional coverage"
                value={`${result.optional_skill_coverage_score}%`}
              />
              <Metric label="Estimated cost" value={`$${result.estimated_cost}`} />
              <Metric
                label="Estimated duration"
                value={`${result.estimated_duration}h`}
              />
            </div>
            <div>
              <Metric label="Workload balance" value={result.workload_balance_score} />
              <Metric label="Productivity" value={result.productivity_score} />
              <Metric label="Risk" value={result.risk_score} />
              <Metric label="Confidence" value={result.confidence_score} />
              <Metric
                label="Overloaded"
                value={
                  result.overloaded_members.length
                    ? result.overloaded_members.join(', ')
                    : 'none'
                }
              />
            </div>
          </div>

          <Metric
            label="Missing required skills"
            value={
              result.missing_required_skills.length
                ? result.missing_required_skills.join(', ')
                : 'none'
            }
          />
          <Metric
            label="Missing optional skills"
            value={
              result.missing_optional_skills.length
                ? result.missing_optional_skills.join(', ')
                : 'none'
            }
          />

          <h3>Critical path</h3>
          <div className="crit-path">
            {result.critical_path.length
              ? result.critical_path.join('  →  ')
              : '—'}
          </div>

          <div className="explanation">{result.plain_english_explanation}</div>

          <h3>Task schedule</h3>
          <TaskScheduleTable schedule={result.task_schedule} />
        </div>
      )}
    </div>
  );
}
