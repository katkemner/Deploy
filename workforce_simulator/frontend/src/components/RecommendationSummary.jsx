import React, { useState } from 'react';
import TaskScheduleTable from './TaskScheduleTable.jsx';

// The single big result card: recommended team, its key numbers, a Monte-Carlo
// realism line (auto-run; no knobs), and the deterministic why/risk rows.
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

function pct(value) {
  return `${Math.round(value * 100)}%`;
}

// One plain-English sentence from the Monte Carlo run: realistic finish and
// the chance of hitting the deadline/budget targets (when set).
function mcLine(mc) {
  const parts = [
    `Realistic finish: ~${mc.duration.p50}h (optimistic ${mc.duration.p10}h, conservative ${mc.duration.p90}h).`,
  ];
  if (mc.probability_meets_deadline !== null && mc.probability_meets_deadline !== undefined) {
    parts.push(
      `Chance of hitting the ${mc.deadline_target_hours}h deadline: ${pct(mc.probability_meets_deadline)}.`
    );
  }
  if (mc.probability_within_budget !== null && mc.probability_within_budget !== undefined) {
    parts.push(
      `Chance of staying within $${mc.budget_target}: ${pct(mc.probability_within_budget)}.`
    );
  }
  return parts.join(' ');
}

export default function RecommendationSummary({ recommendation, option, mc, showInnovation }) {
  const [showSchedule, setShowSchedule] = useState(false);
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

      {option && (
        <div className="tag-group" style={{ margin: '4px 0 8px' }}>
          {option.team_members.map((m) => (
            <span key={m} className="tag">
              {m}
            </span>
          ))}
          {option.ai_agents.map((m) => (
            <span key={m} className="tag tag-ai">
              {m}
            </span>
          ))}
        </div>
      )}

      {option && (
        <p style={{ margin: '4px 0 8px', fontSize: 14 }}>
          <strong>${option.estimated_cost}</strong> ·{' '}
          <strong>{option.estimated_duration}h</strong> ·{' '}
          {option.required_skill_coverage_score}% required-skill coverage · risk{' '}
          {option.risk_score}
          {showInnovation && option.innovation_score !== undefined && (
            <> · innovation {option.innovation_score}/100</>
          )}
        </p>
      )}

      {mc && (
        <p style={{ margin: '4px 0 8px', fontSize: 14 }}>{mcLine(mc)}</p>
      )}

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
        {r.ai_time_verdict && (
          <Row label="Does AI save time?">{r.ai_time_verdict}</Row>
        )}
        {r.reviewer_bottleneck_note && (
          <Row label="Reviewer load">{r.reviewer_bottleneck_note}</Row>
        )}
        <Row label="What to change next">
          <strong>{r.what_to_change_next}</strong>
        </Row>
      </div>

      {option && option.task_schedule && (
        <div className="card-actions">
          <button className="btn" onClick={() => setShowSchedule((s) => !s)}>
            {showSchedule ? 'Hide schedule' : 'View schedule'}
          </button>
        </div>
      )}
      {showSchedule && option && <TaskScheduleTable schedule={option.task_schedule} />}
    </div>
  );
}
