import React, { useCallback, useEffect, useState } from 'react';
import { api } from './api/client.js';

import Header from './components/Header.jsx';
import HealthStatus from './components/HealthStatus.jsx';
import DataUploadPanel from './components/DataUploadPanel.jsx';
import ConfigPanel from './components/ConfigPanel.jsx';
import EmployeeTable from './components/EmployeeTable.jsx';
import AIAgentTable from './components/AIAgentTable.jsx';
import TaskTable from './components/TaskTable.jsx';
import ManualTeamBuilder from './components/ManualTeamBuilder.jsx';
import SimulationResults from './components/SimulationResults.jsx';

export default function App() {
  const [health, setHealth] = useState('loading'); // loading | ok | error
  const [employees, setEmployees] = useState([]);
  const [aiAgents, setAIAgents] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [config, setConfig] = useState(null);
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
  const refreshAIAgents = useCallback(async () => {
    setAIAgents(await api.getAIAgents());
  }, []);
  const refreshTasks = useCallback(async () => {
    setTasks(await api.getTasks());
  }, []);
  const refreshConfig = useCallback(async () => {
    setConfig(await api.getConfig());
  }, []);

  // Initial load of everything.
  useEffect(() => {
    (async () => {
      await refreshHealth();
      try {
        await Promise.all([
          refreshEmployees(),
          refreshAIAgents(),
          refreshTasks(),
          refreshConfig(),
        ]);
        setLoadError(null);
      } catch (err) {
        setLoadError(err.message);
      }
    })();
  }, [refreshHealth, refreshEmployees, refreshAIAgents, refreshTasks, refreshConfig]);

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

        {/* Data tables */}
        <div className="card">
          <h2>Employees ({employees.length})</h2>
          <EmployeeTable employees={employees} />
        </div>

        <div className="grid-2">
          <div className="card">
            <h2>AI Agents ({aiAgents.length})</h2>
            <AIAgentTable agents={aiAgents} />
          </div>
          <div className="card">
            <h2>Project Tasks ({tasks.length})</h2>
            <TaskTable tasks={tasks} />
          </div>
        </div>

        {/* Data + config management */}
        <div className="grid-2">
          <DataUploadPanel
            onEmployees={refreshEmployees}
            onAIAgents={refreshAIAgents}
            onTasks={refreshTasks}
          />
          <ConfigPanel config={config} onSaved={setConfig} />
        </div>

        {/* Team building */}
        <ManualTeamBuilder employees={employees} aiAgents={aiAgents} />

        {/* Full simulation + comparison */}
        <SimulationResults />

        <p className="muted" style={{ textAlign: 'center', marginTop: 30 }}>
          Workforce Simulator MVP · deterministic engine · backend at{' '}
          <code>http://127.0.0.1:8000</code>
        </p>
      </div>
    </>
  );
}
