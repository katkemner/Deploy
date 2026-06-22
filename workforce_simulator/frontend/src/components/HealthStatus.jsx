import React from 'react';

// Small live API status pill. `status` is one of: 'loading' | 'ok' | 'error'.
export default function HealthStatus({ status, onRetry }) {
  const map = {
    loading: { dot: 'dot-wait', text: 'Checking API…' },
    ok: { dot: 'dot-ok', text: 'API: ok' },
    error: { dot: 'dot-bad', text: 'API unreachable' },
  };
  const { dot, text } = map[status] || map.loading;

  return (
    <span style={{ color: '#e2e8f0', fontSize: 13, display: 'inline-flex', alignItems: 'center' }}>
      <span className={`dot ${dot}`} />
      {text}
      {status === 'error' && (
        <button
          className="btn"
          style={{ marginLeft: 10, padding: '3px 9px' }}
          onClick={onRetry}
        >
          Retry
        </button>
      )}
    </span>
  );
}
