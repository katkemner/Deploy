import React, { useState } from 'react';
import { api } from '../api/client.js';
import TaskScheduleTable from './TaskScheduleTable.jsx';
import ScenarioComparison from './ScenarioComparison.jsx';

function Metric({ label, value }) {
  return (
    <div className="metric-row">
      <span className="label">{label}</span>
      <span>{value}</span>
    </div>
  );
}

export default function SimulationResults() {
  const [results, setResults] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [selectedRank, setSelectedRank] = useState(null);
  const [compare, setCompare] = useState(new Set());

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.runSimulation();
      setResults(res);
      setSelectedRank(null);
      setCompare(new Set());
    } catch (err) {
      setError(err.message);
      setResults([]);
    } finally {
      setBusy(false);
    }
  }

  function toggleCompare(rank) {
    setCompare((s) => {
      const next = new Set(s);
      next.has(rank) ? next.delete(rank) : next.add(rank);
      return next;
    });
  }

  const selected = results.find((r) => r.rank === selectedRank) || null;
  const comparison = results.filter((r) => compare.has(r.rank));

  return (
    <div className="card">
      <h2>Full Simulation</h2>
      <p className="section-hint">
        Generates every valid team within the configured limits and ranks the
        top 5 by total score.
      </p>

      <div className="card-actions" style={{ marginTop: 0 }}>
        <button className="btn btn-primary" onClick={run} disabled={busy}>
          {busy ? 'Running…' : 'Run Full Simulation'}
        </button>
        {results.length > 0 && (
          <span className="muted">Showing top {results.length} teams.</span>
        )}
      </div>

      {error && <div className="msg msg-error">{error}</div>}

      {results.length > 0 && (
        <>
          <div className="result-grid" style={{ marginTop: 16 }}>
            {results.map((r) => (
              <div
                key={r.rank}
                className={`result-card ${r.rank === selectedRank ? 'selected' : ''}`}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="rank">#{r.rank}</span>
                  {r.is_valid_team ? (
                    <span className="badge badge-valid">valid</span>
                  ) : (
                    <span className="badge badge-invalid">invalid</span>
                  )}
                </div>

                <div style={{ margin: '8px 0' }}>
                  {r.team_members.map((m) => (
                    <span key={m} className="tag">
                      {m}
                    </span>
                  ))}
                  {r.ai_agents.map((m) => (
                    <span key={m} className="tag tag-ai">
                      {m}
                    </span>
                  ))}
                </div>

                <Metric label="Total score" value={r.total_score} />
                <Metric label="Required coverage" value={`${r.required_skill_coverage_score}%`} />
                <Metric label="Estimated cost" value={`$${r.estimated_cost}`} />
                <Metric label="Estimated duration" value={`${r.estimated_duration}h`} />
                <Metric label="Risk" value={r.risk_score} />
                <Metric label="Confidence" value={r.confidence_score} />

                <div className="crit-path">
                  {r.critical_path.join('  →  ')}
                </div>
                <div className="explanation">{r.plain_english_explanation}</div>

                <div className="card-actions">
                  <button
                    className="btn"
                    onClick={() =>
                      setSelectedRank(r.rank === selectedRank ? null : r.rank)
                    }
                  >
                    {r.rank === selectedRank ? 'Hide schedule' : 'View schedule'}
                  </button>
                  <label className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={compare.has(r.rank)}
                      onChange={() => toggleCompare(r.rank)}
                    />
                    Compare
                  </label>
                </div>
              </div>
            ))}
          </div>

          {selected && (
            <div style={{ marginTop: 20 }}>
              <h3>Task schedule — Team #{selected.rank}</h3>
              <TaskScheduleTable schedule={selected.task_schedule} />
            </div>
          )}

          <div style={{ marginTop: 20 }}>
            <h3>Scenario comparison</h3>
            <ScenarioComparison teams={comparison} />
          </div>
        </>
      )}
    </div>
  );
}
