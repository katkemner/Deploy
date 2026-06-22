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
};

export default function ProjectTaskBuilder({ tasks, onChange }) {
  const [draft, setDraft] = useState(BLANK);
  const [editIndex, setEditIndex] = useState(null);

  function commit() {
    if (!draft.task.trim() || !draft.required_skill.trim()) return;
    const cleaned = {
      ...draft,
      task: draft.task.trim(),
      required_skill: draft.required_skill.trim(),
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
  }

  function edit(i) {
    setDraft(tasks[i]);
    setEditIndex(i);
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
              <th>Dependencies</th>
              <th>Required?</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((t, i) => (
              <tr key={`${t.task}-${i}`}>
                <td>{t.task}</td>
                <td>{t.required_skill}</td>
                <td>{t.effort_hours}h</td>
                <td>{t.priority}</td>
                <td style={{ whiteSpace: 'normal' }}>
                  {t.dependencies && t.dependencies.length
                    ? t.dependencies.join(', ')
                    : '—'}
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
      </div>

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

      <div className="card-actions" style={{ marginTop: 4 }}>
        <button className="btn btn-primary" onClick={commit}>
          {editIndex === null ? 'Add task' : 'Save task'}
        </button>
        {editIndex !== null && (
          <button
            className="btn"
            onClick={() => {
              setDraft(BLANK);
              setEditIndex(null);
            }}
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}
