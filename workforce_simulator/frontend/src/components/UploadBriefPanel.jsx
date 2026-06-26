import React, { useState } from 'react';
import { api } from '../api/client.js';

// Upload a project brief (.docx or text-based PDF), preview the extracted text,
// then — only after the user confirms — have Claude draft editable tasks. The
// LLM only proposes draft tasks; the deterministic engine is never involved.
//
// State machine: idle -> extracting -> preview -> generating -> review.
// On "Use these tasks" the drafts are handed to the parent (ProjectMode),
// which loads them into the existing editable ProjectTaskBuilder.

const STAGE = {
  IDLE: 'idle',
  EXTRACTING: 'extracting',
  PREVIEW: 'preview',
  GENERATING: 'generating',
  REVIEW: 'review',
};

// Map an AI DraftTask onto the ProjectTaskInput shape the simulator expects.
// The review/estimate flags are UI-only and intentionally dropped here.
function toTaskInput(d) {
  return {
    task: d.task,
    required_skill: d.required_skill,
    effort_hours: Number(d.effort_hours) || 0,
    priority: Number(d.priority) || 1,
    dependencies: Array.isArray(d.dependencies) ? d.dependencies : [],
    is_required: true,
    description: d.description || null,
    expected_output: d.expected_output || null,
  };
}

export default function UploadBriefPanel({ onUseTasks }) {
  const [stage, setStage] = useState(STAGE.IDLE);
  const [file, setFile] = useState(null);
  const [extracted, setExtracted] = useState(null); // { text, char_count, ... }
  const [result, setResult] = useState(null); // BriefParseResult
  const [error, setError] = useState(null);

  function reset() {
    setStage(STAGE.IDLE);
    setFile(null);
    setExtracted(null);
    setResult(null);
    setError(null);
  }

  async function handleExtract() {
    if (!file) {
      setError('Choose a .docx or PDF file first.');
      return;
    }
    setStage(STAGE.EXTRACTING);
    setError(null);
    try {
      const res = await api.extractBriefText(file);
      setExtracted(res);
      setStage(STAGE.PREVIEW);
    } catch (err) {
      setError(err.message);
      setStage(STAGE.IDLE);
    }
  }

  async function handleGenerate() {
    setStage(STAGE.GENERATING);
    setError(null);
    try {
      const res = await api.parseBrief(extracted.text);
      setResult(res);
      setStage(STAGE.REVIEW);
    } catch (err) {
      setError(err.message);
      setStage(STAGE.PREVIEW);
    }
  }

  function handleUse() {
    if (!result || !result.draft_tasks) return;
    onUseTasks(result.draft_tasks.map(toTaskInput));
    reset();
  }

  const busy = stage === STAGE.EXTRACTING || stage === STAGE.GENERATING;

  return (
    <div
      className="card"
      style={{ borderTop: '4px solid var(--green)', marginBottom: 16 }}
    >
      <h3 style={{ fontSize: 16, marginTop: 0 }}>
        Start from a project brief (optional)
      </h3>
      <p className="section-hint">
        Upload a Word (.docx) or text-based PDF brief and let AI draft editable
        tasks for you. You review and edit everything before anything runs —
        the AI only fills in the task list, it never picks the team or scores
        options. Manual entry below still works exactly as before.
      </p>

      {/* Step 1: choose a file */}
      <div
        style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}
      >
        <input
          type="file"
          accept=".docx,.pdf"
          disabled={busy}
          onChange={(e) => {
            setFile(e.target.files[0] || null);
            setError(null);
            // Choosing a new file resets any prior preview/draft.
            setExtracted(null);
            setResult(null);
            setStage(STAGE.IDLE);
          }}
        />
        {(stage === STAGE.IDLE || stage === STAGE.EXTRACTING) && (
          <button
            className="btn btn-primary"
            onClick={handleExtract}
            disabled={busy || !file}
          >
            {stage === STAGE.EXTRACTING ? 'Extracting text…' : 'Extract text'}
          </button>
        )}
      </div>

      {error && <div className="msg msg-error">{error}</div>}

      {/* Step 2: preview extracted text + staging warning */}
      {(stage === STAGE.PREVIEW || stage === STAGE.GENERATING) && extracted && (
        <div style={{ marginTop: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <strong>Extracted text ({extracted.char_count} chars)</strong>
            <span className="muted">{extracted.filename}</span>
          </div>
          {extracted.truncated && (
            <div className="msg msg-error">
              The brief was long and has been truncated before drafting.
            </div>
          )}
          <textarea
            readOnly
            value={extracted.text}
            style={{
              width: '100%',
              minHeight: 160,
              marginTop: 6,
              padding: 8,
              fontFamily: 'inherit',
              fontSize: 13,
              border: '1px solid var(--border)',
              borderRadius: 6,
            }}
          />
          <div
            className="msg msg-error"
            style={{ background: '#fff7ed', color: '#9a3412', borderColor: '#fdba74' }}
          >
            ⚠️ <strong>Staging demo.</strong> Clicking “Generate draft tasks”
            sends the text above to Anthropic to draft tasks.{' '}
            <strong>Do not upload sensitive company data yet.</strong>
          </div>
          <div className="card-actions" style={{ marginTop: 8 }}>
            <button
              className="btn btn-primary"
              onClick={handleGenerate}
              disabled={busy}
            >
              {stage === STAGE.GENERATING
                ? 'Generating draft tasks…'
                : 'Generate draft tasks with AI'}
            </button>
            <button className="btn" onClick={reset} disabled={busy}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Step 3: review drafted tasks */}
      {stage === STAGE.REVIEW && result && (
        <div style={{ marginTop: 12 }}>
          <strong>{result.draft_tasks.length} draft task(s)</strong>
          {result.notes && (
            <p className="section-hint" style={{ marginTop: 4 }}>
              {result.notes}
            </p>
          )}
          {result.unmatched_skills && result.unmatched_skills.length > 0 && (
            <div className="msg msg-error">
              Some skills aren’t in your team’s skill list and need review:{' '}
              {result.unmatched_skills.join(', ')}.
            </div>
          )}

          {result.draft_tasks.length > 0 ? (
            <div className="table-scroll" style={{ marginTop: 8 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Task</th>
                    <th>Skill</th>
                    <th>Effort</th>
                    <th>Priority</th>
                    <th>Dependencies</th>
                    <th>Flags</th>
                  </tr>
                </thead>
                <tbody>
                  {result.draft_tasks.map((d, i) => (
                    <tr key={`${d.task}-${i}`}>
                      <td>{d.task}</td>
                      <td>{d.required_skill}</td>
                      <td>
                        {d.effort_hours}h{' '}
                        {d.effort_is_estimated && (
                          <span className="muted" title="AI estimate — please check">
                            est.
                          </span>
                        )}
                      </td>
                      <td>{d.priority}</td>
                      <td style={{ whiteSpace: 'normal' }}>
                        {d.dependencies && d.dependencies.length
                          ? d.dependencies.join(', ')
                          : '—'}
                      </td>
                      <td>
                        {d.needs_user_review ? (
                          <span
                            className="badge badge-critical"
                            title={d.review_reason || 'Needs review'}
                          >
                            check
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="section-hint">
              No tasks were detected. Add them manually below.
            </p>
          )}

          <div className="card-actions" style={{ marginTop: 8 }}>
            <button
              className="btn btn-primary"
              onClick={handleUse}
              disabled={result.draft_tasks.length === 0}
            >
              Use these tasks
            </button>
            <button className="btn" onClick={reset}>
              Discard
            </button>
          </div>
          <p className="section-hint" style={{ marginTop: 4 }}>
            “Use these tasks” loads them into the editable task list below, where
            you can change anything before running the simulation.
          </p>
        </div>
      )}
    </div>
  );
}
