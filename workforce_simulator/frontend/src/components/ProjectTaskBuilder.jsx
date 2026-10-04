import React, { useState } from 'react';

// Add / edit / delete project tasks without touching CSV files. Dependencies
// are chosen from the names of the other tasks already in the list.
const BLANK = {
  task: '',
  required_skill: '',
  effort_hours: 10,
  priority: 1,
  dependencies: [],
  is_required: true,
  // Acceptance criterion: what "done and correct" looks like. Declared up
  // front so whoever reviews (especially AI output) can check it quickly.
  expected_output: '',
  // Decision-cycle stage; optional. Nudges the AI-vs-human routing priors.
  stage: '',
  // Hard to undo once shipped (external-facing, spend, commitments): lowers
  // AI autonomy and adds a sign-off gate to the checkpoint plan.
  irreversible: false,
};

// Stage options for the dropdown ('' = untagged).
const STAGES = [
  ['', '—'],
  ['attention', 'Attention (monitor / detect)'],
  ['intelligence', 'Intelligence (gather / analyze)'],
  ['design', 'Design (ideas / drafts / prototypes)'],
  ['choice', 'Choice (evaluate / decide / approve)'],
  ['implementation', 'Implementation (produce / execute)'],
  ['feedback', 'Feedback (measure / improve)'],
];

export default function ProjectTaskBuilder({ tasks, onChange }) {
  const [draft, setDraft] = useState(BLANK);
  const [editIndex, setEditIndex] = useState(null);
  // The form is hidden until the user adds or edits a task — the usual path
  // is the AI-drafted list from the brief, with occasional touch-ups.
  const [formOpen, setFormOpen] = useState(false);

  function commit() {
    if (!draft.task.trim() || !draft.required_skill.trim()) return;
    const cleaned = {
      ...draft,
      // A hand-edited skill is no longer the accepted match.
      matched_from:
        editIndex !== null && tasks[editIndex].required_skill !== draft.required_skill.trim()
          ? null
          : draft.matched_from || null,
      task: draft.task.trim(),
      required_skill: draft.required_skill.trim(),
      expected_output: (draft.expected_output || '').trim(),
      stage: draft.stage || null,
      effort_hours: Number(draft.effort_hours) || 0,
      priority: Number(draft.priority) || 1,
      // A task can't depend on itself.
      dependencies: draft.dependencies.filter((d) => d !== draft.task.trim()),
    };
    const next = [...tasks];
    if (editIndex === null) next.push(cleaned);
    else next[editIndex] = cleaned;
    onChange(next);
    setDraft(BLANK);
    setEditIndex(null);
    setFormOpen(false);
  }

  function edit(i) {
    setDraft(tasks[i]);
    setEditIndex(i);
    setFormOpen(true);
  }

  function remove(i) {
    onChange(tasks.filter((_, idx) => idx !== i));
    if (editIndex === i) {
      setDraft(BLANK);
      setEditIndex(null);
    }
  }

  const depChoices = tasks
    .map((t) => t.task)
    .filter((name) => name !== draft.task);

  return (
    <div>
      <h3>Project tasks ({tasks.length})</h3>
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Task</th>
              <th>Skill</th>
              <th>Effort</th>
              <th>Priority</th>
              <th>Stage</th>
              <th>Dependencies</th>
              <th>Acceptance criteria</th>
              <th>Required?</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((t, i) => (
              <tr key={`${t.task}-${i}`}>
                <td>{t.task}</td>
                <td>
                  {t.required_skill}
                  {t.matched_from && (
                    <div className="muted" style={{ fontSize: 11 }}>
                      matched from “{t.matched_from}”
                    </div>
                  )}
                </td>
                <td>{t.effort_hours}h</td>
                <td>{t.priority}</td>
                <td>{t.stage || '—'}</td>
                <td style={{ whiteSpace: 'normal' }}>
                  {t.dependencies && t.dependencies.length
                    ? t.dependencies.join(', ')
                    : '—'}
                </td>
                <td style={{ whiteSpace: 'normal', maxWidth: 260 }}>
                  {t.expected_output ? (
                    t.expected_output
                  ) : (
                    <span className="muted">— add one so review is quick</span>
                  )}
                </td>
                <td>
                  {t.is_required ? (
                    <span className="badge badge-valid">required</span>
                  ) : (
                    <span className="badge badge-critical">optional</span>
                  )}
                </td>
                <td>
                  <button className="btn" onClick={() => edit(i)}>
                    Edit
                  </button>{' '}
                  <button className="btn" onClick={() => remove(i)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!formOpen && (
        <div className="card-actions" style={{ marginTop: 4 }}>
          <button
            className="btn"
            type="button"
            onClick={() => {
              setDraft(BLANK);
              setEditIndex(null);
              setFormOpen(true);
            }}
          >
            ＋ Add a task
          </button>
        </div>
      )}

      {formOpen && (
        <>
      <h3>{editIndex === null ? 'Add a task' : `Edit "${tasks[editIndex].task}"`}</h3>
      <div className="checkbox-list" style={{ gridTemplateColumns: '1fr 1fr' }}>
        <label className="field">
          <span>Task name</span>
          <input
            type="text"
            value={draft.task}
            onChange={(e) => setDraft({ ...draft, task: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Required skill</span>
          <input
            type="text"
            value={draft.required_skill}
            onChange={(e) => setDraft({ ...draft, required_skill: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Effort hours</span>
          <input
            type="number"
            min="1"
            value={draft.effort_hours}
            onChange={(e) => setDraft({ ...draft, effort_hours: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Priority (1 = highest)</span>
          <input
            type="number"
            min="1"
            value={draft.priority}
            onChange={(e) => setDraft({ ...draft, priority: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Stage (optional — nudges AI-vs-human routing)</span>
          <select
            value={draft.stage || ''}
            onChange={(e) => setDraft({ ...draft, stage: e.target.value })}
            style={{ width: '100%', padding: 7, borderRadius: 6, border: '1px solid var(--border)' }}
          >
            {STAGES.map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="field">
        <span>Acceptance criteria — how a reviewer knows it’s done right (optional)</span>
        <textarea
          value={draft.expected_output || ''}
          placeholder="e.g. Approved messaging framework with core message, pillars, and tone"
          onChange={(e) => setDraft({ ...draft, expected_output: e.target.value })}
          style={{ width: '100%', minHeight: 48, padding: 6, fontFamily: 'inherit', fontSize: 13, border: '1px solid var(--border)', borderRadius: 6 }}
        />
      </label>

      <label className="field">
        <span>Dependencies (must finish first)</span>
        <select
          multiple
          value={draft.dependencies}
          onChange={(e) =>
            setDraft({
              ...draft,
              dependencies: Array.from(e.target.selectedOptions, (o) => o.value),
            })
          }
          style={{ width: '100%', minHeight: 70, padding: 6 }}
        >
          {depChoices.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>

      <label className="checkbox-row" style={{ margin: '8px 0' }}>
        <input
          type="checkbox"
          checked={draft.is_required}
          onChange={(e) => setDraft({ ...draft, is_required: e.target.checked })}
        />
        Required skill (unchecked = optional)
      </label>

      <label className="checkbox-row" style={{ margin: '8px 0' }}>
        <input
          type="checkbox"
          checked={!!draft.irreversible}
          onChange={(e) => setDraft({ ...draft, irreversible: e.target.checked })}
        />
        Hard to undo once shipped (external-facing, spend, or commitments) —
        gets a human sign-off gate
      </label>

      <div className="card-actions" style={{ marginTop: 4 }}>
        <button className="btn btn-primary" onClick={commit}>
          {editIndex === null ? 'Add task' : 'Save task'}
        </button>
        <button
          className="btn"
          onClick={() => {
            setDraft(BLANK);
            setEditIndex(null);
            setFormOpen(false);
          }}
        >
          Cancel
        </button>
      </div>
        </>
      )}
    </div>
  );
}
