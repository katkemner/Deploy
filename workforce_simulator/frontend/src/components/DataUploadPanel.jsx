import React, { useState } from 'react';
import { api } from '../api/client.js';

// One reusable upload row per dataset.
function UploadRow({ label, hint, uploadFn, onUploaded }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null); // { type, text }

  async function handleUpload() {
    if (!file) {
      setMessage({ type: 'error', text: 'Choose a CSV file first.' });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const res = await uploadFn(file);
      setMessage({
        type: 'success',
        text: `${res.message} (${res.rows} rows).`,
      });
      onUploaded();
    } catch (err) {
      setMessage({ type: 'error', text: err.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginBottom: 16 }}>
      <strong>{label}</strong>
      <div className="section-hint">{hint}</div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => {
            setFile(e.target.files[0] || null);
            setMessage(null);
          }}
        />
        <button className="btn btn-primary" onClick={handleUpload} disabled={busy}>
          {busy ? 'Uploading…' : 'Upload'}
        </button>
      </div>
      {message && (
        <div className={`msg ${message.type === 'error' ? 'msg-error' : 'msg-success'}`}>
          {message.text}
        </div>
      )}
    </div>
  );
}

export default function DataUploadPanel({ onEmployees, onAIAgents, onTasks }) {
  return (
    <div className="card">
      <h2>CSV Upload</h2>
      <p className="section-hint">
        Replace the backend sample data. Files are validated by the backend;
        invalid files are rejected and the existing data is kept.
      </p>
      <UploadRow
        label="employees.csv"
        hint="name, role, skills, capacity_hours, workload_hours, cost_rate, quality_score"
        uploadFn={api.uploadEmployees}
        onUploaded={onEmployees}
      />
      <UploadRow
        label="ai_agents.csv"
        hint="name, agent_type, capabilities, capacity_hours, cost_rate, quality_score, speed_multiplier"
        uploadFn={api.uploadAIAgents}
        onUploaded={onAIAgents}
      />
      <UploadRow
        label="project_tasks.csv"
        hint="task, required_skill, effort_hours, priority, dependency_ids, is_required"
        uploadFn={api.uploadTasks}
        onUploaded={onTasks}
      />
    </div>
  );
}
