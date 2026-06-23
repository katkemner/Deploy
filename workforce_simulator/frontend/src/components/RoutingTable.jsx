import React, { useState } from 'react';

// Task-level human/AI routing table with the nine suitability scores, the
// routing decision, review/rework estimates, and an expandable "Why?" panel
// that shows the provenance of every score and routing output.

const DECISION_STYLE = {
  AI_ONLY: { background: '#ecfeff', color: '#0e7490' },
  AI_FIRST_HUMAN_REVIEW: { background: '#eff6ff', color: '#1d4ed8' },
  HUMAN_FIRST_AI_ASSIST: { background: '#eef2ff', color: '#4338ca' },
  HUMAN_ONLY: { background: '#fef3e2', color: '#b45309' },
  ESCALATE: { background: '#fdecec', color: '#dc2626' },
};

const SOURCE_STYLE = {
  MANUAL_INPUT: { background: '#eef2ff', color: '#4338ca', label: 'manual input' },
  MATCHED_PUBLIC_PRIOR: { background: '#ecfeff', color: '#0e7490', label: 'public prior' },
  EXISTING_HEURISTIC: { background: '#e8f7ee', color: 'var(--green)', label: 'heuristic' },
  DEFAULT_FALLBACK: { background: '#fef3e2', color: 'var(--amber)', label: 'default' },
};

const SCORE_COLS = [
  ['ai_capability_fit', 'AI fit'],
  ['human_judgment_need', 'Judgment'],
  ['verification_ease', 'Verify'],
  ['error_cost', 'Err cost'],
  ['context_sensitivity', 'Context'],
  ['repetition_level', 'Repeat'],
  ['speed_value', 'Speed'],
  ['human_learning_value', 'Learning'],
  ['collaboration_value', 'Collab'],
];

// Task, Routing, 9 scores, Review, Rework, AI saved, Why = 15 columns.
const TOTAL_COLS = 2 + SCORE_COLS.length + 4;

function DecisionBadge({ decision }) {
  const style = DECISION_STYLE[decision] || {};
  return (
    <span className="badge" style={style}>
      {decision.replace(/_/g, ' ')}
    </span>
  );
}

function SourceBadge({ type }) {
  const s = SOURCE_STYLE[type] || SOURCE_STYLE.DEFAULT_FALLBACK;
  return (
    <span className="badge" style={{ background: s.background, color: s.color }}>
      {s.label}
    </span>
  );
}

function ProvenanceRows({ items }) {
  return items.map((p) => (
    <tr key={p.field_name}>
      <td style={{ fontWeight: 600 }}>{p.field_name}</td>
      <td>{String(p.value)}</td>
      <td>
        <SourceBadge type={p.source_type} />
        {p.match_confidence && (
          <span className="muted" style={{ marginLeft: 4 }}>
            {p.match_confidence}
          </span>
        )}
      </td>
      <td>{p.source_name}</td>
      <td>{Math.round(p.confidence * 100)}%</td>
      <td style={{ whiteSpace: 'normal', minWidth: 260 }}>
        {p.explanation}
        {p.blend_ratio !== undefined && (
          <em> (blend {Math.round(p.blend_ratio * 100)}% prior)</em>
        )}
      </td>
    </tr>
  ));
}

function WhyPanel({ row }) {
  return (
    <div style={{ padding: '10px 4px' }}>
      <p className="section-hint" style={{ marginTop: 0 }}>
        <strong>Why?</strong> — where each number came from.{' '}
        <SourceBadge type="MANUAL_INPUT" /> you supplied it,{' '}
        <SourceBadge type="MATCHED_PUBLIC_PRIOR" /> a matched public prior,{' '}
        <SourceBadge type="EXISTING_HEURISTIC" /> built-in logic,{' '}
        <SourceBadge type="DEFAULT_FALLBACK" /> a default was used.
      </p>
      {row.public_priors_enabled && (
        <p className="section-hint" style={{ marginTop: 0 }}>
          Public priors are <strong>ON</strong>.{' '}
          {row.matched_prior_used
            ? `Matched prior used: ${row.matched_prior_used} (${row.prior_match_confidence}).`
            : `No prior used (match confidence: ${row.prior_match_confidence || 'n/a'}).`}
        </p>
      )}
      {row.prior_warning && (
        <div className="msg" style={{ background: 'var(--amber-bg)', color: 'var(--amber)', border: '1px solid var(--border)' }}>
          ⚠ {row.prior_warning}
        </div>
      )}
      <table className="table">
        <thead>
          <tr>
            <th>Field</th>
            <th>Value</th>
            <th>Source</th>
            <th>Source name</th>
            <th>Confidence</th>
            <th>Explanation</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td colSpan={6} style={{ background: '#f8fafc', fontWeight: 600 }}>
              Suitability scores
            </td>
          </tr>
          <ProvenanceRows items={row.score_provenance || []} />
          <tr>
            <td colSpan={6} style={{ background: '#f8fafc', fontWeight: 600 }}>
              Route &amp; estimates
            </td>
          </tr>
          <ProvenanceRows items={row.route_provenance || []} />
        </tbody>
      </table>
    </div>
  );
}

export default function RoutingTable({ routing, summary }) {
  const [expanded, setExpanded] = useState(() => new Set());
  if (!routing || routing.length === 0) return null;

  function toggle(task) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(task) ? next.delete(task) : next.add(task);
      return next;
    });
  }

  return (
    <div>
      {summary && (
        <div
          className="msg"
          style={{
            background: summary.ai_saves_time ? 'var(--green-bg)' : 'var(--amber-bg)',
            color: summary.ai_saves_time ? 'var(--green)' : 'var(--amber)',
            border: '1px solid var(--border)',
          }}
        >
          <strong>
            {summary.ai_saves_time
              ? 'AI saves net time on this project.'
              : 'AI mostly shifts work to reviewers on this project.'}
          </strong>
          <br />
          AI time saved: {summary.total_ai_time_saved}h · Review burden:{' '}
          {summary.total_review_hours}h · Expected rework:{' '}
          {summary.total_expected_rework_hours}h ·{' '}
          <strong>Net: {summary.net_ai_time_saved}h</strong>
        </div>
      )}
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Task</th>
              <th>Routing</th>
              {SCORE_COLS.map(([, label]) => (
                <th key={label} title={label}>
                  {label}
                </th>
              ))}
              <th>Review h</th>
              <th>Rework h</th>
              <th>AI saved h</th>
              <th>Why?</th>
            </tr>
          </thead>
          <tbody>
            {routing.map((r) => (
              <React.Fragment key={r.task}>
                <tr>
                  <td>{r.task}</td>
                  <td>
                    <DecisionBadge decision={r.routing} />
                  </td>
                  {SCORE_COLS.map(([key]) => (
                    <td key={key} style={{ textAlign: 'center' }}>
                      {r.scores[key] === null || r.scores[key] === undefined
                        ? '—'
                        : r.scores[key]}
                    </td>
                  ))}
                  <td>{r.review_hours}</td>
                  <td>{r.expected_rework_hours}</td>
                  <td>{r.ai_time_saved}</td>
                  <td>
                    <button className="btn" onClick={() => toggle(r.task)}>
                      {expanded.has(r.task) ? 'Hide' : 'Why?'}
                    </button>
                  </td>
                </tr>
                {expanded.has(r.task) && (
                  <tr>
                    <td colSpan={TOTAL_COLS} style={{ background: '#fbfcfe' }}>
                      <WhyPanel row={r} />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
