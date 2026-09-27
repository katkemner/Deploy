import React, { useCallback, useEffect, useState } from 'react';
import { api } from './api/client.js';

import Header from './components/Header.jsx';
import HealthStatus from './components/HealthStatus.jsx';
import ProjectMode from './components/ProjectMode.jsx';

export default function App() {
  const [health, setHealth] = useState('loading'); // loading | ok | error
  const [employees, setEmployees] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [loadError, setLoadError] = useState(null);

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
