import React, { useCallback, useEffect, useState } from 'react';
import { api, onWakeChange } from './api/client.js';

import Header from './components/Header.jsx';
import HealthStatus from './components/HealthStatus.jsx';
import ProjectMode from './components/ProjectMode.jsx';

export default function App() {
  const [health, setHealth] = useState('loading'); // loading | ok | error
  const [employees, setEmployees] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [loadError, setLoadError] = useState(null);
  // True while a request is waiting for the sleeping server to wake up.
  const [waking, setWaking] = useState(false);

  useEffect(() => onWakeChange(setWaking), []);

  const refreshHealth = useCallback(async () => {
    setHealth('loading');
    try {
      const res = await api.getHealth();
      setHealth(res.status === 'ok' ? 'ok' : 'error');
    } catch {
      setHealth('error');
    }
  }, []);

  const refreshEmployees = useCallback(async () => {
    setEmployees(await api.getEmployees());
  }, []);
  const refreshTasks = useCallback(async () => {
    setTasks(await api.getTasks());
  }, []);

  useEffect(() => {
    (async () => {
      await refreshHealth();
      try {
        await Promise.all([refreshEmployees(), refreshTasks()]);
        setLoadError(null);
      } catch (err) {
        setLoadError(err.message);
      }
    })();
  }, [refreshHealth, refreshEmployees, refreshTasks]);

  return (
    <>
      <Header
        healthSlot={<HealthStatus status={health} onRetry={refreshHealth} />}
      />
      <div className="container">
        {waking && (
          <div
            className="msg"
            role="status"
            style={{ background: 'var(--amber-bg)', color: 'var(--amber)', border: '1px solid var(--border)' }}
          >
            <strong>Waking up the server…</strong> It sleeps after about 15
            minutes without use and takes up to a minute to start. Your request
            will go through automatically. A restart also clears the uploaded
            roster, so you may need to upload it again.
          </div>
        )}
        {loadError && (
          <div className="msg msg-error">
            Could not load initial data: {loadError}
          </div>
        )}

        <ProjectMode
          employees={employees}
          sampleTasks={tasks}
          onEmployeesChange={refreshEmployees}
        />

        <p className="muted" style={{ textAlign: 'center', marginTop: 30 }}>
          Workforce Simulator MVP · deterministic engine
        </p>
      </div>
    </>
  );
}
