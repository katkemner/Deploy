import React, { useState } from 'react';
import { api } from '../api/client.js';

// Step 1 of Project Mode: Employee Digital Twin Seed Upload.
//
// Seed profiles used for simulation — NOT full digital twins. The user uploads
// a .csv/.xlsx seed file (it becomes the active in-memory roster for the
// session) or explicitly chooses the demo roster. Sensitive columns are dropped
// by the backend on ingest and never returned. Nothing is persisted.

function Badge({ source, filename, count }) {
  if (source === 'uploaded') {
    return (
      <span className="badge badge-valid">
        Uploaded seed active{filename ? ` · ${filename}` : ''} ({count})
      </span>
    );
  }
  if (source === 'demo') {
    return <span className="badge badge-critical">Demo roster active ({count})</span>;
  }
  return <span className="badge badge-invalid">No roster chosen</span>;
}

export default function EmployeeSeedUpload({ status, onActivated }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const report = status && status.report;
  const preview = status && status.preview;

  async function handleUpload() {
    if (!file) {
      setError('Choose a .csv or .xlsx seed file first.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await api.uploadEmployeeSeed(file);
      // res.status carries source/count/report; attach the preview rows too.
      onActivated({ ...res.status, preview: res.employees });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleUseDemo() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.useDemoRoster();
      onActivated({ ...res.status, preview: null });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const src = status ? status.source : 'none';

  return (
    <div className="card" style={{ borderTop: '4px solid var(--primary)', marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <h3 style={{ fontSize: 16, margin: 0 }}>1. Employee Digital Twin Seed Upload</h3>
        <Badge source={src} filename={status && status.filename} count={(status && status.employee_count) || 0} />
      </div>
      <p className="section-hint">
        Upload an employee <strong>profile / digital twin seed file</strong> (.xlsx
        or .csv) to use your own people, or use the demo roster. These are{' '}
        <strong>seed profiles used for simulation — not full digital twins yet.</strong>{' '}
        Sensitive fields (DOB, address, SSN/ID, contact, medical, demographics, etc.)
        are dropped on upload and never stored. Nothing is saved to disk — the
        active set resets on restart.
      </p>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          type="file"
          accept=".csv,.xlsx"
          disabled={busy}
          onChange={(e) => {
            setFile(e.target.files[0] || null);
            setError(null);
          }}
        />
        <button className="btn btn-primary" onClick={handleUpload} disabled={busy || !file}>
          {busy ? 'Uploading…' : 'Upload seed file'}
        </button>
        <span className="muted">or</span>
        <button className="btn" onClick={handleUseDemo} disabled={busy} type="button">
          Use demo roster
        </button>
      </div>

      {error && <div className="msg msg-error">{error}</div>}

      <p className="section-hint" style={{ marginTop: 6 }}>
        Required columns: <code>name, role/job_title, department/team, skills,
        capacity_hours, workload_hours</code> (employee_id generated if absent).
        Recommended: cost_rate, quality_score, manager, job_level,
        innovation_capability_tags, and more (captured for context; they don’t
        affect scoring).
      </p>
      <p className="section-hint">
        Note: this seed controls the active employee set used for team selection
        and simulation. The brief-to-task AI draft still uses the existing demo
        skill vocabulary, so generated task skills may need a quick edit to align
        with your uploaded employee seed.
      </p>

      {/* Validation report */}
      {src === 'uploaded' && report && (
        <div style={{ marginTop: 8 }}>
          <strong>Validation report</strong> — {report.employee_count} employees,{' '}
          {report.distinct_skills ? report.distinct_skills.length : 0} distinct skills.
          {report.defaulted_fields && report.defaulted_fields.length > 0 && (
            <div className="msg msg-error" style={{ background: '#fff7ed', color: '#9a3412', borderColor: '#fdba74' }}>
              <strong>Defaulted (not silent):</strong> {report.defaulted_fields.join('; ')}.
            </div>
          )}
          {report.sensitive_columns_dropped && report.sensitive_columns_dropped.length > 0 && (
            <div className="msg msg-error" style={{ background: '#fff7ed', color: '#9a3412', borderColor: '#fdba74' }}>
              <strong>Sensitive columns dropped (ignored, never stored):</strong>{' '}
              {report.sensitive_columns_dropped.join(', ')}.
            </div>
          )}
          {report.recommended_missing && report.recommended_missing.length > 0 && (
            <p className="section-hint">
              Missing recommended fields: {report.recommended_missing.join(', ')}.
            </p>
          )}
          {report.row_errors && report.row_errors.length > 0 && (
            <div className="msg msg-error">
              Skipped {report.row_errors.length} row(s): {report.row_errors.slice(0, 3).join(' ')}
            </div>
          )}
        </div>
      )}

      {/* Preview of uploaded employees (sanitized) */}
      {src === 'uploaded' && preview && preview.length > 0 && (
        <div className="table-scroll" style={{ marginTop: 8 }}>
          <table className="table">
            <thead>
              <tr>
                <th>ID</th><th>Name</th><th>Role</th><th>Dept</th><th>Skills</th>
                <th>Capacity</th><th>Workload</th><th>Cost</th><th>Quality</th>
              </tr>
            </thead>
            <tbody>
              {preview.map((p) => (
                <tr key={p.employee_id + p.name}>
                  <td>{p.employee_id}</td>
                  <td>{p.name}</td>
                  <td>{p.role}</td>
                  <td>{p.department || '—'}</td>
                  <td style={{ whiteSpace: 'normal' }}>{(p.skills || []).join(', ')}</td>
                  <td>{p.capacity_hours}</td>
                  <td>{p.workload_hours}</td>
                  <td>
                    {p.cost_rate}
                    {p.cost_rate_defaulted && <span className="muted" title="defaulted"> *</span>}
                  </td>
                  <td>
                    {p.quality_score}
                    {p.quality_score_defaulted && <span className="muted" title="defaulted"> *</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="section-hint">* = value defaulted because the column was absent.</p>
        </div>
      )}
    </div>
  );
}
