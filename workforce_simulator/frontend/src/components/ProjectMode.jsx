import React, { useEffect, useState } from 'react';
import { api } from '../api/client.js';
import ProjectTaskBuilder from './ProjectTaskBuilder.jsx';
import UploadBriefPanel from './UploadBriefPanel.jsx';
import EmployeeSeedUpload from './EmployeeSeedUpload.jsx';
import RecommendationSummary from './RecommendationSummary.jsx';
import CheckpointPlan from './CheckpointPlan.jsx';
import ProficiencyCheck, { pairKey } from './ProficiencyCheck.jsx';
import SkillCheck, { OUTSIDE } from './SkillCheck.jsx';
import { listRuns, saveRun, deleteRun } from '../report/savedRuns.js';
import { buildRunPdf } from '../report/pdf.js';
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

const ROSTER_CLEARED =
  'Your roster was cleared because the server restarted (this happens on every ' +
  'deploy, because rosters are never saved). Upload it again in step 1 — your ' +
  'tasks are still here.';
const ROSTER_CHANGED =
  'The active roster changed since this page loaded (on the shared staging ' +
  'server, someone else may have uploaded one). The page has been updated — ' +
  'check step 1, then run again.';

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
        <td>
          {option.estimated_duration}h
          {option.unstaffed_hours > 0 && (
            <div className="muted" style={{ fontSize: 11 }} title="This team can't do some of the work; its cost and hours leave that work out.">
              +{option.unstaffed_hours}h not staffed
            </div>
          )}
        </td>
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
  // Roster hours are per week; the project length turns them into project
  // hours. Blank = derived from the deadline (hours / 40), else 1 week.
  const [projectWeeks, setProjectWeeks] = useState('');
  // Hourly rate for outside help on skills nobody on the roster has. Blank =
  // that work is still scheduled but its cost isn't included (and we say so).
  const [outsideRate, setOutsideRate] = useState('');
  // Where the targets came from, when prefilled from a brief.
  const [briefNote, setBriefNote] = useState(null);

  // Pre-run skill check: task skills nobody has, matched to roster skills.
  // `confirmedOutside` = skills the user already said need outside help.
  const [skillCheck, setSkillCheck] = useState(null);
  const [confirmedOutside, setConfirmedOutside] = useState(() => new Set());

  const [tasks, setTasks] = useState([]);

  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // Auto-run Monte Carlo for the recommended team (one line in the results —
  // no iterations/seed knobs; fixed 500 iterations, seed 42, reproducible).
  const [mc, setMc] = useState(null);

  // Pre-run strength check (relative-capability advice). Answers live only in
  // this browser session and are sent with each run; the server never stores
  // them. `seenPairs` = pairs already shown, so the check only reappears when
  // new tasks bring new person-skill pairs.
  const [profAnswers, setProfAnswers] = useState({});
  const [seenPairs, setSeenPairs] = useState(() => new Set());
  const [profCheck, setProfCheck] = useState(null);

  // Saved runs live only in this browser (never on the server), so results
  // survive server restarts and can be reopened or downloaded as a PDF.
  const [savedRuns, setSavedRuns] = useState(() => listRuns());
  const [showSaved, setShowSaved] = useState(false);
  const [viewingSaved, setViewingSaved] = useState(null);
  const [saveMsg, setSaveMsg] = useState(null);
  const [pdfBusy, setPdfBusy] = useState(false);

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
    // Roster changed — results computed against the old roster are stale,
    // and so are strength answers about the old roster's people.
    setResult(null);
    setMc(null);
    setProfAnswers({});
    setSeenPairs(new Set());
    setProfCheck(null);
    setSkillCheck(null);
    setConfirmedOutside(new Set());
  }

  // The roster lives only in server memory, so a deploy/restart (or another
  // visitor's upload on the shared staging server) can change it under an
  // open page. Before running, compare with the server; if it changed, sync
  // the page and say so plainly instead of sending stale names.
  async function resyncRoster() {
    const server = await api.getActiveRoster();
    const local = rosterStatus || {};
    const changed =
      server.source !== local.source ||
      server.filename !== local.filename ||
      server.employee_count !== local.employee_count;
    if (!changed) return true;
    handleRosterActivated({ ...server, preview: null });
    setError(server.source === 'none' ? ROSTER_CLEARED : ROSTER_CHANGED);
    return false;
  }

  // Run button: first the skill check (task skills nobody on the roster
  // has), then the strength check when this project's tasks need
  // person-skill pairs not yet seen; otherwise run straight away.
  async function handleRun(forceCheck = false) {
    setError(null);
    try {
      if (!(await resyncRoster())) return;
    } catch {
      // Couldn't reach the server to compare; the run itself will report it.
    }
    try {
      const skills = [...new Set(tasks.map((t) => t.required_skill))];
      const m = await api.mapSkills(skills);
      const pending = m.items.filter((i) => !confirmedOutside.has(i.skill.toLowerCase()));
      if (pending.length > 0) {
        setSkillCheck({ ...m, items: pending, forceCheck });
        return;
      }
    } catch {
      // The skill check is a helper; if it fails, carry on - unmatched work
      // still shows up honestly as outside help in the results.
    }
    continueAfterSkillCheck(tasks, forceCheck, {});
  }

  function applySkillCheck(choices, rate) {
    const byLower = {};
    Object.entries(choices).forEach(([skill, choice]) => {
      byLower[skill.toLowerCase()] = choice;
    });
    const next = tasks.map((t) => {
      const choice = byLower[String(t.required_skill).trim().toLowerCase()];
      if (!choice || choice === OUTSIDE) return t;
      return { ...t, required_skill: choice, matched_from: t.matched_from || t.required_skill };
    });
    const outside = new Set(confirmedOutside);
    Object.entries(byLower).forEach(([skill, choice]) => {
      if (choice === OUTSIDE) outside.add(skill);
    });
    const forceCheck = skillCheck && skillCheck.forceCheck;
    setConfirmedOutside(outside);
    setOutsideRate(rate);
    setTasks(next);
    setSkillCheck(null);
    continueAfterSkillCheck(next, forceCheck, { taskList: next, rate });
  }

  async function continueAfterSkillCheck(taskList, forceCheck, overrides) {
    try {
      const check = await api.proficiencyCheck(taskList);
      const unseen = check.pairs.some((p) => !seenPairs.has(pairKey(p.person, p.skill)));
      if (check.pairs.length > 0 && (unseen || forceCheck)) {
        setProfCheck(check);
        return;
      }
    } catch {
      // The check is optional; if it fails, run without it.
    }
    runProjectSimulation(profAnswers, overrides);
  }

  // Tasks from the brief, plus the budget/timeline the brief states.
  function useBriefTasks(taskList, targets) {
    setTasks(taskList);
    setResult(null);
    setMc(null);
    if (!targets) {
      setBriefNote(null);
      return;
    }
    const notes = [];
    const fmt = (n) => `$${Math.round(n).toLocaleString('en-US')}`;
    if (targets.labor_budget) {
      setBudget(String(Math.round(targets.labor_budget)));
      notes.push(
        `Budget target set to ${fmt(targets.labor_budget)}, the brief’s budget for people` +
          (targets.total_budget ? ` (of ${fmt(targets.total_budget)} total)` : '') + '.'
      );
    } else if (targets.total_budget) {
      setBudget(String(Math.round(targets.total_budget)));
      notes.push(
        `Budget target set to the brief’s total budget, ${fmt(targets.total_budget)}. ` +
          'If part of it is for ads, tools or materials rather than people, lower it.'
      );
    }
    if (targets.budget_notes) notes.push(`Brief: “${targets.budget_notes}”`);
    if (targets.timeline_weeks) {
      const w = Math.round(targets.timeline_weeks * 10) / 10;
      setProjectWeeks(String(w));
      setDeadlineHours(String(Math.round(w * 40)));
      notes.push(`Project length set to ${w} weeks (deadline ${Math.round(w * 40)} working hours).`);
    }
    if (targets.timeline_notes) notes.push(`Brief: “${targets.timeline_notes}”`);
    setBriefNote(notes.length ? notes.join(' ') : null);
  }

  function markSeen(check) {
    const next = new Set(seenPairs);
    check.pairs.forEach((p) => next.add(pairKey(p.person, p.skill)));
    setSeenPairs(next);
  }

  function saveProficiency(values) {
    const next = { ...profAnswers, ...values };
    setProfAnswers(next);
    markSeen(profCheck);
    setProfCheck(null);
    runProjectSimulation(next);
  }

  function skipProficiency() {
    const next = { ...profAnswers };
    profCheck.pairs.forEach((p) => {
      next[pairKey(p.person, p.skill)] = 'unknown';
    });
    setProfAnswers(next);
    markSeen(profCheck);
    setProfCheck(null);
    runProjectSimulation(next);
  }

  function currentRunRecord() {
    const rs = rosterStatus || {};
    return {
      name: projectName,
      savedAt: new Date().toISOString(),
      settings: {
        objective, deadlineHours, budget, maxTeamSize, projectName, projectGoal,
        projectWeeks, outsideRate,
      },
      roster: { source: rs.source, filename: rs.filename, count: rs.employee_count },
      tasks,
      result,
      mc,
    };
  }

  function handleSaveRun() {
    const run = saveRun(currentRunRecord());
    setSavedRuns(listRuns());
    setSaveMsg(
      run
        ? 'Saved in this browser. Find it under "Saved runs" to reopen it or download the PDF.'
        : "Couldn't save: this browser's storage is unavailable or full."
    );
  }

  async function handleDownloadPdf(run) {
    setPdfBusy(true);
    try {
      await buildRunPdf(run || viewingSaved || currentRunRecord());
    } catch (err) {
      setError(`Couldn't create the PDF: ${err.message}`);
    } finally {
      setPdfBusy(false);
    }
  }

  function openSavedRun(run) {
    const st = run.settings || {};
    setObjective(st.objective || 'balanced');
    setDeadlineHours(st.deadlineHours ?? '');
    setBudget(st.budget ?? '');
    setMaxTeamSize(st.maxTeamSize ?? 5);
    setProjectWeeks(st.projectWeeks ?? '');
    setOutsideRate(st.outsideRate ?? '');
    setProjectName(st.projectName || run.name);
    setProjectGoal(st.projectGoal || '');
    setTasks(run.tasks || []);
    setResult(run.result);
    setMc(run.mc || null);
    setViewingSaved(run);
    setSaveMsg(null);
    setShowAlternatives(false);
    setShowRouting(false);
  }

  function removeSavedRun(id) {
    deleteRun(id);
    setSavedRuns(listRuns());
    if (viewingSaved && viewingSaved.id === id) setViewingSaved(null);
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

  // `overrides` carries values set in this same click (state updates land
  // after this call starts).
  async function runProjectSimulation(answers = profAnswers, overrides = {}) {
    const taskList = overrides.taskList || tasks;
    const rate = overrides.rate !== undefined ? overrides.rate : outsideRate;
    setBusy(true);
    setError(null);
    setMc(null);
    try {
      const shared = {
        project_weeks: projectWeeks ? Number(projectWeeks) : null,
        outside_help_rate: rate ? Number(rate) : null,
      };
      const scenario = {
        ...shared,
        project_name: projectName,
        project_goal: projectGoal,
        deadline_target_hours: deadlineHours ? Number(deadlineHours) : null,
        budget_target: budget ? Number(budget) : null,
        optimization_objective: objective,
        team_constraints: {
          max_humans_per_team: Number(maxTeamSize),
        },
        tasks: taskList,
        // The whole active roster is the baseline — the simulation picks the
        // team. AI agents are recommended by the simulation; the user never
        // enters them or says how many they have.
        current_team_human_names: employees.map((e) => e.name),
        current_team_ai_agent_names: [],
        // One-time strength answers for this run (never stored server-side).
        proficiency_answers: Object.entries(answers).map(([k, answer]) => {
          const [person, skill] = k.split('||');
          return { person, skill, answer };
        }),
      };
      const res = await api.runProjectSimulation(scenario);
      setResult(res);
      setViewingSaved(null);
      setSaveMsg(null);
      setShowAlternatives(false);
      setShowRouting(false);

      // Best-effort realism line for the recommended team; failures are
      // silent (the deterministic result above stands on its own).
      const rec = res.options[res.recommendation.recommended_option];
      if (rec) {
        try {
          setMc(
            await api.runUncertainty({
              ...shared,
              tasks: taskList,
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
      setResult(null);
      if (/unknown names/i.test(err.message)) {
        // The server's roster no longer matches this page (e.g. a restart
        // cleared it). Sync and explain instead of showing raw names.
        try {
          await resyncRoster();
        } catch {
          setError(ROSTER_CLEARED);
        }
      } else {
        setError(err.message);
      }
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
      <UploadBriefPanel onUseTasks={useBriefTasks} rosterReady={rosterSource !== 'none'} />
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
      <div className="checkbox-list" style={{ gridTemplateColumns: '1fr 1fr' }}>
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
        <label className="field">
          <span>Project length (weeks)</span>
          <input
            type="number"
            min="0"
            step="0.5"
            value={projectWeeks}
            placeholder={deadlineHours ? `about ${Math.max(1, Math.round((Number(deadlineHours) / 40) * 10) / 10)} (from deadline)` : '1'}
            onChange={(e) => setProjectWeeks(e.target.value)}
          />
        </label>
      </div>
      <p className="section-hint" style={{ marginTop: 2 }}>
        Roster hours are per week: each person’s free hours a week are
        multiplied by the project length.
      </p>
      {briefNote && (
        <p className="section-hint" style={{ marginTop: 2, color: 'var(--green)' }}>
          From your brief: {briefNote}
        </p>
      )}

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
          <label className="field">
            <span>Outside help rate ($/hour)</span>
            <input
              type="number"
              min="0"
              value={outsideRate}
              placeholder="not set"
              onChange={(e) => setOutsideRate(e.target.value)}
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
          onClick={() => handleRun(false)}
          disabled={busy || !!profCheck || !!skillCheck || tasks.length === 0 || rosterSource === 'none' || employees.length === 0}
          title={rosterSource === 'none' ? 'Upload employee data or choose demo roster first' : undefined}
        >
          {busy ? 'Comparing staffing options…' : 'Run Project Simulation'}
        </button>
        {seenPairs.size > 0 && !profCheck && !skillCheck && (
          <button
            className="btn"
            type="button"
            onClick={() => handleRun(true)}
            disabled={busy || tasks.length === 0}
          >
            Review team strengths
          </button>
        )}
      </div>

      {skillCheck && (
        <SkillCheck
          check={skillCheck}
          rosterSkills={[...new Set(employees.flatMap((e) => e.skills || []))].sort()}
          outsideRate={outsideRate}
          onApply={applySkillCheck}
          onCancel={() => setSkillCheck(null)}
        />
      )}

      {profCheck && (
        <ProficiencyCheck
          check={profCheck}
          answers={profAnswers}
          onSave={saveProficiency}
          onSkipAll={skipProficiency}
          onCancel={() => setProfCheck(null)}
        />
      )}

      {error && <div className="msg msg-error">{error}</div>}

      {savedRuns.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <button
            type="button"
            onClick={() => setShowSaved((v) => !v)}
            style={{ border: 'none', background: 'none', padding: 0, color: 'var(--primary)', cursor: 'pointer', font: 'inherit' }}
          >
            {showSaved ? '▾' : '▸'} Saved runs ({savedRuns.length})
          </button>
          {showSaved && (
            <div className="table-scroll" style={{ marginTop: 6 }}>
              <table className="table">
                <tbody>
                  {savedRuns.map((r) => {
                    const ro = r.result && r.result.recommendation;
                    const o = ro && r.result.options[ro.recommended_option];
                    return (
                      <tr key={r.id}>
                        <td style={{ whiteSpace: 'normal' }}>
                          <strong>{r.name}</strong>
                          <div className="muted" style={{ fontSize: 12 }}>
                            {new Date(r.savedAt).toLocaleString()}
                            {o && ` · ${ro.recommended_label} · $${Math.round(o.estimated_cost)} · ${Math.round(o.estimated_duration)}h`}
                          </div>
                        </td>
                        <td style={{ whiteSpace: 'nowrap' }}>
                          <button className="btn" type="button" onClick={() => openSavedRun(r)}>Open</button>{' '}
                          <button className="btn" type="button" disabled={pdfBusy} onClick={() => handleDownloadPdf(r)}>PDF</button>{' '}
                          <button className="btn" type="button" onClick={() => removeSavedRun(r.id)}>Delete</button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="section-hint">
                Saved only in this browser on this device, never on the server.
                Team-strength answers are not included.
              </p>
            </div>
          )}
        </div>
      )}

      {/* ---- Results: one recommendation, alternatives on demand ---- */}
      {result && (
        <div style={{ marginTop: 18 }}>
          {viewingSaved && (
            <div className="msg" style={{ background: 'var(--amber-bg)', color: 'var(--amber)', border: '1px solid var(--border)' }}>
              Viewing a saved run from {new Date(viewingSaved.savedAt).toLocaleString()}.
              It reflects the roster and tasks at that time — run again to update it.
            </div>
          )}
          <div className="card-actions" style={{ marginTop: 0, marginBottom: 8 }}>
            {!viewingSaved && (
              <button className="btn" type="button" onClick={handleSaveRun}>
                Save this run
              </button>
            )}
            <button className="btn" type="button" onClick={() => handleDownloadPdf()} disabled={pdfBusy}>
              {pdfBusy ? 'Building PDF…' : 'Download PDF'}
            </button>
          </div>
          {saveMsg && <p className="section-hint">{saveMsg}</p>}
          <RecommendationSummary
            recommendation={result.recommendation}
            option={result.options[recommendedKey]}
            gap={result.staffing_gap}
            capacityBasis={result.capacity_basis}
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
