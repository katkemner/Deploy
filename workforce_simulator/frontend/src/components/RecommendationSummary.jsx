import React from 'react';

// Top-of-results panel summarising the deterministic recommendation.
function Row({ label, children }) {
  return (
    <div style={{ display: 'flex', gap: 10, padding: '4px 0' }}>
      <span className="muted" style={{ minWidth: 150 }}>
        {label}
      </span>
      <span>{children}</span>
    </div>
  );
}

export default function RecommendationSummary({ recommendation }) {
  if (!recommendation) return null;
  const r = recommendation;
  return (
    <div
      className="card"
      style={{ borderLeft: '4px solid var(--primary)', background: '#f8fbff' }}
    >
      <h2 style={{ borderBottom: 'none', marginBottom: 6 }}>
        Recommended Team: {r.recommended_label}
      </h2>
      <div className="explanation" style={{ marginTop: 0 }}>
        {r.summary_text}
      </div>
      <div style={{ marginTop: 12 }}>
        <Row label="Why it won">{r.why}</Row>
        <Row label="Bottleneck">{r.main_bottleneck}</Row>
        <Row label="Critical path">
          <span className="crit-path" style={{ display: 'inline-block' }}>
            {r.critical_path && r.critical_path.length
              ? r.critical_path.join('  →  ')
              : '—'}
          </span>
        </Row>
        <Row label="Biggest risk">{r.biggest_risk}</Row>
        <Row label="AI contribution">{r.ai_contribution}</Row>
        <Row label="What to change next">
          <strong>{r.what_to_change_next}</strong>
        </Row>
      </div>
    </div>
  );
}
