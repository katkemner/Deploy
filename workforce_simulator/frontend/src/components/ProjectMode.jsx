import React, { useEffect, useState } from 'react';
import { api } from '../api/client.js';
import ProjectTaskBuilder from './ProjectTaskBuilder.jsx';
import UploadBriefPanel from './UploadBriefPanel.jsx';
import EmployeeSeedUpload from './EmployeeSeedUpload.jsx';
import RecommendationSummary from './RecommendationSummary.jsx';
import CheckpointPlan from './CheckpointPlan.jsx';
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
  ['Most innovative', 'most_innovative'],
];

// The order options are listed in.
const OPTION_ORDER = [
  'current_team',
  'ai_assisted_current_team',
  'recommended_balanced_team',
  'fastest_valid_team',
  'lowest_cost_valid_team',
  'most_innovative_valid_team',
];

// Plain-language description of what each staffing option represents. The
// whole active roster is the baseline "current team" — the simulation picks
// the team and the AI agents; the user never hand-picks either.
const OPTION_DESCRIPTIONS = {
  current_team: 'Your whole roster, people only — the no-AI baseline.',
  ai_assisted_current_team:
    'Your whole roster plus the AI agents the engine adds where they improve coverage, speed, cost, or risk.',
  recommended_balanced_team:
    'The valid team with the best overall weighted score across all metrics.',
  fastest_valid_team:
    'The valid team with the shortest estimated duration (fully covers required skills).',
  lowest_cost_valid_team:
    'The cheapest valid team (fully covers required skills).',
  most_innovative_valid_team:
    'The valid team with the strongest cross-functional mix for exploring, prototyping, validating, and launching new ideas — while still covering the project’s required skills.',
};

function StepHeading({ n, title, hint }) {
  return (
    <>
      <h3 style={{ fontSize: 17, marginBottom: 2 }}>
        {n}. {title}
      </h3>
      {hint && (
        <p className="section-hint" style={{ marginTop: 2 }}>
          {hint}
        </p>
      )}
    </>
  );
}

// One compact row per staffing option, expandable to full detail. Together the
// rows are the comparison — no separate wide table.
function OptionRow({ option, isRecommended, showInnovation, colCount }) {
  const [open, setOpen] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);
  return (
    <>
      <tr
        style={isRecommended ? { background: '#f0f7ff' } : undefined}
        onClick={() => setOpen((o) => !o)}
        role="button"
      >
        <td style={{ fontWeight: 600, whiteSpace: 'normal' }}>
          {option.option_label}
          {isRecommended && (
            <>
              {' '}
              <span className="badge badge-critical">recommended</span>
            </>
          )}
          {!option.is_valid_team && (
            <>
              {' '}
              <span className="badge badge-invalid">invalid</span>
            </>
          )}
        </td>
        <td style={{ whiteSpace: 'normal' }}>
          {option.team_members.join(', ') || '—'}
          {option.ai_agents.length > 0 && (
            <span className="muted"> + {option.ai_agents.join(', ')}</span>
          )}
        </td>
        <td>${option.estimated_cost}</td>
        <td>{option.estimated_duration}h</td>
        <td>{option.required_skill_coverage_score}%</td>
        <td>{option.risk_score}</td>
        {showInnovation && <td>{option.innovation_score}</td>}
        <td>
          <button
            className="btn"
            onClick={(e) => {
              e.stopPropagation();
              setOpen((o) => !o);
            }}
          >
            {open ? 'Hide' : 'Details'}
          </button>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={colCount} style={{ whiteSpace: 'normal', background: '#fafafa' }}>
            {OPTION_DESCRIPTIONS[option.option] && (
              <p className="section-hint" style={{ marginTop: 0 }}>
                {OPTION_DESCRIPTIONS[option.option]}
              </p>
            )}
            {option.missing_required_skills.length > 0 && (
              <div className="msg msg-error">
                Missing required: {option.missing_required_skills.join(', ')}
              </div>
            )}
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
            <div className="explanation">{option.plain_english_explanation}</div>
            <div className="card-actions">
              <button className="btn" onClick={() => setShowSchedule((s) => !s)}>
                {showSchedule ? 'Hide schedule' : 'View schedule'}
              </button>
            </div>
            {showSchedule && <TaskScheduleTable schedule={option.task_schedule} />}
          </td>
        </tr>
      )}
    </>
  );
}

export default function ProjectMode({ employees, sampleTasks, onEmployeesChange }) {
  // The three inputs that change the answer.
  const [objective, setObjective] = useState('balanced');
  const [deadlineHours, setDeadlineHours] = useState('120');
  const [budget, setBudget] = useState('20000');

  // Advanced (defaults are fine for almost everyone).
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [projectName, setProjectName] = useState('My project');
  const [projectGoal, setProjectGoal] = useState(
    'Staff and deliver the project with the right mix of people and AI agents.'
  );
  const [maxTeamSize, setMaxTeamSize] = useState(5);

  const [tasks, setTasks] = useState([]);

  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // Auto-run Monte Carlo for the recommended team (one line in the results —
  // no iterations/seed knobs; fixed 500 iterations, seed 42, reproducible).
  const [mc, setMc] = useState(null);

  const [showAlternatives, setShowAlternatives] = useState(false);
  const [showRouting, setShowRouting] = useState(false);

  // Active employee digital twin seed roster: 'none' | 'demo' | 'uploaded'.
  // Simulation is gated until the user uploads a seed or chooses demo.
  const [rosterStatus, setRosterStatus] = useState(null);
  const rosterSource = (rosterStatus && rosterStatus.source) || 'none';

  useEffect(() => {
    api.getActiveRoster().then(setRosterStatus).catch(() => {});
  }, []);

  function handleRosterActivated(status) {
    setRosterStatus(status);
    if (onEmployeesChange) onEmployeesChange();
    // Roster changed — results computed against the old roster are stale.
    setResult(null);
    setMc(null);
  }

  // The task list starts EMPTY — a real project's tasks come from the brief
  // upload or manual entry. The sample project is opt-in for exploring.
  function loadSampleTasks() {
    setTasks(
      (sampleTasks || []).map((t) => ({
        task: t.task,
        required_skill: t.required_skill,
        effort_hours: t.effort_hours,
        priority: t.priority,
        dependencies: t.dependencies || [],
        is_required: t.is_required,
      }))
    );
    setResult(null);
    setMc(null);
  }

  async function runProjectSimulation() {
    setBusy(true);
    setError(null);
    setMc(null);
    try {
      const scenario = {
        project_name: projectName,
        project_goal: projectGoal,
        deadline_target_hours: deadlineHours ? Number(deadlineHours) : null,
        budget_target: budget ? Number(budget) : null,
        optimization_objective: objective,
        team_constraints: {
          max_humans_per_team: Number(maxTeamSize),
        },
        tasks,
        // The whole active roster is the baseline — the simulation picks the
        // team. AI agents are recommended by the simulation; the user never
        // enters them or says how many they have.
        current_team_human_names: employees.map((e) => e.name),
        current_team_ai_agent_names: [],
      };
      const res = await api.runProjectSimulation(scenario);
      setResult(res);
      setShowAlternatives(false);
      setShowRouting(false);

      // Best-effort realism line for the recommended team; failures are
      // silent (the deterministic result above stands on its own).
      const rec = res.options[res.recommendation.recommended_option];
      if (rec) {
        try {
          setMc(
            await api.runUncertainty({
              tasks,
              human_names: rec.team_members,
              ai_agent_names: rec.ai_agents,
              iterations: 500,
              seed: 42,
              deadline_target_hours: deadlineHours ? Number(deadlineHours) : null,
              budget_target: budget ? Number(budget) : null,
            })
          );
        } catch {
          setMc(null);
        }
      }
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  const recommendedKey = result ? result.recommendation.recommended_option : null;
  const showInnovation = objective === 'most_innovative';
  const optionColCount = showInnovation ? 8 : 7;

  // One-line routing summary; the full per-task matrix sits behind a toggle.
  const routingLine = result
    ? (() => {
        const s = result.routing_summary || {};
        const d = s.routing_distribution || {};
        const aiOwned = (d.AI_ONLY || 0) + (d.AI_FIRST_HUMAN_REVIEW || 0);
        const net = s.net_ai_time_saved;
        const verdict =
          net > 0
            ? `AI saves a net ~${net}h after review and rework.`
            : `AI does not save time here (net ${net}h after review and rework).`;
        return `AI can lead ${aiOwned} of ${tasks.length} tasks. ${verdict}`;
      })()
    : null;

  return (
    <div className="card" style={{ borderTop: '4px solid var(--primary)' }}>
      <h2 style={{ fontSize: 20 }}>Staff your project</h2>
      <p className="section-hint" style={{ fontSize: 14 }}>
        Three steps: load your people, describe the work, and get a staffing
        recommendation. The simulation picks the team and adds AI agents where
        they genuinely help — you don’t hand-pick either.
      </p>

      {/* ---- Step 1: people ---- */}
      <EmployeeSeedUpload status={rosterStatus} onActivated={handleRosterActivated} />

      {/* ---- Step 2: the work ---- */}
      <StepHeading
        n={2}
        title="The work"
        hint="Upload a project brief and let AI draft the task list, or edit tasks by hand. Every task stays editable."
      />
      <UploadBriefPanel onUseTasks={setTasks} rosterReady={rosterSource !== 'none'} />
      {tasks.length === 0 && (
        <p className="section-hint">
          No tasks yet — upload a brief above, add tasks below, or{' '}
          <button
            type="button"
            onClick={loadSampleTasks}
            disabled={!sampleTasks || sampleTasks.length === 0}
            style={{ border: 'none', background: 'none', padding: 0, color: 'var(--primary)', cursor: 'pointer', textDecoration: 'underline', font: 'inherit' }}
          >
            load the sample project
          </button>{' '}
          just to explore.
        </p>
      )}
      <ProjectTaskBuilder tasks={tasks} onChange={setTasks} />

      <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '16px 0' }} />

      {/* ---- Step 3: the answer ---- */}
      <StepHeading
        n={3}
        title="Your answer"
        hint="Pick what matters most, set your targets, and run."
      />
      <div className="checkbox-list" style={{ gridTemplateColumns: '1fr 1fr 1fr' }}>
        <label className="field">
          <span>What matters most?</span>
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
      </div>

      {showInnovation && (
        <p className="section-hint" style={{ marginTop: 4 }}>
          Most innovative still uses the project’s actual tasks, skills,
          dependencies, effort, and constraints. It adds an innovation lens that
          rewards cross-functional exploration, prototyping, validation, launch
          capability, and innovation-skill coverage while penalizing overload,
          missing skills, bottlenecks, and unhelpful AI review/rework.
        </p>
      )}

      <p style={{ margin: '4px 0' }}>
        <button
          className="btn"
          type="button"
          onClick={() => setShowAdvanced((s) => !s)}
          style={{ border: 'none', background: 'none', padding: 0, color: 'var(--primary)', cursor: 'pointer' }}
        >
          {showAdvanced ? '▾ Hide advanced settings' : '▸ Advanced settings'}
        </button>
      </p>
      {showAdvanced && (
        <div className="checkbox-list" style={{ gridTemplateColumns: '1fr 1fr 1fr' }}>
          <label className="field">
            <span>Project name</span>
            <input
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Project goal</span>
            <input
              type="text"
              value={projectGoal}
              onChange={(e) => setProjectGoal(e.target.value)}
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
        </div>
      )}

      {rosterSource === 'none' && (
        <div className="msg msg-error">
          Upload employee data or choose demo roster (step 1) before running.
        </div>
      )}

      <div className="card-actions">
        <button
          className="btn btn-primary"
          style={{ fontSize: 15, padding: '10px 18px' }}
          onClick={runProjectSimulation}
          disabled={busy || tasks.length === 0 || rosterSource === 'none' || employees.length === 0}
          title={rosterSource === 'none' ? 'Upload employee data or choose demo roster first' : undefined}
        >
          {busy ? 'Comparing staffing options…' : 'Run Project Simulation'}
        </button>
      </div>

      {error && <div className="msg msg-error">{error}</div>}

      {/* ---- Results: one recommendation, alternatives on demand ---- */}
      {result && (
        <div style={{ marginTop: 18 }}>
          <RecommendationSummary
            recommendation={result.recommendation}
            option={result.options[recommendedKey]}
            mc={mc}
            showInnovation={showInnovation}
          />

          <CheckpointPlan plan={result.checkpoint_plan} />

          <p style={{ margin: '10px 0 4px' }}>
            <button
              className="btn"
              type="button"
              onClick={() => setShowAlternatives((s) => !s)}
            >
              {showAlternatives
                ? 'Hide other options'
                : `Compare all ${OPTION_ORDER.length} staffing options`}
            </button>{' '}
            <button className="btn" type="button" onClick={() => setShowRouting((s) => !s)}>
              {showRouting ? 'Hide task-by-task AI detail' : 'Task-by-task AI detail'}
            </button>
          </p>

          {showAlternatives && (
            <div className="table-scroll" style={{ marginTop: 8 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Option</th>
                    <th>Team</th>
                    <th>Cost</th>
                    <th>Duration</th>
                    <th>Coverage</th>
                    <th>Risk</th>
                    {showInnovation && <th>Innovation</th>}
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {OPTION_ORDER.map((key) => (
                    <OptionRow
                      key={key}
                      option={result.options[key]}
                      isRecommended={key === recommendedKey}
                      showInnovation={showInnovation}
                      colCount={optionColCount}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {showRouting ? (
            <div style={{ marginTop: 8 }}>
              <p className="section-hint">
                For each task, a recommended split between humans and AI — from
                AI_ONLY through HUMAN_ONLY — plus the review and rework hours
                that split implies.
              </p>
              <RoutingTable
                routing={result.task_routing}
                summary={result.routing_summary}
              />
            </div>
          ) : (
            routingLine && (
              <p className="muted" style={{ marginTop: 6 }}>
                {routingLine}
              </p>
            )
          )}
        </div>
      )}
    </div>
  );
}
