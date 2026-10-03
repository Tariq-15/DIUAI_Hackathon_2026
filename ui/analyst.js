/* Analyst copilot (Layer 3): live alert queue, complaint cases, recharges, SHAP evidence, money network, the
   customer's amount habit, 4-part case report, human actions, and the federated-learning results.
   English or Bangla (the case report itself stays English). */
(function () {
  const P = window.Prohori;
  const { L } = P;
  const $ = (id) => document.getElementById(id);
  const S = { alerts: [], seen: new Set(), sel: null, filter: 'all', pinned: false, health: null, first: true, tab: 'alerts', detail: null };
  if (P.embed) $('proto').classList.add('hidden');
  document.addEventListener('click', (e) => { const d = $('proto'); if (d.open && !d.contains(e.target)) d.open = false; });
  $('analyst').value = P.store.get('prohori.analyst') || '';
  $('analyst').addEventListener('input', () => P.store.set('prohori.analyst', $('analyst').value.trim()));
  const tbl = (head, rows) => `<div class="tscroll"><table class="t"><thead><tr>${head.map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>`;
  const pct = (v) => (v == null ? '—' : `${(100 * v).toFixed(1)}%`);

  // ---------------------------------------------------------------- tabs
  const TABS = ['alerts', 'agents', 'model', 'fl', 'audit'];
  function openTab(t) {
    S.tab = t;
    document.querySelectorAll('#tabs button').forEach((x) => x.classList.toggle('on', x.dataset.tab === t));
    TABS.forEach((x) => $(`tab-${x}`).classList.toggle('hidden', x !== t));
    if (t === 'agents') loadAgents();
    if (t === 'model') loadModel();
    if (t === 'fl') loadFL();
    if (t === 'audit') loadAudit();
  }
  $('tabs').addEventListener('click', (e) => {
    const b = e.target.closest('[data-tab]');
    if (b) openTab(b.dataset.tab);
  });

  // ---------------------------------------------------------------- queue
  $('filters').addEventListener('click', (e) => {
    const b = e.target.closest('[data-f]');
    if (!b) return;
    S.filter = b.dataset.f;
    document.querySelectorAll('#filters button').forEach((x) => x.classList.toggle('on', x === b));
    renderFeed();
  });

  const STATUS = {
    held_for_review: ['পর্যালোচনার জন্য আটকে আছে', 'held: needs review'], awaiting_customer: ['গ্রাহকের উত্তরের অপেক্ষা', 'waiting for customer'],
    cancelled_by_customer: ['গ্রাহক বাতিল করেছেন', 'customer cancelled'], sent_after_warning: ['সতর্কতার পরও পাঠিয়েছেন', 'customer sent anyway'],
    released_by_analyst: ['বিশ্লেষক ছেড়ে দিয়েছেন', 'released by analyst'], recipient_frozen: ['প্রাপক স্থগিত', 'recipient frozen'],
    dismissed: ['বাতিল (ভুল সতর্কতা)', 'dismissed'], historical: ['টেস্ট উইন্ডো', 'test window'],
    changed_to_suggested: ['প্রস্তাবিত নম্বরে বদলেছেন', 'switched to the suggested number'],
    complaint_received: ['অভিযোগ গৃহীত', 'complaint received'], details_requested: ['আরও তথ্য চাওয়া হয়েছে', 'details requested'],
    hold_requested: ['টাকা আটকানোর অনুরোধ', 'hold requested'], recipient_contacted: ['প্রাপকের সম্মতি চাওয়া হয়েছে', 'recipient asked for consent'],
    resolved: ['নিষ্পত্তি', 'resolved'],
  };
  const status = (s) => (STATUS[s] ? L(...STATUS[s]) : s);
  const CHOICE = {
    cancelled: ['বাতিল করেছেন', 'cancelled'], confirmed: ['সতর্কতার পর নিশ্চিত করেছেন', 'confirmed after warning'],
    confirmed_pin: ['আবার পিন দিয়ে পাঠিয়েছেন', 're-entered PIN and sent'], used_suggested: ['প্রস্তাবিত নম্বর বেছে নিয়েছেন', 'switched to the suggested number'],
  };

  async function poll() {
    try {
      const list = await P.api(`/api/v1/alerts?all=${S.filter === 'planted' ? 1 : 0}`);
      const fresh = list.filter((a) => a.source === 'live' && !S.seen.has(a.id));
      list.forEach((a) => S.seen.add(a.id));
      S.alerts = list;
      renderFeed(S.first ? [] : fresh.map((a) => a.id));
      if (fresh.length && !S.first && !S.pinned) select(fresh[0].id);
      else if (S.sel) refreshDetail();
      S.first = false;
    } catch (e) { /* API restarting: keep polling */ }
  }

  function renderFeed(flash = []) {
    let a = S.alerts;
    if (S.filter === 'live') a = a.filter((x) => x.source === 'live');
    if (S.filter === 'historical') a = a.filter((x) => x.source === 'historical');
    if (S.filter === 'HOLD') a = a.filter((x) => x.band === 'HOLD');
    if (S.filter === 'planted') a = a.filter((x) => x.planted_id);
    if (S.filter === 'complaint') a = a.filter((x) => x.kind === 'complaint');
    if (S.filter === 'wrong') a = a.filter((x) => x.wrong_number || x.case_type === 'genuine_wrong_send');
    if (S.filter === 'amount') a = a.filter((x) => x.unusual_amount);
    if (S.filter === 'recharge') a = a.filter((x) => x.kind === 'recharge');
    $('count').textContent = `(${P.n(a.length)})`;
    $('feed').innerHTML = a.map((x) => `
      <div class="al ${x.id === S.sel ? 'sel' : ''} ${flash.includes(x.id) ? 'fresh' : ''}" data-id="${x.id}">
        <div class="t"><span><span class="band band-${x.band}">${x.band === 'COMPLAINT' ? L('অভিযোগ', 'COMPLAINT') : x.band}</span>
          ${x.kind === 'complaint' || x.kind === 'recharge' ? '' : `<b class="num">${Math.round(x.risk_score)}</b>`}
          ${x.kind === 'recharge' ? `<span class="chip" style="padding:1px 7px">📱 ${L('রিচার্জ', 'recharge')}</span>` : ''}
          ${x.unusual_amount ? `<span class="chip" style="padding:1px 7px">💰 ${L('অস্বাভাবিক পরিমাণ', 'unusual amount')}</span>` : ''}
          ${x.source === 'live' ? '<span class="chip" style="padding:1px 7px">LIVE</span>' : ''}
          ${x.wrong_number ? `<span class="chip" style="padding:1px 7px">🔢 ${L('ভুল নম্বর?', 'wrong number?')}</span>` : ''}
          ${x.planted_id ? `<span class="chip" style="padding:1px 7px">${P.esc(x.planted_id)}</span>` : ''}</span>
          <span class="num muted">${P.esc(String(x.created).slice(5, 16).replace('T', ' '))}</span></div>
        <div class="r"><span class="num">${P.tk(x.amount)}</span> · ${P.esc(x.sender_id)} → ${P.esc(x.receiver_id || '?')}</div>
        <div class="r">${P.esc(x.title || x.top_reason || '')}</div>
        ${x.kind === 'complaint' ? `<div class="r muted">${P.esc(x.top_reason || '')}</div>` : ''}
        <div class="r muted">${P.esc(status(x.status))}</div></div>`).join('') || `<div class="empty">${L('কোনো অ্যালার্ট নেই', 'No alerts')}</div>`;
  }
  $('feed').addEventListener('click', (e) => {
    const it = e.target.closest('[data-id]');
    if (!it) return;
    S.pinned = true;
    select(it.dataset.id);
  });

  async function select(id, llm = false) {
    S.sel = id;
    renderFeed();
    try {
      const d = await P.api(`/api/v1/alerts/${id}${llm ? '?llm=1' : ''}`);
      S.detail = d;
      renderDetail(d);
    } catch (err) { $('detail').innerHTML = `<div class="panel empty">${P.esc(err.message)}</div>`; }
  }
  async function refreshDetail() {
    if (!S.detail || S.detail.source !== 'live') return;
    const d = await P.api(`/api/v1/alerts/${S.sel}`);
    if (d.status !== S.detail.status || d.customer_choice !== S.detail.customer_choice || d.audit.length !== S.detail.audit.length) {
      S.detail = d;
      renderDetail(d);
    }
  }

  // ---------------------------------------------------------------- detail
  function wrongNumberPanel(sug, typed, choice) {
    if (!sug) return '';
    const who = sug.name_en || sug.name;
    return `<div class="panel"><h3>🔢 ${L('ভুল নম্বর যাচাই (ফেডারেটেড লার্নিং-এ শেখা কি-প্যাড ভুলের খরচ)', 'Wrong-number check (keypad slip costs learned with federated learning)')}</h3>
      ${P.numDiff(typed || sug.typed, sug.msisdn, sug.slip && sug.slip.positions)}
      <div style="font-size:13.5px;line-height:1.5">${L(
        `টাইপ করা নম্বরটি ${P.esc(sug.name || '')} (${P.esc(sug.msisdn)}) থেকে এক কি-প্যাড ভুল দূরে; গ্রাহক সেখানে আগে ${P.bn(sug.count)} বার পাঠিয়েছেন। ${P.esc(sug.slip ? sug.slip.bn : '')}।`,
        `The number typed is one keypad slip from ${P.esc(who || '')} (${P.esc(sug.msisdn)}), whom the customer has paid ${sug.count} times: ${P.esc(sug.slip ? sug.slip.en : '')}.`)}
        <span class="muted">${L('দূরত্ব', 'distance')} ${sug.distance}</span></div>
      ${choice ? `<div class="small" style="margin-top:6px"><b>${L('গ্রাহক', 'Customer')}:</b> ${P.esc(choice)}</div>` : ''}</div>`;
  }

  // the customer's own habit next to this amount (src/serve/habits.py; thresholds from federated analytics)
  function habitPanel(h) {
    if (!h || !h.n) return '';
    const kind = h.kind === 'recharge' ? L('রিচার্জ', 'recharge') : L('সেন্ড মানি', 'Send Money');
    const x = (v) => (v == null ? '—' : `${v >= 10 ? Math.round(v) : (+v).toFixed(1)}×`);
    return `<div class="panel"><h3>💰 ${L(`পরিমাণের অভ্যাস (${kind}): গ্রাহক সাধারণত কত পাঠান`, `Amount habit (${kind}): how much this customer usually moves`)}
        ${h.unusual ? `<span class="chip" style="background:#fff4e5;border-color:#f3d58c">${L('অস্বাভাবিক', 'unusual')}</span>` : `<span class="chip">${L('স্বাভাবিকের মধ্যে', 'within habit')}</span>`}</h3>
      <div class="kv">
        <div><span>${L(`সাধারণ পরিমাণ (শেষ ${P.n(h.n)}টি)`, `Usual amount (last ${h.n})`)}</span><b class="num">${P.tk(h.usual)}</b></div>
        <div><span>${L('মাঝের অর্ধেক', 'Middle half')}</span><b class="num">${P.tk(h.low)} – ${P.tk(h.high)}</b></div>
        <div><span>${L('সবচেয়ে বড়', 'Largest')}</span><b class="num">${P.tk(h.max)}</b></div>
        <div><span>${L('কত ঘন ঘন', 'How often')}</span><b class="num">${h.per_week} ${L('বার / সপ্তাহ', 'a week')}</b></div>
        <div><span>${L('এই পরিমাণ / সাধারণ', 'This amount / usual')}</span><b class="num">${x(h.ratio)} <span class="muted">(${L('সীমা', 'limit')} ${x(h.threshold)})</span></b></div>
        <div><span>${L('২৪ ঘণ্টার মোট / সাধারণ দিন', '24 h total / usual day')}</span><b class="num">${x(h.day_ratio)} <span class="muted">(${L('সীমা', 'limit')} ${x(h.day_threshold)})</span></b></div>
      </div>
      <div style="max-width:520px;margin-top:8px">${P.habitStrip(h, { h: 60 })}</div>
      <div class="small muted">${L(`সীমাগুলো ${P.esc(h.source || 'ফেডারেটেড অ্যানালিটিক্স')} থেকে; ছোট অঙ্ক (${P.tk(h.floor)}-এর কম) কখনো চিহ্নিত হয় না। এটি নিয়ম, মডেল নয়: শুধু একবার জিজ্ঞেস করে।`,
    `Limits from ${P.esc(h.source || 'federated analytics')}; small amounts (under ${P.tk(h.floor)}) are never flagged. A plain rule, not the model: it only asks once.`)}</div></div>`;
  }

  function header(d, extra) {
    const truth = d.truth ? `<span class="chip" title="Known only because the data is synthetic">${L('সিন্থেটিক সত্য', 'synthetic truth')}: ${d.truth.is_fraud ? `fraud ${P.esc(d.truth.scenario)} (${P.esc(d.truth.role)})` : 'legitimate'}</span>` : '';
    return `<div class="row" style="flex-wrap:wrap;gap:10px">
        <span class="band band-${d.band}" style="font-size:14px">${d.band === 'COMPLAINT' ? L('অভিযোগ', 'COMPLAINT') : d.band}</span>
        <b style="font-size:20px" class="num">${P.tk(d.amount)}</b>
        <span class="num">${P.esc(d.sender_id)} → ${P.esc(d.receiver_id || '?')}</span>
        ${d.policy_override ? `<span class="chip">policy: ${P.esc(d.policy_override.replace(/_/g, ' '))}</span>` : ''}
        ${d.planted_id ? `<span class="chip">${P.esc(d.planted_id)}: ${P.esc(d.title)}</span>` : ''} ${truth} ${extra || ''}
      </div>`;
  }

  function evidence(d) {
    if (!d.receiver_id) return '';
    return `<div class="two">
        <div class="panel"><h3>${L('কেন ঝুঁকি (SHAP, এই লেনদেনে)', 'Why it fired (SHAP, this transaction)')}</h3>${shapBars(d.shap)}
          <h3 style="margin-top:14px">${d.kind === 'complaint' ? L('মডেলের কারণ (প্রাপকের দিকে একটি পরীক্ষামূলক লেনদেন)', 'Model reasons (a probe transfer to the receiving wallet)') : L('গ্রাহক যে কারণ দেখেছেন', 'Evidence the customer saw')}</h3>
          <ul style="margin:0;padding-left:18px;font-size:13.5px;line-height:1.5">${d.reasons.map((r) => `<li>${P.esc(L(r.bn, r.en))}<div class="muted">${P.esc(L(r.en, r.bn))}</div></li>`).join('') || `<li class="muted">${L('কোনো কারণ নেই', 'none')}</li>`}</ul></div>
        <div class="panel graph"><h3>${L('টাকার নেটওয়ার্ক (২৪ ঘণ্টা আগে, ৩ ঘণ্টা পরে)', 'Money network (24 h before, 3 h after)')}</h3>${drawNetwork(d.network, d)}
          <div class="legend"><span><i style="background:#005bac"></i>${L('প্রেরক', 'sender')}</span><span><i style="background:#c62828"></i>${L('প্রাপক', 'recipient')}</span>
          <span><i style="background:#7b8bb0"></i>${L('অন্য প্রেরক', 'payer')}</span><span><i style="background:#e07a10"></i>${L('এজেন্ট', 'agent')}</span><span><i style="background:#7b3fb3"></i>${L('একই ফোন', 'shared phone')}</span>
          <span><i style="background:#b23b3b"></i>${L('সাজানো প্রতারণার ভূমিকা', 'planted fraud role')}</span><span><i style="background:#fff;border:2px solid #c62828"></i>${L('১৬২৬৮-এ অভিযোগ', 'reported to 16268')}</span><span>🔒 ${L('স্থগিত', 'frozen')}</span></div></div>
      </div>`;
  }

  function report(d) {
    const rep = d.report;
    return `<div class="panel report">
        <div class="row" style="flex-wrap:wrap"><h3 style="margin:0">${L('কেস রিপোর্ট', 'Case report')}</h3><span class="aiflag">${P.esc(rep.generated_by)} · ${L('শুধু উপরের প্রমাণ থেকে তৈরি', 'built only from the evidence above')}</span>
          <span class="grow"></span>${S.health && S.health.llm === 'anthropic' && d.kind !== 'complaint' ? `<button class="btn-link" id="llm">${L('Claude দিয়ে ভাষা ঘষামাজা', 'Rewrite wording with Claude')}</button>` : ''}</div>
        ${P.lang === 'bn' ? '<div class="small muted" style="margin-top:4px">রিপোর্টটি ইংরেজিতে, অডিট রেকর্ডের ভাষা।</div>' : ''}
        <h4>1. What happened</h4><ul>${rep.what_happened.map((x) => `<li>${P.esc(x)}</li>`).join('')}</ul>
        <h4>2. ${d.kind === 'complaint' ? 'What kind of case' : 'Why it is risky'}</h4><ul>${rep.why_risky.map((x) => `<li>${P.esc(x)}</li>`).join('')}</ul>
        <h4>3. Recommended action (rules pick from a fixed list; you decide)</h4><ul>${rep.recommended_action.map((x) => `<li>${P.esc(x)}</li>`).join('')}</ul>
        <h4>4. Confidence and limits</h4><ul>${rep.confidence_limits.map((x) => `<li>${P.esc(x)}</li>`).join('')}</ul>
      </div>`;
  }

  const COMPLAINT_ONLY = ['HOLD_DISPUTED_AMOUNT', 'ASK_RECIPIENT_CONSENT', 'ASK_CUSTOMER_DETAILS'];
  function decide(d) {
    const rep = d.report;
    const rec = new Set(rep.actions);
    const labels = rep.action_labels;
    const fits = (k) => (d.kind === 'complaint' ? !['RELEASE_TRANSACTION', 'VERIFY_OWNER', 'REVIEW_AGENT'].includes(k)
      : d.kind === 'recharge' ? ['VERIFY_OWNER', 'WATCHLIST', 'DISMISS'].includes(k) : !COMPLAINT_ONLY.includes(k));
    const order = [...rep.actions, ...Object.keys(labels).filter((k) => !rec.has(k) && fits(k))];
    const can = (k) => !(k === 'RELEASE_TRANSACTION' && !(d.source === 'live' && d.status === 'held_for_review'));
    return `<div class="panel">
        <h3>${L('সিদ্ধান্ত নিন', 'Decide')}</h3>
        <div class="actions" id="acts">${order.map((k) => `<button data-act="${k}" class="${rec.has(k) ? 'rec' : ''} ${k === 'DISMISS' ? 'warn' : ''}" ${can(k) ? '' : 'disabled'} title="${P.esc(L(labels[k].en, labels[k].bn))}">${P.esc(L(labels[k].bn, labels[k].en))}</button>`).join('')}</div>
        <input class="field" id="note" placeholder="${L('অডিট লগের জন্য নোট (বাতিল করতে আবশ্যক)', 'Note for the audit log (required to dismiss)')}" style="margin-top:10px;font-size:14px;padding:9px">
        <div class="small muted" style="margin-top:6px">${d.frozen_recipient ? L('🔒 প্রাপক স্থগিত: নতুন যেকোনো লেনদেন আটকে যাবে। ', '🔒 The recipient is frozen: any new transfer to it is held. ') : ''}${d.hold_amount ? L(`আটকানোর অনুরোধ: ${P.tk(d.hold_amount)}। `, `Hold requested: ${P.tk(d.hold_amount)}. `) : ''}${L('প্রতিটি পদক্ষেপ আপনার নামে লগ হয়।', 'Every action is logged with your name.')}</div>
        <h3 style="margin-top:14px">${L('এই অ্যালার্টের ট্রেইল', 'Trail for this alert')}</h3>
        <div class="audit">${d.audit.map((e) => `<div>${P.esc(e.at.slice(11, 19))} · <b>${P.esc(e.actor)}</b> (${P.esc(e.role)}) ${P.esc(e.action)} ${e.detail && e.detail.note ? `· “${P.esc(e.detail.note)}”` : ''} <span class="muted">#${P.esc(e.hash.slice(0, 10))}</span></div>`).join('') || `<div class="muted">${L('ঐতিহাসিক কেস: অফলাইনে স্কোর করা, লাইভ ট্রেইল নেই।', 'Historical case: scored offline, no live trail.')}</div>`}</div>
      </div>`;
  }

  function wire(d) {
    const llm = $('llm');
    if (llm) llm.addEventListener('click', () => select(d.id, true));
    $('acts').addEventListener('click', async (e) => {
      const b = e.target.closest('[data-act]');
      if (!b) return;
      const analyst = $('analyst').value.trim();
      if (!analyst) { $('analyst').focus(); alert(L('আগে আপনার নাম লিখুন: প্রতিটি পদক্ষেপ একজন মানুষ অনুমোদন করেন।', 'Enter your name first: a person approves every action.')); return; }
      try {
        await P.api(`/api/v1/alerts/${d.id}/action`, { method: 'POST', body: { action: b.dataset.act, analyst, note: $('note').value } });
        await select(d.id);
        poll();
      } catch (err) { alert(err.message); }
    });
  }

  function renderDetail(d) {
    if (d.kind === 'complaint') { renderComplaint(d); return; }
    if (d.kind === 'recharge') { renderRecharge(d); return; }
    const choice = d.customer_choice ? (CHOICE[d.customer_choice] ? L(...CHOICE[d.customer_choice]) : d.customer_choice)
      : (d.source === 'live' ? L('এখনো উত্তর দেননি', 'no answer yet') : '—');
    $('detail').innerHTML = `
      <div class="panel">
        ${header(d)}
        <div class="kv" style="margin-top:10px">
          <div><span>${L('ঝুঁকি স্কোর', 'Risk score')}</span><b class="num">${d.risk_score}/100</b></div>
          <div><span>${L('প্রতারণার সম্ভাবনা (ক্যালিব্রেটেড)', 'Fraud probability (calibrated)')}</span><b class="num">${Math.round(100 * d.p_fraud_calibrated)}%</b></div>
          <div><span>${L('আচরণগত অস্বাভাবিকতা (পার্সেন্টাইল)', 'Behaviour anomaly (percentile)')}</span><b class="num">${Math.round(100 * d.anomaly)}%</b></div>
          <div><span>${L('গ্রাফ-নিয়ম স্কোর', 'Graph-rule score')}</span><b class="num">${(+d.graph).toFixed(2)}</b></div>
          <div><span>${L('সময়', 'When')}</span><b class="num">${P.esc(String(d.created).replace('T', ' '))}</b></div>
          <div><span>${L('অবস্থা', 'Status')}</span><b>${P.esc(status(d.status))}</b></div>
          <div><span>${L('গ্রাহক', 'Customer')}</span><b>${P.esc(choice)}</b></div>
          <div><span>${L('অ্যালার্ট', 'Alert')}</span><b class="num">${P.esc(d.id)}</b></div>
        </div>
        <div class="gauge" style="margin-top:12px"><i style="left:calc(${Math.min(99.4, d.risk_score)}% - 2px)"></i></div>
        <div class="row small muted" style="justify-content:space-between"><span>ALLOW</span><span>NUDGE 30</span><span>STEP-UP 60</span><span>HOLD 80</span></div>
      </div>
      ${wrongNumberPanel(d.suggestion, d.typed, d.customer_choice ? choice : null)}
      ${habitPanel(d.habit)}
      ${evidence(d)}${report(d)}${decide(d)}`;
    wire(d);
  }

  function renderRecharge(d) {
    const rc = d.recharge;
    const choice = d.customer_choice ? (CHOICE[d.customer_choice] ? L(...CHOICE[d.customer_choice]) : d.customer_choice) : L('এখনো উত্তর দেননি', 'no answer yet');
    const whose = rc.own ? L('গ্রাহকের নিজের নম্বর', "the customer's own number") : rc.contact ? `${L('পরিচিত', 'contact')}: ${P.esc(rc.contact)}`
      : L('গ্রাহকের নয়, পরিচিত তালিকাতেও নেই', 'not theirs, not a saved contact');
    $('detail').innerHTML = `
      <div class="panel">
        <div class="row" style="flex-wrap:wrap;gap:10px">
          <span class="band band-${d.band}" style="font-size:14px">${d.band}</span><span class="chip">📱 ${L('মোবাইল রিচার্জ', 'Mobile recharge')}</span>
          <b style="font-size:20px" class="num">${P.tk(d.amount)}</b><span class="num">${P.esc(d.sender_id)} → ${P.esc(rc.number)}</span>
          <span class="chip">${P.esc(d.title || '')}</span></div>
        <div class="kv" style="margin-top:10px">
          <div><span>${L('কার নম্বর', 'Whose number')}</span><b>${whose}</b></div>
          <div><span>${L('সময়', 'When')}</span><b class="num">${P.esc(String(d.created).replace('T', ' '))}</b></div>
          <div><span>${L('গত এক ঘণ্টায় রিচার্জ', 'Recharges in the hour before')}</span><b class="num">${P.n(rc.recent.length)}</b></div>
          <div><span>${L('অবস্থা', 'Status')}</span><b>${P.esc(status(d.status))}</b></div>
          <div><span>${L('গ্রাহক', 'Customer')}</span><b>${P.esc(choice)}</b></div>
          <div><span>${L('মডেল', 'Model')}</span><b>${L('রিচার্জে প্রশিক্ষিত নয়: অভ্যাস + নিয়ম', 'not trained on recharges: habit + rule')}</b></div>
        </div>
        <ul style="margin:10px 0 0;padding-left:18px;font-size:13.5px;line-height:1.5">${d.reasons.map((r) => `<li>${P.esc(L(r.bn, r.en))}</li>`).join('')}</ul>
        ${rc.recent.length ? `<div class="small muted" style="margin-top:8px">${rc.recent.map((r) => `${P.esc(r.at.slice(11, 16))} ${P.tk(r.amount)} → ${P.esc(r.number)}${r.own ? L(' (নিজের)', ' (own)') : ''}`).join(' · ')}</div>` : ''}
      </div>
      ${habitPanel(d.habit)}${report(d)}${decide(d)}`;
    wire(d);
  }

  function renderComplaint(d) {
    const c = d.complaint;
    const e = c.extraction || {};
    const t = c.match.transfer;
    const read = [];
    if (e.amount) read.push(`${L('পরিমাণ', 'amount')} ${P.tk(e.amount)}`);
    if (e.number) read.push(`${L('নম্বর', 'number')} ${e.number}`); else if (e.number_last4) read.push(`${L('নম্বরের শেষ', 'number ending')} ${e.number_last4}`);
    if (e.day_offset != null) read.push(({ 0: L('আজ', 'today'), 1: L('গতকাল', 'yesterday') })[e.day_offset] || L(`${P.bn(e.day_offset)} দিন আগে`, `${e.day_offset} days ago`));
    if (e.hour != null) read.push(`${L('প্রায়', 'about')} ${String(e.hour).padStart(2, '0')}:00`);
    if (e.trx_id) read.push(`TrxID ${e.trx_id}`);
    const cues = Object.entries(e.cues || {}).filter(([, v]) => v).map(([k]) => k);
    const PROB = { wrong_number: ['ভুল নম্বরে পাঠানো', 'wrong number'], scam: ['প্রতারণা', 'scam'], other: ['অন্য', 'other'] };
    const LANG = { bn: 'বাংলা / Bangla', banglish: 'Banglish', en: 'English', mixed: 'mixed' };
    $('detail').innerHTML = `
      <div class="panel">
        ${header(d, `<span class="chip">${P.esc(c.case_label)}</span><span class="chip">${L('শেষ তারিখ', 'Due')} <b class="num">${P.esc(c.deadline)}</b></span>`)}
        <div class="kv" style="margin-top:10px">
          <div><span>${L('জমা', 'Filed')}</span><b class="num">${P.esc(String(c.filed_at).replace('T', ' ').slice(0, 16))}</b></div>
          <div><span>${L('ভাষা', 'Language')}</span><b>${P.esc(LANG[c.language] || c.language)}</b></div>
          <div><span>${L('সমস্যা', 'Problem')}</span><b>${P.esc(L(...(PROB[c.problem] || [c.problem, c.problem])))}</b></div>
          <div><span>${L('লেনদেন মেলানো', 'Transfer match')}</span><b>${t ? `${P.esc(t.id)} · ${P.esc(c.match.how)} (${c.match.confidence})` : L('পাওয়া যায়নি', 'not found')}</b></div>
          <div><span>${L('প্রাপকের ব্যালেন্স এখন', 'Recipient balance now')}</span><b class="num">${P.tk(c.recipient_balance)}</b></div>
          <div><span>${L('এখনো আটকানো যায়', 'Can still be held')}</span><b class="num">${P.tk(c.holdable)}</b></div>
          <div><span>${L('প্রাপক সম্পর্কে মডেল', 'Model view of recipient')}</span><b class="num">${c.probe_band ? `${d.risk_score}/100 ${c.probe_band}` : '—'}</b></div>
          <div><span>${L('অবস্থা', 'Status')}</span><b>${P.esc(status(d.status))}</b></div>
        </div>
      </div>
      <div class="panel"><h3>${L('গ্রাহকের নিজের ভাষায়', "The customer's own words")}</h3>
        <blockquote class="words">${P.esc(c.text)}</blockquote>
        <div class="small muted" style="margin-top:8px">${L('নিয়ম দিয়ে পড়া (কোনো ভাষা মডেল নয়)', 'Read by rules (no language model)')}:</div>
        <div class="understood">${read.map((x) => `<span class="chip">${P.esc(x)}</span>`).join('') || `<span class="muted small">${L('নির্দিষ্ট কিছু নেই', 'nothing specific')}</span>`}
          ${cues.map((x) => `<span class="chip" style="background:#fff4e5;border-color:#f3d58c">${P.esc(x)}</span>`).join('')}</div>
        ${t ? `<div class="small" style="margin-top:8px"><b>${L('মিলে যাওয়া লেনদেন', 'Matched transfer')}:</b> <span class="num">${P.esc(t.id)} · ${P.tk(t.amount)} → ${P.esc(t.number)} · ${P.esc(String(t.at).replace('T', ' ').slice(0, 16))}</span></div>` : ''}
      </div>
      ${wrongNumberPanel(c.slip, c.slip && c.slip.typed, null)}
      ${evidence(d)}${report(d)}${decide(d)}`;
    wire(d);
  }

  function shapBars(list) {
    if (!list || !list.length) return `<div class="muted small">${L('কোনো ফিচার-ভিত্তিক ব্যাখ্যা নেই।', 'No per-feature attribution stored.')}</div>`;
    const max = Math.max(...list.map((s) => Math.abs(s.shap)), 1e-9);
    return list.slice(0, 9).map((s) => {
      const w = Math.round((Math.abs(s.shap) / max) * 50);
      const pos = s.shap >= 0;
      const val = s.value === null || s.value === undefined ? '—' : (typeof s.value === 'number' ? (+s.value.toFixed(2)).toString() : String(s.value));
      return `<div class="shapbar"><span title="${P.esc(s.feature)}">${P.esc(s.label || s.feature)} <span class="muted num">= ${P.esc(val)}</span></span>
        <div class="bar"><i style="${pos ? 'left:50%' : `right:50%`};width:${w}%;background:${pos ? '#c62828' : '#0f8a5f'}"></i><i style="left:50%;width:1px;background:#9aa4b5"></i></div>
        <span class="num small" style="text-align:right;color:${pos ? '#c62828' : '#0f8a5f'}">${pos ? '+' : ''}${s.shap.toFixed(2)}</span></div>`;
    }).join('') + `<div class="small muted" style="margin-top:4px">${L('লাল প্রতারণার দিকে ঠেলে, সবুজ উল্টো দিকে (log-odds)।', 'Red pushes towards fraud, green away (log-odds contribution).')}</div>`;
  }

  // ---------------------------------------------------------------- network drawing (no library)
  function drawNetwork(net, d) {
    if (!net || !net.nodes.length) return `<div class="muted small">${L('কোনো নেটওয়ার্ক নেই।', 'No network stored.')}</div>`;
    const N = new Map(net.nodes.map((n) => [n.id, { ...n }]));
    const E = net.edges;
    const Lv = new Map();
    Lv.set(d.receiver_id, 2);
    E.forEach((e) => { if (e.target === d.receiver_id && e.source !== d.receiver_id) Lv.set(e.source, 1); });
    E.forEach((e) => { if (e.source === d.receiver_id && !Lv.has(e.target)) Lv.set(e.target, 3); });
    N.forEach((n) => { if (n.kind === 'device') Lv.set(n.id, 0); });
    for (let pass = 0; pass < 6; pass++) {
      E.forEach((e) => {
        if (Lv.has(e.source) && !Lv.has(e.target)) Lv.set(e.target, Math.min(4, Lv.get(e.source) + 1));
        if (Lv.has(e.target) && !Lv.has(e.source)) Lv.set(e.source, Math.max(0, Lv.get(e.target) - 1));
      });
    }
    N.forEach((n) => { if (!Lv.has(n.id)) Lv.set(n.id, 1); });
    const cols = [...new Set([...Lv.values()])].sort((a, b) => a - b);
    const byCol = cols.map((c) => [...N.values()].filter((n) => Lv.get(n.id) === c));
    const pri = { sender: 0, victim: 0, device: 1, payer: 2, recipient: 0, agent: 3 };
    byCol.forEach((col) => col.sort((a, b) => (pri[a.role] ?? 2) - (pri[b.role] ?? 2) || String(a.id).localeCompare(String(b.id))));
    const W = 640, maxN = Math.max(...byCol.map((c) => c.length)), H = Math.max(280, maxN * 40 + 40);
    const pos = new Map();
    byCol.forEach((col, ci) => {
      const x = cols.length === 1 ? W / 2 : 60 + (ci * (W - 120)) / (cols.length - 1);
      col.forEach((n, i) => pos.set(n.id, [x, (H / (col.length + 1)) * (i + 1)]));
    });
    const colorOf = (n) => (n.kind === 'device' ? '#7b3fb3' : n.id === d.sender_id ? '#005bac' : n.id === d.receiver_id ? '#c62828'
      : n.kind === 'agent' ? '#e07a10' : n.role === 'payer' ? '#7b8bb0' : /mule|collector|seller|fraud|takeover/.test(n.role) ? '#b23b3b' : '#97a3b8');
    let edges = '';
    E.forEach((e) => {
      const a = pos.get(e.source), b = pos.get(e.target);
      if (!a || !b) return;
      const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2 - (a[1] === b[1] ? 22 : 0);
      let stroke = '#a7b2c6', dash = '', w = e.amount ? Math.max(1, Math.min(5, Math.log10(e.amount) - 1.5)) : 1;
      if (e.type === 'CASH_OUT') stroke = '#e07a10';
      if (e.type === 'DEVICE') { stroke = '#7b3fb3'; dash = '2 4'; w = 1.2; }
      if (e.key) { stroke = e.status === 'sent' ? '#0f8a5f' : e.status === 'cancelled' ? '#97a3b8' : '#c62828'; dash = e.attempt && e.status !== 'sent' ? '7 5' : ''; w = 3; }
      const tip = `${e.source} → ${e.target}${e.amount ? ` · Tk ${Number(e.amount).toLocaleString('en-US')}` : ''} · ${e.type}${e.attempt ? ` · ${e.status}` : ''}`;
      edges += `<path d="M${a[0]},${a[1]} Q${mx},${my} ${b[0]},${b[1]}" fill="none" stroke="${stroke}" stroke-width="${w}" stroke-dasharray="${dash}" marker-end="url(#arr)" opacity="${e.key ? 1 : 0.75}"><title>${P.esc(tip)}</title></path>`;
    });
    let nodes = '';
    N.forEach((n) => {
      const [x, y] = pos.get(n.id);
      const c = colorOf(n);
      const big = n.id === d.receiver_id || n.id === d.sender_id;
      const r = big ? 11 : 7;
      const ring = n.reported ? 'stroke="#c62828" stroke-width="3"' : 'stroke="#fff" stroke-width="1.5"';
      const shape = n.kind === 'agent' ? `<rect x="${x - r}" y="${y - r}" width="${2 * r}" height="${2 * r}" rx="3" fill="${c}" ${ring}/>`
        : n.kind === 'device' ? `<path d="M${x},${y - r - 2} L${x + r + 2},${y} L${x},${y + r + 2} L${x - r - 2},${y} Z" fill="${c}" ${ring}/>`
          : `<circle cx="${x}" cy="${y}" r="${r}" fill="${c}" ${ring}/>`;
      const label = n.kind === 'customer' ? `…${String(n.id).slice(-4)}` : n.id;
      const sub = [n.role !== 'other' ? n.role : '', n.age_days !== null && n.age_days !== undefined && n.kind === 'customer' && n.age_days < 120 ? `${Math.round(n.age_days)}d old` : ''].filter(Boolean).join(' · ');
      nodes += `<g>${shape}<title>${P.esc(`${n.id} · ${n.kind} · ${n.role}${n.age_days != null ? ` · opened ${n.age_days} days before` : ''}${n.reported ? ' · reported' : ''}`)}</title>
        <text x="${x}" y="${y + r + 12}" text-anchor="middle" font-size="10.5" fill="#33405a" font-family="ui-monospace,Consolas,monospace">${P.esc(label)}${n.frozen ? ' 🔒' : ''}</text>
        ${sub && (big || n.kind !== 'customer' || byCol[cols.indexOf(Lv.get(n.id))].length <= 6) ? `<text x="${x}" y="${y + r + 23}" text-anchor="middle" font-size="9.5" fill="#7b8597">${P.esc(sub)}</text>` : ''}</g>`;
    });
    return `<svg viewBox="0 0 ${W} ${H + 20}" role="img" aria-label="Money network around the alert">
      <defs><marker id="arr" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#7d889c"/></marker></defs>
      ${edges}${nodes}</svg>`;
  }

  // ---------------------------------------------------------------- Agent Watch
  async function loadAgents() {
    const a = await P.api('/api/v1/agent-watch');
    const thr = a.threshold;
    const spark = (series) => {
      const W = 220, H = 40, n = series.length;
      if (!n) return '';
      const x = (i) => 4 + (i * (W - 8)) / Math.max(n - 1, 1);
      const y = (v) => H - 4 - (v / 100) * (H - 8);
      const line = series.map((p, i) => `${i ? 'L' : 'M'}${x(i)},${y(p.score)}`).join(' ');
      const dots = series.map((p, i) => (p.flagged ? `<circle cx="${x(i)}" cy="${y(p.score)}" r="3" fill="#c62828"/>` : '')).join('');
      const ep = series.map((p, i) => (p.is_episode ? `<rect x="${x(i) - 4}" y="0" width="8" height="${H}" fill="#ffe6c4" opacity=".7"/>` : '')).join('');
      return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">${ep}${thr != null ? `<line x1="0" x2="${W}" y1="${y(thr)}" y2="${y(thr)}" stroke="#c9d1df" stroke-dasharray="3 3"/>` : ''}<path d="${line}" fill="none" stroke="#005bac" stroke-width="1.6"/>${dots}</svg>`;
    };
    const rows = Object.entries(a.series).map(([id, s]) => {
      const mx = Math.max(...s.map((p) => p.score));
      const vr = Math.max(...s.map((p) => p.volume_ratio));
      const fl = s.filter((p) => p.flagged).map((p) => p.day + 1);
      return `<tr><td class="num"><b>${P.esc(id)}</b>${id === a.staged_agent ? ` <span class="chip">${L('লাইভ ডেমো ক্যাশ-আউট', 'live demo cash-outs')}</span>` : ''}</td><td>${P.esc(a.area[id] || '')}</td>
        <td>${spark(s)}</td><td class="num">${mx.toFixed(1)}</td><td class="num">${vr.toFixed(1)}×</td><td class="num">${fl.length ? fl.join(', ') : '—'}</td></tr>`;
    }).join('');
    const sc = a.sc06 || {};
    const rc = a.register_compromise || {};
    $('agents').innerHTML = `<h3>${L('এজেন্ট ওয়াচ: অসৎ ক্যাশ-আউট এজেন্ট (সহকর্মীদের সাথে তুলনা, প্রশিক্ষিত মডেল নয়)', 'Agent Watch: rogue cash-out agents (peer z-scores, not a trained model)')}</h3>
      <p class="small muted" style="margin-top:0">${L('ডেটায় মাত্র ৯টি অসৎ এজেন্ট, তাই সুপারভাইজড মডেল ৯টি উদাহরণ শিখত। এজেন্ট ওয়াচ প্রতিটি এজেন্টকে একই এলাকার অন্যদের সাথে তুলনা করে: পরিমাণ, রাতের অংশ, নতুন ওয়ালেটের অংশ, পাস-থ্রু অংশ, আগে অভিযোগ হওয়া অংশ। ছায়া দেওয়া দিন = সিন্থেটিক সত্যে অসৎ পর্ব; লাল বিন্দু = চিহ্নিত দিন।',
        'With only 9 rogue agents in the data, a supervised model would learn 9 examples. Agent Watch compares each agent with peers in its area: volume, night share, young-wallet share, pass-through share and share already reported. Shaded days = rogue episodes in the synthetic ground truth; red dots = days flagged (score above the dashed threshold).')}</p>
      <div class="kv" style="margin-bottom:12px">
        <div><span>${L('সাজানো কেস SC-06', 'Planted case SC-06')}</span><b>${P.esc(sc.agent || '—')}</b></div><div><span>${L('সর্বোচ্চ স্কোর', 'Max score')}</span><b class="num">${sc.max_score ?? '—'}</b></div>
        <div><span>${L('এলাকার মিডিয়ানের তুলনায় পরিমাণ', 'Volume vs area median')}</span><b class="num">${sc.max_volume_vs_peer_median ?? '—'}×</b></div>
        <div><span>${L('চিহ্নিত দিন', 'Flagged days')}</span><b class="num">${(sc.flagged_days || []).join(', ') || '—'}</b></div>
        <div><span>${L('রেজিস্টার-চুরি পরীক্ষা', 'Register-compromise test')}</span><b class="num">${rc.harvested_flagged ?? '—'} / ${rc.harvested_agents ?? '—'} ${L('চিহ্নিত', 'harvested agents flagged')}, ${rc.other_agents_flagged ?? '—'} ${L('অন্য', 'other')}</b></div>
        <div><span>${L('টেস্ট পর্ব ধরা পড়েছে', 'Test episodes caught')}</span><b class="num">${(a.by_split || {}).test ? `${a.by_split.test.episodes_flagged} / ${a.by_split.test.episodes}` : '—'}</b></div>
        <div><span>${L('প্রতিদিন ভুল সতর্কতা (এজেন্ট-দিন)', 'False-alarm agent-days per day')}</span><b class="num">${(a.by_split || {}).test ? a.by_split.test.false_alarm_agent_days_per_day : '—'}</b></div></div>
      ${tbl([L('এজেন্ট', 'Agent'), L('এলাকা', 'Area'), L('দৈনিক স্কোর, টেস্ট উইন্ডো', 'Daily score, test window'), L('সর্বোচ্চ', 'Max'), L('সর্বোচ্চ পরিমাণ বনাম সহকর্মী', 'Max volume vs peers'), L('চিহ্নিত দিন', 'Flagged days')], rows)}`;
  }

  // ---------------------------------------------------------------- model card
  async function loadModel() {
    const m = await P.api('/api/v1/model');
    S.model = m;
    const fedRow = ((m.federated || {}).crosssilo || {}).comparison;
    const comp = [...(m.comparison || []), ...(fedRow ? fedRow.filter((r) => /federated/.test(r.model)) : [])]
      .map((r) => `<tr style="${/federated/.test(r.model) ? 'background:#eef5fc' : ''}"><td>${P.esc(r.model)}</td><td class="num">${r.pr_auc?.toFixed(3)}</td><td class="num">${r.roc_auc?.toFixed(3)}</td>
      <td class="num">${pct(r.recall_at_fpr_0p5)}</td><td class="num">${pct(r.recall_at_fpr_2)}</td></tr>`).join('');
    const bands = Object.entries(m.bands || {}).filter(([k]) => k !== 'band_counts').map(([k, v]) => `<tr><td>${k}</td><td class="num">${v.alerts}</td>
      <td class="num">${pct(v.precision)}</td><td class="num">${pct(v.recall)}</td><td class="num">${pct(v.fpr)}</td></tr>`).join('');
    const im = m.impact || {}, fr = m.friction || {};
    const fair = (m.fairness || []).map((r) => `<tr style="${r.flag ? 'background:#fff4e5' : ''}"><td>${P.esc(r.attribute)}</td><td>${P.esc(r.group)}</td>
      <td class="num">${r.legit_txns}</td><td class="num">${pct(r.fpr_nudge)}</td><td class="num">${r.fpr_nudge_ratio}×</td><td class="num">${pct(r.fpr_stepup)}</td><td class="num">${r.fpr_stepup_ratio}×</td><td>${r.flag ? L('নজরে রাখুন', 'watch') : ''}</td></tr>`).join('');
    const demo = (m.demo || []).map((r) => `<tr><td>${P.esc(r.id)}</td><td>${P.esc(r.title)}</td><td>${P.esc(r.expected)}</td><td><span class="band band-${r.actual === 'FLAGGED' ? 'HOLD' : r.actual}">${P.esc(r.actual)}</span></td><td class="num">${r.risk_score}</td></tr>`).join('');
    $('model').innerHTML = `<h3>${L('আলাদা রাখা টেস্ট উইন্ডো (দিন ৫১–৬০, প্রশিক্ষণ বা টিউনিং-এ কখনো ব্যবহার হয়নি) · সিন্থেটিক ডেটা, ঊর্ধ্বসীমা হিসেবে পড়ুন', 'Held-out test window (days 51–60, never used for training or tuning) · synthetic data, read as upper bounds')}</h3>
      <div class="kv" style="margin-bottom:12px">
        <div><span>${L('রক্ষা পাওয়া ভুক্তভোগীর টাকা (ঘোষিত অনুমানে)', 'Victim money protected (stated stop-rate assumptions)')}</span><b class="num">${pct(im.expected_prevented_share)}</b></div>
        <div><span>${L('STEP-UP+ পাওয়া প্রতারণার লেনদেন', 'Victim-side scam transfers flagged STEP-UP+')}</span><b class="num">${pct(im.victim_side_recall_stepup)}</b></div>
        <div><span>${L('কোনো বাধা ছাড়া সৎ লেনদেন', 'Honest transactions with no friction')}</span><b class="num">${pct((fr.legit_txn_share_by_band || {}).ALLOW)}</b></div>
        <div><span>${L('বিশ্লেষকের ঘণ্টা, ১০ দিন: হাতে → কোপাইলটে', 'Analyst hours, 10 days: manual → with copilot')}</span><b class="num">${fr.analyst_hours_manual} → ${fr.analyst_hours_with_copilot}</b></div></div>
      <div class="two"><div><h3>${L('মডেল তুলনা', 'Model comparison')}</h3>${tbl([L('মডেল', 'Model'), 'PR-AUC', 'ROC-AUC', L('রিকল @০.৫% FPR', 'Recall @0.5% FPR'), L('রিকল @২% FPR', 'Recall @2% FPR')], comp)}
        ${fedRow ? `<div class="small muted" style="margin-top:4px">${L('নীল সারি: ৮টি বিভাগে ফেডারেটেড প্রশিক্ষণ, লেনদেন এক জায়গায় না এনে। বিস্তারিত “ফেডারেটেড ও গোপনীয়তা” ট্যাবে।', 'Blue row: trained federated across 8 divisions without pooling transactions. Details in the “Federated & privacy” tab.')}</div>` : ''}
        <h3 style="margin-top:14px">${L('নীতির অপারেটিং পয়েন্ট', 'Policy operating points')}</h3>${tbl([L('যে ব্যান্ডে পৌঁছেছে', 'Band reached'), L('অ্যালার্ট', 'Alerts'), 'Precision', 'Recall', L('ভুল-পজিটিভ হার', 'False-positive rate')], bands)}</div>
      <div><h3>${L('সাজানো ডেমো পরিস্থিতি (অদেখা টেস্ট ডেটা)', 'Planted demo scenarios (unseen test data)')}</h3>${tbl(['ID', L('পরিস্থিতি', 'Scenario'), L('প্রত্যাশিত', 'Expected'), L('ফলাফল', 'Actual'), L('স্কোর', 'Score')], demo)}</div></div>
      <h3 style="margin-top:14px">${L('ন্যায্যতা: গোষ্ঠীভিত্তিক ভুল-পজিটিভ হার (এই বৈশিষ্ট্যগুলো কখনো মডেলের ইনপুট নয়)', 'Fairness: false-positive rates by group (attributes are never model inputs)')}</h3>
      ${tbl([L('বৈশিষ্ট্য', 'Attribute'), L('গোষ্ঠী', 'Group'), L('সৎ লেনদেন', 'Honest txns'), 'FPR NUDGE+', L('সামগ্রিকের তুলনায়', 'vs overall'), 'FPR STEP-UP+', L('সামগ্রিকের তুলনায়', 'vs overall'), ''], fair)}`;
  }

  // ---------------------------------------------------------------- federated learning & privacy
  async function loadFL() {
    const m = S.model || await P.api('/api/v1/model');
    S.model = m;
    const f = m.federated || {};
    const od = f.ondevice, cs = f.crosssilo, costs = f.slip_costs;
    let html = `<h3>${L('ফেডারেটেড লার্নিং: ডেটা যেখানে আছে সেখানেই থাকে', 'Federated learning: the data stays where it is')}</h3>
      <p class="small muted" style="margin-top:0">${L('প্রহরী দুই জায়গায় কাঁচা ডেটা এক জায়গায় না এনে শেখে: গ্রাহকের ফোনে (কোন ডিজিট ভুল টাইপ হয়) এবং upay-এর বিভাগগুলোর মধ্যে (প্রতারণা শনাক্তের মডেল)। দুটোই সিমুলেশন, সিন্থেটিক ডেটায়; প্রোটোকল ও হিসাব আসল।',
      'Prohori learns in two places without collecting raw data: on customers\' phones (which digits get mistyped) and across upay\'s divisions (the scam model). Both are simulations on synthetic data; the protocols and the arithmetic are real.')}</p>`;
    if (od) {
      const lc = od.local_noise_comparison || {};
      const hist = od.history || [];
      const maxE = Math.max(...hist.map((h) => h.l1_error), 0.01);
      const bars = hist.map((h, i) => `<rect x="${10 + i * 34}" y="${70 - (h.l1_error / maxE) * 60}" width="24" height="${(h.l1_error / maxE) * 60}" fill="#005bac" rx="3"><title>round ${h.round}: L1 ${h.l1_error}</title></rect>
        <text x="${22 + i * 34}" y="84" font-size="10" text-anchor="middle" fill="#7b8597">${h.round}</text>
        <text x="${22 + i * 34}" y="${66 - (h.l1_error / maxE) * 60}" font-size="9" text-anchor="middle" fill="#33405a">${h.l1_error.toFixed(3).slice(1)}</text>`).join('');
      const cmpMax = Math.max(od.final_l1_error, lc.final_l1_error || 0, 0.01);
      const cmpBar = (label, v, color) => `<div class="flbar"><span>${label}</span><div class="bar"><i style="width:${(100 * v / cmpMax).toFixed(1)}%;background:${color}"></i></div><b class="num">${v}</b></div>`;
      html += `<div class="panel" style="margin-top:10px"><h3>① ${L('ফোনে: কোন ডিজিট মানুষ ভুল টাইপ করে (অন-ডিভাইস)', 'On the phone: which digits people mistype (on-device)')}</h3>
        <div class="kv" style="margin-bottom:10px">
          <div><span>${L('ফোন (সিমুলেটেড)', 'Phones (simulated)')}</span><b class="num">${od.phones.toLocaleString('en-US')}</b></div>
          <div><span>${L('রাউন্ড', 'Rounds')}</span><b class="num">${od.rounds} · ${Math.round(100 * od.online_per_round)}% ${L('অনলাইন', 'online')}</b></div>
          <div><span>${L('গোপনীয়তা', 'Privacy')}</span><b class="num">ε ${od.epsilon_total} (δ 10⁻⁵)</b></div>
          <div><span>${L('আসল ভুলের ধরন থেকে ত্রুটি (L1)', 'Error vs true slip pattern (L1)')}</span><b class="num">${od.final_l1_error}</b></div>
          <div><span>${L('শুধু লোকাল নয়েজে একই ε-তে', 'Local noise only, same ε')}</span><b class="num">${lc.final_l1_error ?? '—'}</b></div>
          <div><span>${L('শেখা: পাশের বোতাম / অন্য বোতাম', 'Learned cost: neighbour key / other key')}</span><b class="num">${od.neighbour_cost_mean} / ${od.other_cost_mean}</b></div>
          <div><span>${L('দুই ডিজিট উল্টে যাওয়া', 'Swapped digits, share of slips')}</span><b class="num">${Math.round(100 * od.learned_swap_share)}% (${L('আসল', 'true')} ${Math.round(100 * od.true_swap_share)}%)</b></div></div>
        <div class="two"><div>
          <div class="small muted">${L(`একই ε (${od.epsilon_total})-তে আসল ভুলের ধরন থেকে ত্রুটি, কম হলে ভালো`, `Error vs the true slip pattern at the same ε (${od.epsilon_total}); lower is better`)}</div>
          ${cmpBar(L('সিকিউর অ্যাগ্রিগেশন + বিতরণকৃত নয়েজ (ব্যবহৃত)', 'Secure aggregation + distributed noise (used)'), od.final_l1_error, '#0f8a5f')}
          ${lc.final_l1_error != null ? cmpBar(L('শুধু লোকাল নয়েজ (সার্ভারে কোনো আস্থা ছাড়া)', 'Local noise only (no trust in the server)'), lc.final_l1_error, '#c2570c') : ''}
          <div class="small muted" style="margin-top:8px">${L('প্রতি রাউন্ডে ত্রুটি (ব্যবহৃত পদ্ধতি)', 'Error after each round (method used)')}</div>
          <svg viewBox="0 0 ${20 + hist.length * 34} 90" style="max-width:300px;width:100%">${bars}</svg>
          <ul class="small" style="padding-left:18px;line-height:1.55">
            <li><b>${L('ফোন থেকে যায়', 'Leaves the phone')}:</b> ${L('প্রতি রাউন্ডে ১০১টি সংখ্যার একটি নয়েজ মেশানো, মাস্ক করা গণনা।', 'one noisy, masked vector of 101 counts per round.')}</li>
            <li><b>${L('কখনো যায় না', 'Never leaves')}:</b> ${L('পরিচিত নম্বর, টাইপ করা নম্বর, কোন ভুল হয়েছিল।', 'contacts, numbers typed, the slips themselves.')}</li>
            <li><b>${L('সার্ভার দেখে', 'The server sees')}:</b> ${L(`শুধু ${P.n(od.group_size)}টি ফোনের যোগফল (সিকিউর অ্যাগ্রিগেশন; মাস্ক যোগফলে কেটে যায়)।`, `only sums over ${od.group_size} phones (secure aggregation: the masks cancel in the sum).`)}</li>
            <li><b>${L('লাইভ ব্যবহার', 'Used live')}:</b> ${L('এই খরচগুলোই “আপনি কি মা-কে পাঠাতে চেয়েছিলেন?” যাচাই চালায়।', 'these costs drive the “Did you mean মা?” check.')} <span class="muted">${P.esc(costs ? costs.source : '')}</span></li>
          </ul></div>
          <div>${costs ? heatmap(costs) : ''}</div></div>
        <div class="small muted">${P.esc(od.method)}</div></div>`;
    }
    if (cs) {
      const silos = (cs.silos || []).map((s) => `<tr><td>${P.esc(s.name)}</td><td class="num">${s.train_rows.toLocaleString('en-US')}</td><td class="num">${s.train_fraud}</td></tr>`).join('');
      const comp = (cs.comparison || []).map((r) => `<tr style="${/federated/.test(r.model) ? 'background:#eef5fc' : ''}"><td>${P.esc(r.model)}</td><td class="num">${r.pr_auc.toFixed(3)}</td><td class="num">${r.roc_auc.toFixed(4)}</td>
        <td class="num">${pct(r.recall_at_fpr_0p1)}</td><td class="num">${pct(r.recall_at_fpr_0p5)}</td><td class="num">${pct(r.recall_at_fpr_2)}</td></tr>`).join('');
      const bandRows = ['NUDGE+', 'STEP_UP+', 'HOLD+'].map((b) => {
        const c = (cs.bands || {}).central?.[b] || {}, fd = (cs.bands || {}).federated?.[b] || {};
        return `<tr><td>${b}</td><td class="num">${pct(c.precision)} / ${pct(c.recall)}</td><td class="num">${pct(fd.precision)} / ${pct(fd.recall)}</td></tr>`;
      }).join('');
      const central = (cs.comparison || []).find((r) => !/federated/.test(r.model)), fed = (cs.comparison || []).find((r) => /federated/.test(r.model));
      const planted = (cs.planted || []).map((p) => `<span class="chip" title="${L('প্রত্যাশিত', 'expected')} ${P.esc(p.expected)}">${P.esc(p.id)} <span class="band band-${p.federated}">${P.esc(p.federated)}</span> ${p.ok ? '✓' : '✗'}</span>`).join(' ');
      html += `<div class="panel" style="margin-top:10px"><h3>② ${L('বিভাগগুলোর মধ্যে: লেনদেন এক জায়গায় না এনে প্রতারণার মডেল (ক্রস-সাইলো)', 'Across divisions: the scam model without pooling transactions (cross-silo)')}</h3>
        <div class="kv" style="margin-bottom:10px">
          <div><span>${L('সাইলো', 'Silos')}</span><b class="num">${(cs.silos || []).length} ${L('বিভাগ', 'divisions')}</b></div>
          <div><span>${L('গাছ', 'Trees')}</span><b class="num">${cs.trees} · depth ${cs.depth} · ${cs.bins} bins</b></div>
          <div><span>${L('কেন্দ্রীয় মডেলের তুলনায় PR-AUC', 'PR-AUC vs central model')}</span><b class="num">${fed && central ? `${fed.pr_auc.toFixed(3)} / ${central.pr_auc.toFixed(3)} (${Math.round(1000 * fed.pr_auc / central.pr_auc) / 10}%)` : '—'}</b></div>
          <div><span>${L('সাজানো পরিস্থিতি ঠিক ব্যান্ডে', 'Planted scenarios in an acceptable band')}</span><b class="num">${(cs.planted || []).filter((p) => p.ok).length} / ${(cs.planted || []).length}</b></div>
          <div><span>${L('LightGBM ফরম্যাটে রপ্তানি, পার্থক্য', 'Exported as LightGBM, max difference')}</span><b class="num">${Number(cs.export_gap).toExponential(1)}</b></div></div>
        <div class="two"><div><h3>${L('বিভাগ (সাইলো)', 'Divisions (silos)')}</h3>${tbl([L('বিভাগ', 'Division'), L('প্রশিক্ষণ সারি', 'Training rows'), L('প্রতারণা', 'Fraud')], silos)}</div>
          <div><h3>${L('টেস্ট উইন্ডোতে তুলনা', 'Test-window comparison')}</h3>${tbl([L('মডেল', 'Model'), 'PR-AUC', 'ROC-AUC', 'R@0.1%', 'R@0.5%', 'R@2%'], comp)}
            <h3 style="margin-top:12px">${L('ব্যান্ড: precision / recall', 'Bands: precision / recall')}</h3>${tbl([L('ব্যান্ড', 'Band'), L('কেন্দ্রীয়', 'Central'), L('ফেডারেটেড', 'Federated')], bandRows)}</div></div>
        <div style="margin-top:10px">${planted}</div>
        <div class="two" style="margin-top:10px">
          <div><b class="small">${L('সার্ভারের সাথে যা ভাগ হয়', 'Shared with the server')}</b><ul class="small" style="padding-left:18px">${(cs.shared_with_server || []).map((x) => `<li>${P.esc(x)}</li>`).join('')}</ul>
            <b class="small">${L('কখনো ভাগ হয় না', 'Never shared')}</b><ul class="small" style="padding-left:18px">${(cs.never_shared || []).map((x) => `<li>${P.esc(x)}</li>`).join('')}</ul></div>
          <div><b class="small">${L('সীমাবদ্ধতা', 'Limits')}</b><ul class="small" style="padding-left:18px">${(cs.limits || []).map((x) => `<li>${P.esc(x)}</li>`).join('')}</ul>
            <div class="small" style="margin-top:6px"><b>${L('লাইভে কোন মডেল', 'Serving')}:</b> ${S.health && S.health.scorer === 'federated'
              ? L('এই সার্ভার ফেডারেটেড মডেল চালাচ্ছে।', 'this server runs the federated model.')
              : L('কেন্দ্রীয় LightGBM (HOLD recall বেশি)। ফেডারেটেড মডেল সরাসরি বদলে বসানো যায়: PROHORI_SCORER=federated।', 'central LightGBM (higher HOLD recall). The federated model is a drop-in: PROHORI_SCORER=federated.')}</div></div></div>
        <div class="small muted" style="margin-top:6px">${P.esc(cs.method)}</div></div>`;
    }
    const am = f.amounts;
    if (am) {
      const ev = am.evaluation || {}, th = am.thresholds || {}, hs = am.histograms || {};
      const x = (v) => (v == null ? '—' : `${v >= 10 ? Math.round(v) : (+v).toFixed(1)}×`);
      const roles = Object.entries((ev.send || {}).by_role || {}).map(([k, v]) => `<tr><td>${P.esc(k.replace(/_/g, ' '))}</td><td class="num">${v.rows}</td><td class="num">${pct(v.checked)}</td></tr>`).join('');
      const thrRow = (kind, key, label) => {
        const h = (hs[kind] || {})[key] || {};
        return `<tr><td>${label}</td><td class="num"><b>${x(h.federated_threshold)}</b></td><td class="num">${x(h.central_threshold)}</td><td class="num">${P.n((h.phones || 0).toLocaleString('en-US'))}</td></tr>`;
      };
      html += `<div class="panel" style="margin-top:10px"><h3>③ ${L('পরিমাণের অভ্যাস: গ্রাহক সাধারণত কত পাঠান ও রিচার্জ করেন (ফেডারেটেড অ্যানালিটিক্স)', 'Amount habits: how much each customer usually sends and recharges (federated analytics)')}</h3>
        <p class="small muted" style="margin-top:0">${L('প্রতিটি ফোন নিজের শেষ ৩০টি সেন্ড মানি ও ৩০টি রিচার্জের পরিমাণ নিজের কাছে রাখে। “অস্বাভাবিক” কতটা, তা শেখা হয়েছে সব ফোন মিলে: প্রতিটি ফোন শুধু একটি নয়েজ মেশানো, মাস্ক করা হিস্টোগ্রাম পাঠায় (এই লেনদেন নিজের সাধারণ পরিমাণের কত গুণ), সার্ভার কেবল যোগফল দেখে। আসল ৬৮৩k-সারির ডেটাসেটে, প্রতিটি ওয়ালেট একটি ফোন।',
    'Each phone keeps its own last 30 Send Money amounts and last 30 recharges. What counts as unusual was learned across all phones: each phone sends one noisy, masked histogram (how many times its own usual amount each transfer was) and the server sees only the sum. Run on the real 683k-row dataset, one phone per wallet.')}</p>
        <div class="kv" style="margin-bottom:10px">
          <div><span>${L('ফোন (ওয়ালেট)', 'Phones (wallets)')}</span><b class="num">${(am.phones || 0).toLocaleString('en-US')}</b></div>
          <div><span>${L('গোপনীয়তা', 'Privacy')}</span><b class="num">ε ${am.epsilon_total} (δ 10⁻⁵)</b></div>
          <div><span>${L('সেন্ড মানি: অস্বাভাবিক যদি', 'Send Money: unusual from')}</span><b class="num">${x((th.send || {}).amount_ratio)} ${L('সাধারণের', 'the usual')}</b></div>
          <div><span>${L('রিচার্জ: অস্বাভাবিক যদি', 'Recharge: unusual from')}</span><b class="num">${x((th.recharge || {}).amount_ratio)} ${L('সাধারণের', 'the usual')}</b></div>
          <div><span>${L('টেস্ট উইন্ডো: সৎ সেন্ড মানিতে একবার জিজ্ঞেস', 'Test window: honest Send Money asked once')}</span><b class="num">${pct((ev.send || {}).honest_checked_share)}</b></div>
          <div><span>${L('টেস্ট উইন্ডো: ভুক্তভোগীর প্রতারণা-লেনদেন ধরা', 'Test window: victim-side scam transfers caught')}</span><b class="num">${pct((ev.send || {}).victim_side_checked_share)}</b></div>
          <div><span>${L('টেস্ট উইন্ডো: সৎ রিচার্জে জিজ্ঞেস', 'Test window: honest recharges asked once')}</span><b class="num">${pct((ev.recharge || {}).honest_checked_share)}</b></div></div>
        <div class="two"><div>${tailChart(am, 'send', 'amount_ratio')}
          <div class="small muted">${L('কতগুলো লেনদেন নিজের সাধারণ পরিমাণের অন্তত এত গুণ (লগ স্কেল)। সীমা বসে যেখানে ০.৭৫% লেনদেন তার উপরে; নীল = কেন্দ্রীয় (কাঁচা ডেটা), কমলা = ফেডারেটেড (নয়েজসহ)।',
    'Share of transfers at least this many times the customer\'s own usual amount (log scale). The limit sits where 0.75% of transfers are above it; blue = central (raw data), orange = federated (with noise).')}</div></div>
          <div>${tbl([L('পরীক্ষা', 'Check'), L('ফেডারেটেড (ব্যবহৃত)', 'Federated (used)'), L('কেন্দ্রীয়', 'Central'), L('ফোন', 'Phones')],
            thrRow('send', 'amount_ratio', L('সেন্ড মানি: এই পরিমাণ', 'Send Money: this amount')) + thrRow('send', 'day_ratio', L('সেন্ড মানি: ২৪ ঘণ্টার মোট', 'Send Money: 24 h total'))
            + thrRow('recharge', 'amount_ratio', L('রিচার্জ: এই পরিমাণ', 'Recharge: this amount')) + thrRow('recharge', 'day_ratio', L('রিচার্জ: ২৪ ঘণ্টার মোট', 'Recharge: 24 h total')))}
            <h3 style="margin-top:12px">${L('টেস্ট উইন্ডোতে প্রতারণার ধরন অনুযায়ী ধরা', 'Test window: caught by fraud role')}</h3>${tbl([L('ভূমিকা', 'Role'), L('লেনদেন', 'Transfers'), L('জিজ্ঞেস করা হতো', 'Would be asked')], roles)}</div></div>
        <div class="two" style="margin-top:10px">
          <div><b class="small">${L('ফোনে থাকে', 'Stays on the phone')}</b><ul class="small" style="padding-left:18px">${(am.on_phone || []).map((v) => `<li>${P.esc(v)}</li>`).join('')}</ul>
            <b class="small">${L('ফোন থেকে যায়', 'Leaves the phone')}</b><ul class="small" style="padding-left:18px">${(am.leaves_phone || []).map((v) => `<li>${P.esc(v)}</li>`).join('')}</ul>
            <b class="small">${L('কখনো যায় না', 'Never leaves')}</b><ul class="small" style="padding-left:18px">${(am.never_leaves || []).map((v) => `<li>${P.esc(v)}</li>`).join('')}</ul></div>
          <div><b class="small">${L('সীমাবদ্ধতা', 'Limits')}</b><ul class="small" style="padding-left:18px">${(am.limits || []).map((v) => `<li>${P.esc(v)}</li>`).join('')}</ul>
            <div class="small"><b>${L('লাইভ ব্যবহার', 'Used live')}:</b> ${L('সেন্ড মানির পরিমাণ ও মোবাইল রিচার্জ: সীমা পার হলে একবার জিজ্ঞেস (NUDGE), গ্রাহক নিজের সাধারণ পরিমাণ পাশে দেখেন।', 'Send Money amounts and mobile recharges: past the limit the customer is asked once (NUDGE), with their own usual amount shown next to it.')}</div></div></div>
        <div class="small muted" style="margin-top:6px">${P.esc(am.method || '')}</div></div>`;
    }
    if (!od && !cs && !am) html += `<div class="empty">${L('ফেডারেটেড ফলাফল পাওয়া যায়নি (python -m src.fl.summary)।', 'No federated results packaged (python -m src.fl.summary).')}</div>`;
    $('fl').innerHTML = html;
  }

  /* Share of transfers at or above each ratio, central vs federated, log y; the threshold where it crosses the target. */
  function tailChart(am, kind, key) {
    const h = ((am.histograms || {})[kind] || {})[key];
    if (!h || !am.edges) return '';
    const E = am.edges, n = h.phones || 1, target = (am.target_share || {})[kind] || 0.0075;
    const tail = (arr) => { const out = []; let acc = 0; for (let i = arr.length - 1; i >= 0; i--) { acc += arr[i]; out[i] = Math.max(acc / n, 1e-5); } return out; };
    const tc = tail(h.central), tf = tail(h.federated);
    const W = 320, H = 150, l = 34, b = 22, lo = 0, hi = 6;                 // x: log2 ratio 0..6 (1x..64x)
    const X = (e) => l + ((Math.min(Math.max(e, lo), hi) - lo) / (hi - lo)) * (W - l - 8);
    const Y = (p) => 8 + ((Math.log10(1) - Math.log10(p)) / 4) * (H - b - 8);   // 100% .. 0.01%
    const path = (t) => E.slice(0, -1).map((e, i) => (e >= lo - 0.01 && e <= hi ? `${X(e).toFixed(1)},${Y(t[i]).toFixed(1)}` : null)).filter(Boolean).join(' L');
    const thr = Math.log2(h.federated_threshold);
    const grid = [1, 0.1, 0.01, 0.001].map((p) => `<line x1="${l}" x2="${W - 8}" y1="${Y(p)}" y2="${Y(p)}" stroke="#eef1f6"/><text x="${l - 4}" y="${Y(p) + 3}" font-size="9" text-anchor="end" fill="#7b8597">${p * 100}%</text>`).join('');
    const xt = [0, 1, 2, 3, 4, 5, 6].map((e) => `<text x="${X(e)}" y="${H - 6}" font-size="9" text-anchor="middle" fill="#7b8597">${2 ** e}×</text>`).join('');
    return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:420px" role="img" aria-label="tail share chart">${grid}${xt}
      <line x1="${l}" x2="${W - 8}" y1="${Y(target)}" y2="${Y(target)}" stroke="#c2570c" stroke-dasharray="2 3"/>
      <line x1="${X(thr)}" x2="${X(thr)}" y1="8" y2="${H - b}" stroke="#c62828" stroke-width="1.5"/>
      <text x="${X(thr) - 3}" y="16" font-size="10" text-anchor="end" fill="#c62828">${L('সীমা', 'limit')} ${Math.round(h.federated_threshold * 10) / 10}×</text>
      <path d="M${path(tc)}" fill="none" stroke="#005bac" stroke-width="2"/><path d="M${path(tf)}" fill="none" stroke="#e07a10" stroke-width="1.6" stroke-dasharray="5 3"/></svg>`;
  }

  function heatmap(costs) {
    const D = '0123456789';
    let cells = `<span class="h"></span>${[...D].map((d) => `<span class="h">${d}</span>`).join('')}`;
    [...D].forEach((a) => {
      cells += `<span class="h">${a}</span>`;
      [...D].forEach((b) => {
        const c = a === b ? null : costs.sub[a][b];
        const t = c === null ? 0 : Math.max(0, Math.min(1, (1 - c) / 0.4));
        cells += `<span style="background:${c === null ? '#f0f2f6' : `rgba(0,91,172,${(0.08 + 0.85 * t).toFixed(2)})`};color:${t > 0.55 ? '#fff' : '#33405a'}" title="${L('চেয়েছিলেন', 'meant')} ${a} → ${L('টাইপ', 'typed')} ${b}: ${c === null ? '' : c}">${c === null ? '' : c.toFixed(2).slice(1)}</span>`;
      });
    });
    return `<div class="small muted" style="margin-bottom:4px">${L('শেখা খরচ: সারি = যে ডিজিট চেয়েছিলেন, কলাম = যা টাইপ হয়েছে; গাঢ় = বেশি ঘটে (কম খরচ)', 'Learned costs: row = digit meant, column = digit typed; darker = more common slip (lower cost)')}</div>
      <div class="tscroll"><div class="heat">${cells}</div></div>`;
  }

  // ---------------------------------------------------------------- audit
  async function loadAudit() {
    const a = await P.api('/api/v1/audit');
    $('audit').innerHTML = `<h3>${L('অডিট লগ', 'Audit log')} <span class="chip">${a.verify.ok ? L('✓ হ্যাশ চেইন যাচাই হয়েছে', '✓ hash chain verified') : `✗ broken at #${a.verify.broken_at}`}</span> <span class="small muted">${P.n(a.verify.entries)} ${L('এন্ট্রি', 'entries')}</span></h3>
      <div class="audit">${a.entries.slice().reverse().map((e) => `<div>#${e.seq} ${P.esc(e.at.replace('T', ' '))} · <b>${P.esc(e.actor)}</b> (${P.esc(e.role)}) ${P.esc(e.action)} ${e.alert_id ? `· ${P.esc(e.alert_id)}` : ''} <span class="muted">${P.esc(e.hash.slice(0, 16))}… prev ${P.esc(e.prev.slice(0, 8))}</span></div>`).join('')}</div>`;
  }

  // ---------------------------------------------------------------- language switch
  P.onLang(() => {
    renderFeed();
    if (S.detail) renderDetail(S.detail);
    if (S.tab !== 'alerts') openTab(S.tab);
  });

  // ---------------------------------------------------------------- start
  async function boot() {
    try { S.health = await P.api('/health'); } catch (e) { S.health = null; }
    await poll();
    const firstLive = S.alerts.find((a) => a.source === 'live') || S.alerts.find((a) => a.planted_id === 'SC-03') || S.alerts[0];
    if (firstLive) select(firstLive.id);
  }
  boot().then(() => {
    setInterval(poll, 2500);
    setInterval(async () => {
      try { const h = await P.api('/health'); $('clock').textContent = `${L('ডেমো ঘড়ি', 'demo clock')} ${h.clock.replace('T', ' ').slice(0, 16)}`; } catch (e) { /* offline */ }
    }, 5000);
  });

  // the showcase's reset: start over without reloading the page (the in-browser engine stays up)
  window.ProhoriCopilot = {
    async restart() {
      Object.assign(S, { alerts: [], sel: null, detail: null, pinned: false, first: true, model: null });
      S.seen.clear();
      $('detail').innerHTML = `<div class="panel empty">${L('একটি অ্যালার্ট বেছে নিন।', 'Pick an alert.')}</div>`;
      await boot();
      if (S.tab !== 'alerts') openTab(S.tab);
    },
  };
})();
