import React from 'react';

// App title bar. Receives the health indicator as a slot so the live API
// status is always visible in the top-right.
export default function Header({ healthSlot }) {
  return (
    <header className="app-header">
      <div className="inner">
        <div>
          <h1>Workforce Simulator</h1>
          <p>Compare people + AI agent teams and predict project outcomes.</p>
        </div>
        <div>{healthSlot}</div>
      </div>
    </header>
  );
}
