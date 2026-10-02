import React, { useMemo, useState } from 'react';
import { api } from '../api/client.js';

// Pre-run strength check. Asks, only for the person-skill pairs this
// project's tasks need, how often each person's work on that skill gets
// approved without changes. Prefilled from the roster file or (opt-in) AI
// suggestions from roster notes; every value is the user's to confirm.
// Answers are a one-time input for this run - never stored server-side.

export const ANSWERS = [
  ['unknown', "Don't know"],
  ['almost_always', 'Almost always'],
  ['usually', 'Usually'],
  ['sometimes', 'Sometimes'],
  ['rarely', 'Rarely'],
];

export const pairKey = (person, skill) =>
  `${String(person).toLowerCase()}||${String(skill).toLowerCase()}`;

export default function ProficiencyCheck({ check, answers, onSave, onSkipAll, onCancel }) {
  // Initial values: earlier answer this session, else roster-file prefill,
  // else unknown.
  const [values, setValues] = useState(() => {
    const v = {};
    check.pairs.forEach((p) => {
      const k = pairKey(p.person, p.skill);
      v[k] = answers[k] || p.prefill || 'unknown';
    });
    return v;
  });
  const [sources, setSources] = useState(() => {
    const s = {};
    check.pairs.forEach((p) => {
      const k = pairKey(p.person, p.skill);
      if (!answers[k] && p.prefill) s[k] = `from ${p.source}`;
    });
    return s;
  });
  const [suggesting, setSuggesting] = useState(false);
  const [suggestError, setSuggestError] = useState(null);

  const bySkill = useMemo(() => {
    const groups = {};
    check.pairs.forEach((p) => {
      (groups[p.skill] = groups[p.skill] || []).push(p);
    });
    return groups;
  }, [check.pairs]);

  async function suggestFromNotes() {
    setSuggesting(true);
    setSuggestError(null);
    try {
      const pairs = check.pairs
        .filter((p) => p.has_notes)
        .map((p) => ({ person: p.person, skill: p.skill }));
      const res = await api.proficiencySuggest(pairs);
      const nextV = { ...values };
      const nextS = { ...sources };
      res.suggestions.forEach((s) => {
        if (s.answer && s.answer !== 'unknown') {
          const k = pairKey(s.person, s.skill);
          nextV[k] = s.answer;
          nextS[k] = `suggested from your notes${s.reason ? `: “${s.reason}”` : ''}`;
        }
      });
      setValues(nextV);
      setSources(nextS);
    } catch (err) {
      setSuggestError(err.message);
    } finally {
      setSuggesting(false);
    }
  }

  return (
    <div className="card" style={{ borderTop: '4px solid var(--primary)', marginTop: 12 }}>
      <h3 style={{ fontSize: 16, marginTop: 0 }}>
        Quick check: how strong is your team at this project’s skills?
      </h3>
      <p className="section-hint">{check.why}</p>
      <p className="section-hint" style={{ marginTop: 0 }}>
        For each person: <strong>how often does their work on this skill get
        approved without changes?</strong>
      </p>

      {check.any_notes && (
        <div style={{ margin: '6px 0 10px' }}>
          <button className="btn" type="button" onClick={suggestFromNotes} disabled={suggesting}>
            {suggesting ? 'Reading notes…' : 'Suggest answers from my roster notes'}
          </button>
          <span className="section-hint" style={{ marginLeft: 8 }}>
            Sends the notes of the people listed below to Anthropic. Staging
            demo — don’t upload sensitive employee notes.
          </span>
          {suggestError && <div className="msg msg-error">{suggestError}</div>}
        </div>
      )}

      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Skill</th>
              <th>Person</th>
              <th>Approved without changes…</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(bySkill).map(([skill, pairs]) =>
              pairs.map((p, i) => {
                const k = pairKey(p.person, p.skill);
                return (
                  <tr key={k}>
                    <td style={{ fontWeight: i === 0 ? 600 : 400 }}>{i === 0 ? skill : ''}</td>
                    <td>{p.person}</td>
                    <td>
                      <select
                        value={values[k]}
                        onChange={(e) => {
                          setValues({ ...values, [k]: e.target.value });
                          setSources({ ...sources, [k]: undefined });
                        }}
                        style={{ padding: 5, borderRadius: 6, border: '1px solid var(--border)' }}
                      >
                        {ANSWERS.map(([key, label]) => (
                          <option key={key} value={key}>{label}</option>
                        ))}
                      </select>
                    </td>
                    <td className="muted" style={{ fontSize: 12, whiteSpace: 'normal', maxWidth: 300 }}>
                      {sources[k] || ''}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="card-actions">
        <button className="btn btn-primary" type="button" onClick={() => onSave(values)}>
          Save and run
        </button>
        <button className="btn" type="button" onClick={onSkipAll}>
          Skip all — run without it
        </button>
        <button className="btn" type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}
