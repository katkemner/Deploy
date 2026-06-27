import React, { useState } from 'react';
import { api } from '../api/client.js';

// Step 1 of Project Mode: bring your own employee roster.
//
// The roster is uploaded fresh each session (staging has no database, so it is
// ephemeral and global — it resets on restart and replaces the current roster
// for everyone). Sample data is only a fallback so the demo works with no
// upload. On success the parent refreshes the employee list and clears any
// stale team selection (old names won't exist in the new roster).
export default function RosterUploadPanel({ employees, onUploaded }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null); // { type, text }

  async function handleUpload() {
    if (!file) {
      setMessage({ type: 'error', text: 'Choose a roster CSV first.' });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const res = await api.uploadEmployees(file);
      setMessage({ type: 'success', text: `Roster replaced — ${res.rows} people.` });
      onUploaded();
    } catch (err) {
      setMessage({ type: 'error', text: err.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ borderTop: '4px solid var(--primary)', marginBottom: 16 }}>
      <h3 style={{ fontSize: 16, marginTop: 0 }}>1. Your team (roster)</h3>
      <p className="section-hint">
        Bring your own people. Upload a roster CSV with the columns:{' '}
        <code>name, role, skills, capacity_hours, workload_hours, cost_rate, quality_score</code>{' '}
        (semicolon-separate multiple skills). It replaces the sample roster for
        this session.
      </p>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          type="file"
          accept=".csv,text/csv"
          disabled={busy}
          onChange={(e) => {
            setFile(e.target.files[0] || null);
            setMessage(null);
          }}
        />
        <button className="btn btn-primary" onClick={handleUpload} disabled={busy || !file}>
          {busy ? 'Uploading…' : 'Upload roster'}
        </button>
        <span className="muted">
          Currently loaded: <strong>{employees.length}</strong> people
          {employees.length > 0 && ' (sample until you upload your own)'}
        </span>
      </div>

      {message && (
        <div className={`msg ${message.type === 'error' ? 'msg-error' : 'msg-success'}`}>
          {message.text}
        </div>
      )}

      <p className="section-hint" style={{ marginTop: 6 }}>
        ⚠️ Staging demo: the roster is not saved — upload it each session, and
        don’t use confidential employee data.
      </p>
    </div>
  );
}
