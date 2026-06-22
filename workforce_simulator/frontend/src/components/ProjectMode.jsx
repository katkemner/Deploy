import React, { useEffect, useState } from 'react';
import { api } from '../api/client.js';
import ProjectTaskBuilder from './ProjectTaskBuilder.jsx';
import CurrentTeamSelector from './CurrentTeamSelector.jsx';
import RecommendationSummary from './RecommendationSummary.jsx';
import ProjectComparisonTable from './ProjectComparisonTable.jsx';
import TaskScheduleTable from './TaskScheduleTable.jsx';
import RoutingTable from './RoutingTable.jsx';

// Objective dropdown: label shown to user -> key sent to the API.
const OBJECTIVES = [
  ['Balanced', 'balanced'],
  ['Fastest delivery', 'fastest'],
  ['Lowest cost', 'lowest_cost'],
  ['Best skill coverage', 'best_skill_coverage'],
  ['Best workload balance', 'best_workload_balance'],
  ['Lowest risk', 'lowest_risk'],
];

// The order option cards are displayed in.
const OPTION_ORDER = [
  'current_team',
  'ai_assisted_current_team',
  'recommended_balanced_team',
  'fastest_valid_team',
  'lowest_cost_valid_team',
];

function Metric({ label, value }) {
  return (
    <div className="metric-row">
      <span className="label">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function OptionCard({ option, isRecommended }) {
  const [showSchedule, setShowSchedule] = useState(false);
  return (
    <div className={`result-card ${isRecommended ? 'selected' : ''}`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong>{option.option_label}</strong>
        {option.is_valid_team ? (
          <span className="badge badge-valid">valid</span>
        ) : (
          <span className="badge badge-invalid">invalid</span>
        )}
      </div>
      {isRecommended && (
        <div style={{ margin: '6px 0' }}>
          <span className="badge badge-critical">recommended</span>
        </div>
      )}

      <div className="tag-group" style={{ margin: '8px 0' }}>
        {option.team_members.map((m) => (
          <span key={m} className="tag">
            {m}
          </span>
        ))}
        {option.ai_agents.map((m) => (
          <span key={m} className="tag tag-ai">
            {m}
          </span>
        ))}
        {option.team_members.length === 0 && option.ai_agents.length === 0 && (
          <span className="muted">empty team</span>
        )}
      </div>

      <Metric label="Total score" value={option.total_score} />
      <Metric label="Required coverage" value={`${option.required_skill_coverage_score}%`} />
      <Metric label="Optional coverage" value={`${option.optional_skill_coverage_score}%`} />
      <Metric label="Estimated cost" value={`$${option.estimated_cost}`} />
      <Metric label="Estimated duration" value={`${option.estimated_duration}h`} />
      <Metric label="Risk" value={option.risk_score} />
      <Metric label="Confidence" value={option.confidence_score} />

      {option.ai_agents_added && option.ai_agents_added.length > 0 && (
        <div className="explanation" style={{ borderLeftColor: 'var(--green)' }}>
          <strong>AI agents added:</strong> {option.ai_agents_added.join(', ')}
          <ul style={{ margin: '6px 0 0 16px', padding: 0 }}>
            {option.ai_assist_notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </div>
      )}

      {option.missing_required_skills.length > 0 && (
        <div className="msg msg-error">
          Missing required: {option.missing_required_skills.join(', ')}
        </div>
      )}

      <div className="crit-path">
        {option.critical_path.length ? option.critical_path.join('  →  ') : '—'}
      </div>
      <div className="explanation">{option.plain_english_explanation}</div>

      <div className="card-actions">
        <button className="btn" onClick={() => setShowSchedule((s) => !s)}>
          {showSchedule ? 'Hide schedule' : 'View schedule'}
        </button>
      </div>
      {showSchedule && <TaskScheduleTable schedule={option.task_schedule} />}
    </div>
  );
}

export default function ProjectMode({ employees, aiAgents, sampleTasks }) {
  const [projectName, setProjectName] = useState('Sample Project');
  const [projectGoal, setProjectGoal] = useState(
    'Staff and deliver the MVP with the right mix of people and AI agents.'
  );
  const [deadlineHours, setDeadlineHours] = useState('');
  const [budget, setBudget] = useState('');
  const [maxTeamSize, setMaxTeamSize] = useState(5);
  const [maxAi, setMaxAi] = useState(2);
  const [objective, setObjective] = useState('balanced');

  const [tasks, setTasks] = useState([]);
  const [selectedHumans, setSelectedHumans] = useState(new Set());
  const [selectedAis, setSelectedAis] = useState(new Set());

  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [routingPreview, setRoutingPreview] = useState(null);
  const [previewBusy, setPreviewBusy] = useState(false);

  // Preload the current sample tasks as the default sample project.
  useEffect(() => {
    if (sampleTasks && sampleTasks.length && tasks.length === 0) {
      setTasks(
        sampleTasks.map((t) => ({
          task: t.task,
          required_skill: t.required_skill,
          effort_hours: t.effort_hours,
          priority: t.priority,
          dependencies: t.dependencies || [],
          is_required: t.is_required,
        }))
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sampleTasks]);

  async function runProjectSimulation() {
    setBusy(true);
    setError(null);
    try {
      const scenario = {
        project_name: projectName,
        project_goal: projectGoal,
        deadline_target_hours: deadlineHours ? Number(deadlineHours) : null,
        budget_target: budget ? Number(budget) : null,
        optimization_objective: objective,
        team_constraints: {
          max_humans_per_team: Number(maxTeamSize),
          max_ai_agents_per_team: Number(maxAi),
        },
        tasks,
        current_team_human_names: [...selectedHumans],
        current_team_ai_agent_names: [...selectedAis],
      };
      const res = await api.runProjectSimulation(scenario);
      setResult(res);
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  function fillBestTeam() {
    setSelectedHumans(new Set(['Sarah', 'Maya', 'Priya', 'Alex', 'Casey']));
    setSelectedAis(new Set(['AI Research Agent', 'AI QA Reviewer']));
  }

  async function previewRouting() {
    setPreviewBusy(true);
    setError(null);
    try {
      const res = await api.routeTasks(tasks);
      setRoutingPreview(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setPreviewBusy(false);
    }
  }

  const recommendedKey = result ? result.recommendation.recommended_option : null;

  return (
    <div className="card" style={{ borderTop: '4px solid var(--primary)' }}>
      <h2 style={{ fontSize: 20 }}>Project Mode</h2>
      <p className="section-hint" style={{ fontSize: 14 }}>
        What project are you trying to staff? Describe the work and your current
        team, then compare staffing options.
      </p>

      {/* Project fields */}
      <div className="checkbox-list" style={{ gridTemplateColumns: '1fr 1fr' }}>
        <label className="field">
          <span>Project name</span>
          <input
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Optimization objective</span>
          <select
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            style={{ width: '100%', padding: 7, borderRadius: 6, border: '1px solid var(--border)' }}
          >
            {OBJECTIVES.map(([label, key]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="field">
        <span>Project goal</span>
        <input
          type="text"
          value={projectGoal}
          onChange={(e) => setProjectGoal(e.target.value)}
        />
      </label>

      <div className="checkbox-list" style={{ gridTemplateColumns: '1fr 1fr 1fr 1fr' }}>
        <label className="field">
          <span>Deadline target (hours)</span>
          <input
            type="number"
            min="0"
            value={deadlineHours}
            placeholder="optional"
            onChange={(e) => setDeadlineHours(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Budget target ($)</span>
          <input
            type="number"
            min="0"
            value={budget}
            placeholder="optional"
            onChange={(e) => setBudget(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Max team size</span>
          <input
            type="number"
            min="1"
            value={maxTeamSize}
            onChange={(e) => setMaxTeamSize(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Max AI agents</span>
          <input
            type="number"
            min="0"
            value={maxAi}
            onChange={(e) => setMaxAi(e.target.value)}
          />
        </label>
      </div>

      <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '8px 0 16px' }} />
      <ProjectTaskBuilder tasks={tasks} onChange={setTasks} />

      <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '16px 0' }} />
      <CurrentTeamSelector
        employees={employees}
        aiAgents={aiAgents}
        tasks={tasks}
        selectedHumans={selectedHumans}
        selectedAis={selectedAis}
        onHumansChange={setSelectedHumans}
        onAisChange={setSelectedAis}
      />

      <div className="card-actions">
        <button
          className="btn btn-primary"
          style={{ fontSize: 15, padding: '10px 18px' }}
          onClick={runProjectSimulation}
          disabled={busy || tasks.length === 0}
        >
          {busy ? 'Comparing staffing options…' : 'Run Project Simulation'}
        </button>
        <button className="btn" onClick={fillBestTeam} type="button">
          Fill current best team
        </button>
        <button
          className="btn"
          onClick={previewRouting}
          type="button"
          disabled={previewBusy || tasks.length === 0}
        >
          {previewBusy ? 'Routing…' : 'Preview task routing'}
        </button>
      </div>

      {error && <div className="msg msg-error">{error}</div>}

      {routingPreview && !result && (
        <div style={{ marginTop: 16 }}>
          <h3 style={{ fontSize: 16 }}>Task Routing (preview)</h3>
          <RoutingTable
            routing={routingPreview.task_routing}
            summary={routingPreview.routing_summary}
          />
        </div>
      )}

      {result && (
        <div style={{ marginTop: 18 }}>
          <RecommendationSummary recommendation={result.recommendation} />

          <h3 style={{ fontSize: 16 }}>Compare Staffing Options</h3>
          <ProjectComparisonTable rows={result.comparison_table} />

          <h3 style={{ fontSize: 16, marginTop: 18 }}>Decision options</h3>
          <div className="result-grid">
            {OPTION_ORDER.map((key) => (
              <OptionCard
                key={key}
                option={result.options[key]}
                isRecommended={key === recommendedKey}
              />
            ))}
          </div>

          <h3 style={{ fontSize: 16, marginTop: 18 }}>
            Task Routing (human vs AI)
          </h3>
          <p className="section-hint">
            How each task should be split between humans and AI, with the review
            and rework hours that routing implies.
          </p>
          <RoutingTable
            routing={result.task_routing}
            summary={result.routing_summary}
          />
        </div>
      )}
    </div>
  );
}
