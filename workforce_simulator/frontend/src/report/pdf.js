// Builds the downloadable PDF report for a run, entirely in the browser.
// jsPDF is loaded on demand so it doesn't slow the first page load.
//
// Content mirrors the results page: inputs, the recommendation, the realistic
// finish, the human checkpoint plan (task-level strength advice only - never
// person-level ratings), the staffing options, and the task list with stages,
// routing and acceptance criteria.

const OPTION_ORDER = [
  'current_team',
  'ai_assisted_current_team',
  'recommended_balanced_team',
  'fastest_valid_team',
  'lowest_cost_valid_team',
  'most_innovative_valid_team',
];

const OBJECTIVE_LABELS = {
  balanced: 'Balanced',
  fastest: 'Fastest delivery',
  lowest_cost: 'Lowest cost',
  best_skill_coverage: 'Best skill coverage',
  best_workload_balance: 'Best workload balance',
  lowest_risk: 'Lowest risk',
  most_innovative: 'Most innovative',
};

const ROUTING_LABELS = {
  AI_ONLY: 'AI only',
  AI_FIRST_HUMAN_REVIEW: 'AI first, human reviews',
  HUMAN_FIRST_AI_ASSIST: 'Human leads, AI assists',
  HUMAN_ONLY: 'Human only',
  ESCALATE: 'Needs a human call',
};

// The built-in PDF fonts only cover basic Latin characters; map the common
// typographic ones and drop anything else rather than printing garbage.
function clean(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[–—]/g, '-')
    .replace(/→/g, '->')
    .replace(/…/g, '...')
    .replace(/[≈]/g, '~')
    .replace(/[^\x20-\x7E -ÿ\n]/g, '');
}

const money = (v) =>
  v === null || v === undefined || v === '' ? '-' : `$${Math.round(Number(v)).toLocaleString('en-US')}`;
const hours = (v) => (v === null || v === undefined || v === '' ? '-' : `${Math.round(Number(v))}h`);
const pct = (v) => (v === null || v === undefined ? '-' : `${Math.round(v * 100)}%`);

export function pdfFilename(run) {
  const base = clean(run.name || 'workforce-run')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '') || 'workforce-run';
  const day = (run.savedAt || new Date().toISOString()).slice(0, 10);
  return `${base}-${day}.pdf`;
}

export async function buildRunPdf(run) {
  const [{ jsPDF }, autoTableMod] = await Promise.all([
    import('jspdf'),
    import('jspdf-autotable'),
  ]);
  const autoTable = autoTableMod.default || autoTableMod.autoTable;

  const { settings = {}, roster = {}, tasks = [], result = {}, mc } = run;
  const rec = result.recommendation || {};
  const opt = (result.options || {})[rec.recommended_option] || {};
  const plan = result.checkpoint_plan || {};

  const doc = new jsPDF({ unit: 'pt', format: 'letter' });
  const pageW = doc.internal.pageSize.getWidth();
  const margin = 48;
  const width = pageW - margin * 2;
  let y = margin;

  const ensure = (h) => {
    if (y + h > doc.internal.pageSize.getHeight() - margin) {
      doc.addPage();
      y = margin;
    }
  };
  const heading = (text) => {
    ensure(40);
    y += 10;
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(13);
    doc.text(clean(text), margin, y);
    y += 16;
  };
  const para = (text, { size = 10, bold = false } = {}) => {
    if (!text) return;
    doc.setFont('helvetica', bold ? 'bold' : 'normal');
    doc.setFontSize(size);
    const lines = doc.splitTextToSize(clean(text), width);
    lines.forEach((line) => {
      ensure(size + 4);
      doc.text(line, margin, y);
      y += size + 4;
    });
    y += 2;
  };
  const table = (head, body, columnStyles = {}, extra = {}) => {
    if (!body.length) return;
    autoTable(doc, {
      startY: y,
      head: [head.map(clean)],
      body: body.map((row) => row.map(clean)),
      margin: { left: margin, right: margin },
      styles: { fontSize: 8.5, cellPadding: 4, overflow: 'linebreak' },
      headStyles: { fillColor: [37, 99, 235] },
      columnStyles,
      ...extra,
    });
    y = doc.lastAutoTable.finalY + 12;
  };

  // ---- Title and inputs ----
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(18);
  doc.text(clean(run.name || 'Staffing recommendation'), margin, y);
  y += 20;
  para(
    `Workforce Simulator report - saved ${new Date(run.savedAt || Date.now()).toLocaleString('en-US')}`,
    { size: 9 }
  );
  table(
    ['Input', 'Value'],
    [
      ['What matters most', OBJECTIVE_LABELS[settings.objective] || settings.objective || '-'],
      ['Deadline target', settings.deadlineHours ? `${settings.deadlineHours}h` : 'none'],
      ['Budget target', settings.budget ? money(settings.budget) : 'none'],
      ['Max team size', settings.maxTeamSize ?? '-'],
      ['Roster', roster.source === 'uploaded'
        ? `Uploaded: ${roster.filename || 'file'} (${roster.count} people)`
        : roster.source === 'demo' ? `Demo roster (${roster.count} people)` : '-'],
      ['Tasks', `${tasks.length} task(s)`],
    ],
    { 0: { cellWidth: 140, fontStyle: 'bold' } }
  );

  // ---- Recommendation ----
  heading(`Recommended: ${rec.recommended_label || '-'}`);
  para(
    `${money(opt.estimated_cost)} - ${hours(opt.estimated_duration)} - ` +
      `${opt.required_skill_coverage_score ?? '-'}% required-skill coverage - risk ${opt.risk_score ?? '-'}` +
      (settings.objective === 'most_innovative' && opt.innovation_score !== undefined
        ? ` - innovation ${Math.round(opt.innovation_score)}/100`
        : ''),
    { bold: true }
  );
  para(
    `Team: ${(opt.team_members || []).join(', ') || '-'}` +
      ((opt.ai_agents || []).length ? ` + AI: ${opt.ai_agents.join(', ')}` : '')
  );
  if (mc && mc.duration) {
    let line = `Realistic finish: ~${hours(mc.duration.p50)} (optimistic ${hours(mc.duration.p10)}, conservative ${hours(mc.duration.p90)}).`;
    if (mc.probability_meets_deadline !== null && mc.probability_meets_deadline !== undefined) {
      line += ` Chance of hitting the deadline: ${pct(mc.probability_meets_deadline)}.`;
    }
    if (mc.probability_within_budget !== null && mc.probability_within_budget !== undefined) {
      line += ` Chance of staying within budget: ${pct(mc.probability_within_budget)}.`;
    }
    para(line);
  }
  table(
    ['', ''],
    [
      ['Why it won', rec.why],
      ['Bottleneck', rec.main_bottleneck],
      ['Critical path', (rec.critical_path || []).join(' -> ')],
      ['Biggest risk', rec.biggest_risk],
      ['AI contribution', rec.ai_contribution],
      ['Does AI save time?', rec.ai_time_verdict],
      ['What to change next', rec.what_to_change_next],
    ].filter(([, v]) => v),
    { 0: { cellWidth: 110, fontStyle: 'bold' } },
    { showHead: 'never' }
  );

  // ---- Human checkpoint plan ----
  heading('Human checkpoint plan');
  para(plan.summary);
  if (plan.rubber_stamping_warning) para(`Warning: ${plan.rubber_stamping_warning}`);
  if ((plan.no_delegate || []).length) {
    para(`Do not delegate: ${plan.no_delegate.map((n) => n.task).join('; ')}`);
  }
  if ((plan.release_gates || []).length) {
    para(`Sign-off before release: ${plan.release_gates.map((g) => g.task).join('; ')}`);
  }
  table(
    ['Task', 'Checkpoint', 'Check against', 'Review h'],
    (plan.checkpoints || []).map((c) => [
      c.task + (c.advice ? `\n${c.advice}` : ''),
      c.checkpoint_label,
      c.check_against || 'no acceptance criteria set',
      c.review_hours,
    ]),
    { 0: { cellWidth: 170 }, 3: { cellWidth: 50 } }
  );
  const advice = plan.capability_advice;
  if (advice && advice.items && advice.items.length) {
    para('Team-strength advice', { bold: true });
    advice.items.forEach((a) => para(`- ${a.task}: ${a.advice}`));
    para(advice.note, { size: 8 });
  }

  // ---- Staffing options ----
  heading('All staffing options');
  table(
    ['Option', 'Team', 'Cost', 'Hours', 'Coverage', 'Risk'],
    OPTION_ORDER.filter((k) => (result.options || {})[k]).map((k) => {
      const o = result.options[k];
      return [
        `${o.option_label}${k === rec.recommended_option ? ' (recommended)' : ''}${o.is_valid_team ? '' : ' (invalid)'}`,
        (o.team_members || []).join(', ') + ((o.ai_agents || []).length ? ` + ${o.ai_agents.join(', ')}` : ''),
        money(o.estimated_cost),
        hours(o.estimated_duration),
        `${o.required_skill_coverage_score}%`,
        o.risk_score,
      ];
    }),
    { 0: { cellWidth: 110 }, 2: { cellWidth: 55 }, 3: { cellWidth: 40 }, 4: { cellWidth: 50 }, 5: { cellWidth: 35 } }
  );

  // ---- Tasks ----
  heading('Tasks');
  const routingByTask = {};
  (result.task_routing || []).forEach((r) => {
    routingByTask[r.task] = r;
  });
  table(
    ['Task', 'Skill', 'Hours', 'Stage', 'Who leads', 'Acceptance criteria'],
    tasks.map((t) => {
      const r = routingByTask[t.task] || {};
      return [
        t.task + (t.irreversible ? ' (hard to undo)' : ''),
        t.required_skill,
        t.effort_hours,
        t.stage || '-',
        ROUTING_LABELS[r.routing] || r.routing || '-',
        t.expected_output || '-',
      ];
    }),
    { 2: { cellWidth: 35 }, 3: { cellWidth: 60 } }
  );

  para(
    'Deterministic engine: the same inputs always give the same results. ' +
      'Advice is about tasks, not people; strength answers are never stored. ' +
      'Estimates are planning aids - a person makes the final staffing decision.',
    { size: 8 }
  );

  doc.save(pdfFilename(run));
}
