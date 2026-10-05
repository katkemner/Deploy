import React, { useState } from 'react';

// Pre-run skill check. Some tasks name a skill nobody on the roster has
// ("Campaign Strategy" when people list "Strategy"). For each one we suggest
// the closest roster skill - or say nobody has it, so the work is planned as
// outside help. The user confirms or changes every match before the run.

export const OUTSIDE = '__outside__';

export default function SkillCheck({ check, rosterSkills, outsideRate, onApply, onCancel }) {
  const [choices, setChoices] = useState(() => {
    const c = {};
    check.items.forEach((i) => {
      c[i.skill] = i.suggestion || OUTSIDE;
    });
    return c;
  });
  // Stretched labels: default to the AI's view (a better roster skill, or
  // outside help); the user can keep the original label.
  const stretches = check.stretches || [];
  const [taskChoices, setTaskChoices] = useState(() => {
    const c = {};
    stretches.forEach((st) => {
      c[st.task] = st.suggestion || OUTSIDE;
    });
    return c;
  });
  const [rate, setRate] = useState(outsideRate || '');

  const anyOutside =
    Object.values(choices).some((v) => v === OUTSIDE) ||
    Object.values(taskChoices).some((v) => v === OUTSIDE);
  const methodNote =
    check.method === 'ai'
      ? 'Suggestions are matched by meaning with AI (only the skill names are sent).'
      : 'Suggestions are matched by shared words (AI matching isn’t available right now), so check them carefully.';

  return (
    <div className="card" style={{ borderTop: '4px solid var(--primary)', marginTop: 12 }}>
      <h3 style={{ fontSize: 16, marginTop: 0 }}>
        Skill check: match your tasks to your roster
      </h3>
      {check.items.length > 0 && (
      <>
      <p className="section-hint">
        These tasks name skills nobody on your roster lists, so nobody could
        be staffed on them. Pick the roster skill that covers the work, or
        mark it as outside help if nobody on your team can do it. {methodNote}
      </p>

      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Task skill</th>
              <th>Covered by</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {check.items.map((i) => {
              const options = [...rosterSkills];
              if (i.suggestion && !options.includes(i.suggestion)) options.unshift(i.suggestion);
              return (
                <tr key={i.skill}>
                  <td style={{ fontWeight: 600 }}>{i.skill}</td>
                  <td>
                    <select
                      value={choices[i.skill]}
                      onChange={(e) => setChoices({ ...choices, [i.skill]: e.target.value })}
                      style={{ padding: 5, borderRadius: 6, border: '1px solid var(--border)', maxWidth: 220 }}
                    >
                      {options.map((s) => (
                        <option key={s} value={s}>
                          {s}
                          {s === i.suggestion ? ' (suggested)' : ''}
                        </option>
                      ))}
                      <option value={OUTSIDE}>Nobody on my team — outside help</option>
                    </select>
                  </td>
                  <td className="muted" style={{ fontSize: 12, whiteSpace: 'normal', maxWidth: 300 }}>
                    {i.reason || ''}
                    {i.ai_only && choices[i.skill] === i.suggestion && (
                      <> Only an AI agent has this skill, so an AI agent would do this work.</>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      </>
      )}

      {stretches.length > 0 && (
        <>
          <p className="section-hint" style={{ marginTop: 10 }}>
            <strong>These tasks may be labelled with the wrong skill.</strong>{' '}
            The skill on them is on your roster, but someone with it probably
            couldn’t do this work well — so your team may need outside help.
            Keep the label if you know better.
          </p>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Who should do it</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {stretches.map((st) => {
                  const others = rosterSkills.filter((s) => s !== st.required_skill);
                  return (
                    <tr key={st.task}>
                      <td style={{ whiteSpace: 'normal', fontWeight: 600 }}>
                        {st.task}
                        <div className="muted" style={{ fontSize: 11, fontWeight: 400 }}>
                          labelled “{st.required_skill}”
                          {st.needed_skill && <> · really needs “{st.needed_skill}”</>}
                        </div>
                      </td>
                      <td>
                        <select
                          value={taskChoices[st.task]}
                          onChange={(e) => setTaskChoices({ ...taskChoices, [st.task]: e.target.value })}
                          style={{ padding: 5, borderRadius: 6, border: '1px solid var(--border)', maxWidth: 220 }}
                        >
                          <option value={OUTSIDE}>
                            Outside help{st.needed_skill ? ` (${st.needed_skill})` : ''}
                            {!st.suggestion ? ' (suggested)' : ''}
                          </option>
                          <option value={st.required_skill}>Keep “{st.required_skill}”</option>
                          {others.map((s) => (
                            <option key={s} value={s}>
                              {s}
                              {s === st.suggestion ? ' (suggested)' : ''}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="muted" style={{ fontSize: 12, whiteSpace: 'normal', maxWidth: 300 }}>
                        {st.reason || ''}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {anyOutside && (
        <label className="field" style={{ maxWidth: 320, marginTop: 8 }}>
          <span>Hourly rate for outside help ($, optional)</span>
          <input
            type="number"
            min="0"
            value={rate}
            placeholder="e.g. 100"
            onChange={(e) => setRate(e.target.value)}
          />
          <span className="section-hint" style={{ marginTop: 2 }}>
            Outside-help work is always scheduled. Without a rate its cost is
            left out of the totals, and the results say so.
          </span>
        </label>
      )}

      <div className="card-actions">
        <button className="btn btn-primary" type="button" onClick={() => onApply(choices, rate, taskChoices)}>
          Apply and continue
        </button>
        <button className="btn" type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}
