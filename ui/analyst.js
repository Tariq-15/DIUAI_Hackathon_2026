/* Analyst copilot (Layer 3): an overview dashboard (where the warned money went, what customers decided, the
   held-out test window), the live alert queue, complaint cases, recharges, SHAP evidence, money network, the
   customer's amount habit, 4-part case report, follow-up actions, and the federated-learning results.
   English or Bangla (the case report itself stays English). */
(function () {
  const P = window.Prohori;
  const { L } = P;
  const $ = (id) => document.getElementById(id);
  const S = { alerts: [], seen: new Set(), sel: null, filter: 'all', pinned: false, health: null, first: true, tab: 'overview', detail: null,
    model: null, auditInfo: null, ovSig: '' };
  if (P.embed) { $('proto').classList.add('hidden'); $('tour-start').classList.add('hidden'); }
  document.addEventListener('click', (e) => { const d = $('proto'); if (d.open && !d.contains(e.target)) d.open = false; });
  $('analyst').value = P.store.get('prohori.analyst') || '';
  $('analyst').addEventListener('input', () => P.store.set('prohori.analyst', $('analyst').value.trim()));
  const tbl = (head, rows, cls = '') => `<div class="tscroll tbox"><table class="t ${cls}"><thead><tr>${head.map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>`;
  const pct = (v) => (v == null ? '—' : `${(100 * v).toFixed(1)}%`);

  // ---------------------------------------------------------------- tabs
  const TABS = ['overview', 'alerts', 'agents', 'model', 'fl', 'audit'];
  function openTab(t) {
    S.tab = t;
    document.querySelectorAll('#tabs button').forEach((x) => x.classList.toggle('on', x.dataset.tab === t));
    TABS.forEach((x) => $(`tab-${x}`).classList.toggle('hidden', x !== t));
    if (t === 'overview') loadOverview();
    if (t === 'agents') loadAgents();
    if (t === 'model') loadModel();
    if (t === 'fl') loadFL();
    if (t === 'audit') loadAudit();
  }
  $('tabs').addEventListener('click', (e) => {
    const b = e.target.closest('[data-tab]');
    if (b) { openTab(b.dataset.tab); window.scrollTo(0, 0); }
  });

  // ---------------------------------------------------------------- judge walkthrough (icon-based tour)
  const TOUR = [
    { icon: '👋', tab: 'overview', target: null,
      title: ['প্রহরী কোপাইলটে স্বাগতম', 'Welcome to the Prohori copilot'],
      body: ['এই গাইডটি বিচারকদের জন্য: মডেল, SHAP প্রমাণ, মানি নেটওয়ার্ক, ন্যায্যতা ও ফেডারেটেড ফলাফল কোথায় পাবেন, ধাপে ধাপে দেখাবে।',
        'A short guided tour for judges: where to find the model, SHAP evidence, the money network, fairness and federated results.'] },
    { icon: '📊', tab: 'overview', target: '[data-tab="overview"]',
      title: ['সারসংক্ষেপ: সতর্কতাগুলো কী করল', 'Overview: what the warnings did'],
      body: ['সতর্ক করা টাকা মানিব্যাগে থেকে গেল, সতর্কতার পরও পাঠানো হল, নাকি গ্রাহকের উত্তরের অপেক্ষায় আছে — এবং টেস্ট উইন্ডোর ফলাফল এখানে।',
        'How much warned money stayed in the wallet, was sent anyway, or is still waiting — plus the held-out test-window results, all before you open a single case.'] },
    { icon: '🔔', tab: 'alerts', target: '.queue',
      title: ['অ্যালার্ট তালিকা ও ফিল্টার', 'The alert queue and filters'],
      body: ['অভিযোগ, ভুল নম্বর, অস্বাভাবিক পরিমাণ, রিচার্জ — ফিল্টার দিয়ে বেছে নিন। একটি HOLD অ্যালার্ট ক্লিক করুন প্রমাণ দেখতে।',
        'Filter by complaint, wrong number, unusual amount or recharge. Click any HOLD alert on the left to open its evidence.'] },
    { icon: '🧠', tab: 'alerts', target: '#detail',
      title: ['কেন ঝুঁকি: SHAP প্রমাণ ও মানি নেটওয়ার্ক', 'Why it fired: SHAP evidence and the money network'],
      body: ['একটি অ্যালার্ট খুললে এখানে মডেলের SHAP কারণ (বারচার্ট), মানি নেটওয়ার্ক গ্রাফ, গ্রাহকের নিজের পরিমাণ অভ্যাস এবং একটি চার-অংশের কেস রিপোর্ট দেখবেন।',
        'Open any alert and this panel shows the model’s SHAP reason bars, the money-network graph, the customer’s own amount habit, and a four-part case report — all from structured evidence, nothing invented.'] },
    { icon: '🕵️', tab: 'agents', target: '[data-tab="agents"]',
      title: ['এজেন্ট ওয়াচ: অসাধু ক্যাশ-আউট এজেন্ট', 'Agent Watch: rogue cash-out agents'],
      body: ['পিয়ার z-স্কোর ও পয়সন টেস্ট দিয়ে এলাকার ভিড়ের তুলনায় সন্দেহজনক এজেন্ট ধরা হয় — মাত্র ৯টি অসাধু এজেন্ট থেকে সুপারভাইজড মডেল শেখানো সম্ভব না বলে।',
        'Peer z-scores and a Poisson test flag agents against their area’s footfall — used because only 9 rogue agents exist, too few to train a supervised model on.'] },
    { icon: '⚖️', tab: 'model', target: '[data-tab="model"]',
      title: ['মডেল, অ্যাবলেশন ও ন্যায্যতা', 'Model, ablation and fairness'],
      body: ['টেস্ট উইন্ডোর তুলনা, উপাদান অ্যাবলেশন এবং গ্রুপভিত্তিক false-positive rate (গ্রামীণ কৃষক, বয়স্ক গ্রাহক) — সবই পরিমাপসহ।',
        'Test-window model comparison, component ablation, and the group false-positive-rate audit (rural farmers, older customers), each with measured numbers.'] },
    { icon: '🔒', tab: 'fl', target: '[data-tab="fl"]',
      title: ['ফেডারেটেড লার্নিং ও গোপনীয়তা', 'Federated learning and privacy'],
      body: ['তিনটি ফেডারেটেড ফল: কীপ্যাড-স্লিপ খরচ, পরিমাণ অভ্যাসের সীমা, এবং ৮টি বিভাগ জুড়ে স্কাম মডেল — কী ফোন ছেড়ে যায়, কী কখনো যায় না।',
        'The three federated results: keypad-slip costs, amount-habit limits, and the cross-division scam model — what leaves a phone, and what never does.'] },
    { icon: '🧾', tab: 'audit', target: '[data-tab="audit"]',
      title: ['অডিট লগ', 'Audit log'],
      body: ['প্রতিটি মডেল অ্যালার্ট, গ্রাহকের সিদ্ধান্ত, অভিযোগ ও বিশ্লেষকের পদক্ষেপ একটি SHA-256 হ্যাশ-চেইন করা লগে যায়; নিচের বাটন দিয়ে যাচাই করা যায়।',
        'Every model alert, customer decision, complaint and analyst action goes into a SHA-256 hash-chained log; the button here verifies the chain.'] },
    { icon: '🎓', tab: 'overview', target: null,
      title: ['ঘোরা শেষ — এখন নিজে চালান', 'Tour complete — try it yourself'],
      body: ['হেডারের ⓘ বাটনে ২৭টি টেস্ট নম্বর আছে, প্রতিটির প্রত্যাশিত উত্তরসহ। এই 🧭 বাটনে ক্লিক করলে এই গাইড আবার চালু হবে।',
        'The header’s ⓘ lists test numbers with each one’s recorded answer. Click this 🧭 button any time to replay this tour.'] },
  ];
  const TS = { i: 0, open: false };
  function tourRender() {
    const step = TOUR[TS.i];
    $('tour-icon').textContent = step.icon;
    $('tour-no').textContent = `${TS.i + 1} / ${TOUR.length}`;
    $('tour-title').textContent = L(...step.title);
    $('tour-body').textContent = L(...step.body);
    $('tour-dots').innerHTML = TOUR.map((_, i) => `<i class="${i === TS.i ? 'on' : ''}"></i>`).join('');
    $('tour-back').classList.toggle('hidden', TS.i === 0);
    $('tour-next').textContent = L(...(TS.i === TOUR.length - 1 ? ['শেষ করুন', 'Finish'] : ['পরবর্তী', 'Next']));
    document.querySelectorAll('.tour-highlight').forEach((x) => x.classList.remove('tour-highlight'));
    if (step.tab && step.tab !== S.tab) openTab(step.tab);
    if (step.target) {
      const el = document.querySelector(step.target);
      if (el) { el.classList.add('tour-highlight'); el.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
    }
  }
  function tourOpen(i = 0) {
    TS.i = i; TS.open = true; $('tour').classList.remove('hidden'); tourRender();
    P.store.set('prohori.tourSeen', '1');
  }
  function tourClose() {
    TS.open = false; $('tour').classList.add('hidden');
    document.querySelectorAll('.tour-highlight').forEach((x) => x.classList.remove('tour-highlight'));
  }
  $('tour-start').addEventListener('click', () => tourOpen(0));
  $('tour-skip').addEventListener('click', tourClose);
  $('tour-back').addEventListener('click', () => { if (TS.i > 0) { TS.i -= 1; tourRender(); } });
  $('tour-next').addEventListener('click', () => { if (TS.i < TOUR.length - 1) { TS.i += 1; tourRender(); } else tourClose(); });
  if (!P.embed && !P.store.get('prohori.tourSeen')) setTimeout(() => tourOpen(0), 600);

  // ---------------------------------------------------------------- queue
  $('filters').addEventListener('click', (e) => {
    const b = e.target.closest('[data-f]');
    if (!b) return;
    S.filter = b.dataset.f;
    document.querySelectorAll('#filters button').forEach((x) => x.classList.toggle('on', x === b));
    renderFeed();
  });

  const STATUS = {
    awaiting_customer: ['গ্রাহকের উত্তরের অপেক্ষা', 'waiting for customer'],
    cancelled_by_customer: ['গ্রাহক বাতিল করেছেন', 'customer cancelled'], sent_after_warning: ['সতর্কতার পরও পাঠিয়েছেন', 'customer sent anyway'],
    recipient_flagged: ['প্রাপক চিহ্নিত', 'recipient flagged'],
    dismissed: ['বাতিল (ভুল সতর্কতা)', 'dismissed'], historical: ['টেস্ট উইন্ডো', 'test window'],
    changed_to_suggested: ['প্রস্তাবিত নম্বরে বদলেছেন', 'switched to the suggested number'],
    complaint_received: ['অভিযোগ গৃহীত', 'complaint received'], details_requested: ['আরও তথ্য চাওয়া হয়েছে', 'details requested'],
    details_received: ['গ্রাহকের উত্তর এসেছে', 'customer replied'],
    hold_requested: ['টাকা আটকানোর অনুরোধ', 'hold requested'], recipient_contacted: ['প্রাপকের সম্মতি চাওয়া হয়েছে', 'recipient asked for consent'],
    resolved: ['নিষ্পত্তি', 'resolved'],
  };
  const status = (s) => (STATUS[s] ? L(...STATUS[s]) : s);
  // the dot beside a status: amber = waiting for the customer, teal = money kept, red = sent anyway
  const ST_CLASS = { awaiting_customer: 's-wait', cancelled_by_customer: 's-kept', changed_to_suggested: 's-kept', sent_after_warning: 's-sent',
    complaint_received: 's-case', details_requested: 's-wait', details_received: 's-case', hold_requested: 's-case',
    recipient_contacted: 's-case', recipient_flagged: 's-case' };
  const stPill = (s) => `<span class="st ${ST_CLASS[s] || ''}"><i></i>${P.esc(status(s))}</span>`;
  const bandName = (b) => (b === 'COMPLAINT' ? L('অভিযোগ', 'COMPLAINT') : b === 'STEP_UP' ? 'STEP-UP' : b);
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
      const flash = S.first ? [] : fresh.map((a) => a.id);
      renderFeed(flash);
      const nLive = list.filter((a) => a.source === 'live').length;
      $('nav-live').textContent = P.n(nLive);
      $('nav-live').classList.toggle('hidden', !nLive);
      if (flash.length) S.auditInfo = null;           // new entries in the chain: fetch it again
      if (S.tab === 'overview') loadOverview(flash);
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
      <div class="al ${x.id === S.sel ? 'sel' : ''} ${flash.includes(x.id) ? 'fresh' : ''}" data-id="${x.id}" data-band="${x.band}">
        <div class="t"><span><span class="band band-${x.band}">${bandName(x.band)}</span>
          ${x.kind === 'complaint' || x.kind === 'recharge' ? '' : `<b class="num">${Math.round(x.risk_score)}</b>`}
          ${x.kind === 'recharge' ? `<span class="chip">📱 ${L('রিচার্জ', 'recharge')}</span>` : ''}
          ${x.unusual_amount ? `<span class="chip">💰 ${L('অস্বাভাবিক পরিমাণ', 'unusual amount')}</span>` : ''}
          ${x.source === 'live' ? '<span class="chip">LIVE</span>' : ''}
          ${x.wrong_number ? `<span class="chip">🔢 ${L('ভুল নম্বর?', 'wrong number?')}</span>` : ''}
          ${x.planted_id ? `<span class="chip">${P.esc(x.planted_id)}</span>` : ''}</span>
          <span class="num muted">${P.esc(String(x.created).slice(5, 16).replace('T', ' '))}</span></div>
        <div class="r"><span class="num amt">${P.tk(x.amount)}</span> <span class="num">${P.esc(x.sender_id)} → ${P.esc(x.receiver_id || '?')}</span></div>
        <div class="r why">${P.esc(x.title || x.top_reason || '')}</div>
        ${x.kind === 'complaint' ? `<div class="r muted why">${P.esc(x.top_reason || '')}</div>` : ''}
        ${stPill(x.status)}</div>`).join('') || `<div class="empty">${L('এই ফিল্টারে কোনো অ্যালার্ট নেই। অন্য ফিল্টার বেছে নিন, অথবা ফোন থেকে একটি লেনদেন পাঠান।', 'No alerts match this filter. Pick another filter, or send a transfer on the phone.')}</div>`;
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

  // ---------------------------------------------------------------- overview dashboard
  // Built from what the other tabs already load: the alert list (this session), the model card (held-out test
  // window), health and the audit chain. Nothing here is a separate count kept on the server.
  const BANDS3 = ['HOLD', 'STEP_UP', 'NUDGE'];
  const ASKS = { HOLD: ['সবচেয়ে জোরালো সতর্কতা', 'strongest warning'], STEP_UP: ['আবার পিন', 'PIN again'], NUDGE: ['একটি প্রশ্ন', 'one question'] };
  const SCEN = { S1: ['ওটিপি নিয়ে অ্যাকাউন্ট দখল', 'OTP takeover'], S2: ['টাকা তোলার ওয়ালেট', 'Collector wallet'], S3: ['মিউল চেইন', 'Mule chain'],
    S4: ['অসৎ এজেন্ট', 'Rogue agent'], S5: ['ভুয়া অনলাইন বিক্রেতা', 'Fake online seller'], S6: ['সিম বদল', 'SIM swap'],
    S7: ['ফোনে চাপ দিয়ে পাঠানো', 'Victim guided on a call'], S8: ['চুরি করা কার্ড', 'Stolen card'] };
  const sum = (xs) => xs.reduce((t, a) => t + (+a.amount || 0), 0);
  const kept = (a) => a.customer_choice === 'cancelled' || a.customer_choice === 'used_suggested';
  const count = (v) => P.n(Number(v).toLocaleString('en-US'));

  function sessionStats() {
    const live = S.alerts.filter((a) => a.source === 'live');
    const warn = live.filter((a) => a.kind !== 'complaint');
    const hold = warn.filter((a) => a.band === 'HOLD');
    return { live, warn,
      kept: warn.filter(kept), sent: warn.filter((a) => a.customer_choice && !kept(a)), wait: warn.filter((a) => !a.customer_choice),
      byBand: Object.fromEntries(BANDS3.map((b) => [b, warn.filter((a) => a.band === b).length])),
      holdCancelled: hold.filter(kept).length, holdAnswered: hold.filter((a) => a.customer_choice).length,
      wrong: warn.filter((a) => a.wrong_number), complaints: live.filter((a) => a.kind === 'complaint') };
  }

  // one horizontal bar: label, mark from a zero baseline, value at the tip
  const hbar = (label, small, share, value, cls, tipText) => `<div class="hb" data-tip="${P.esc(tipText)}" tabindex="0">
      <span class="lab">${label}${small ? `<small>${small}</small>` : ''}</span>
      <span class="track axis0">${share > 0 ? `<i class="${cls}" style="width:${Math.min(100, 100 * share).toFixed(1)}%"></i>` : ''}</span><span class="v">${value}</span></div>`;

  function loadOverview(flash = []) {
    if (!S.model && !S.modelBusy) {
      S.modelBusy = true;
      P.api('/api/v1/model').then((m) => { S.model = m; }).catch(() => {}).finally(() => { S.modelBusy = false; if (S.tab === 'overview') renderOverview(); });
    }
    if (!S.auditInfo && !S.auditBusy) {
      S.auditBusy = true;
      P.api('/api/v1/audit').then((a) => { S.auditInfo = a.verify; }).catch(() => {}).finally(() => { S.auditBusy = false; if (S.tab === 'overview') renderOverview(); });
    }
    renderOverview(flash);
  }

  function renderOverview(flash = []) {
    const st = sessionStats();
    const h = S.health || {};
    const sig = JSON.stringify([P.lang, S.alerts.map((a) => [a.id, a.status, a.customer_choice]), !!S.model, S.auditInfo, h.model_trees, (h.clock || '').slice(0, 16)]);
    if (sig === S.ovSig && !flash.length) return;       // nothing changed: keep the page (and any open tooltip) as it is
    S.ovSig = sig;
    const n = st.warn.length;
    const amt = { k: sum(st.kept), s: sum(st.sent), w: sum(st.wait) };

    // -- where the warned money went
    const parts = [['k', amt.k, st.kept.length, L('ওয়ালেটে থেকে গেছে', 'Stayed in the wallet'), L(`${P.n(st.kept.length)}টি বাতিল বা নম্বর ঠিক করা`, `${st.kept.length} cancelled or corrected`)],
      ['s', amt.s, st.sent.length, L('সতর্কতার পরও পাঠানো হয়েছে', 'Sent after the warning'), L(`${P.n(st.sent.length)}টি, গ্রাহকের নিজের সিদ্ধান্তে`, `${st.sent.length}, the customer's own choice`)],
      ['w', amt.w, st.wait.length, L('গ্রাহকের উত্তরের অপেক্ষায়', 'Waiting for the customer'), L(`${P.n(st.wait.length)}টি এখনো ফোনের পর্দায়`, `${st.wait.length} still open on the phone`)]];
    const seg = n ? `<div class="seg" role="img" aria-label="${P.esc(parts.map((p) => `${p[3]}: ${P.money(p[1])}`).join('; '))}">${parts.filter((p) => p[1] > 0)
      .map((p) => `<i class="${p[0]}" style="flex:${p[1]} 1 0%" data-tip="${P.esc(`${p[3]}: ${P.money(p[1])}`)}" tabindex="0"></i>`).join('')}</div>`
      : '<div class="seg none"></div>';
    const flow = `<section class="panel flow">
        <div class="flow-top"><div><h2>${L('সতর্ক করা টাকা কোথায় গেল', 'Where the warned money went')}</h2>
            <p class="sub">${L('প্রহরী শুধু সতর্ক করে। বাতিল করবেন না পাঠাবেন, সেই সিদ্ধান্ত গ্রাহকের; কোনো লেনদেন এখানে আটকে থাকে না।', 'Prohori only warns. Cancelling or sending is the customer\'s decision; no transfer waits here.')}</p></div>
          <div class="flow-total">${L('এই সেশনে সতর্ক করা হয়েছে', 'Warned about this session')}<b>${P.money(amt.k + amt.s + amt.w)}</b>${L(`${P.n(n)}টি সতর্কতা`, `${n} warning${n === 1 ? '' : 's'}`)}</div></div>
        <div class="hero-fig"><b>${P.money(amt.k)}</b><span>${L('সতর্কবার্তার পর ওয়ালেটেই থেকে গেছে', 'stayed in the wallet after a warning')}</span></div>
        ${seg}
        ${n ? `<div class="flow-legend">${parts.map((p) => `<div><i class="sw ${p[0]}"></i><span>${p[3]}</span><b>${P.money(p[1])}</b><em>${p[4]}</em></div>`).join('')}</div>`
          : `<div class="flow-empty">${L('এই সেশনে এখনো কোনো সতর্কতা নেই। ফোন থেকে একটি লেনদেন পাঠান; কয়েক সেকেন্ডের মধ্যে এখানে দেখা যাবে।', 'No warnings yet in this session. Send a transfer on the phone and it shows up here within a few seconds.')}</div>`}
      </section>`;

    // -- four figures
    const switched = st.wrong.filter((a) => a.customer_choice === 'used_suggested').length;
    const tile = (lbl, val, note) => `<div class="tile"><div class="lbl">${lbl}</div><div class="val">${val}</div><div class="note">${note}</div></div>`;
    const tiles = `<div class="tiles">
      ${tile(L('এই সেশনে সতর্কতা', 'Warnings this session'), P.n(n), BANDS3.map((b) => `<span class="band band-${b}">${bandName(b)} ${P.n(st.byBand[b])}</span>`).join(''))}
      ${tile(L('জোরালো সতর্কতার পর বাতিল', 'Cancelled after the strongest warning'), st.holdAnswered ? `${P.n(st.holdCancelled)} <small>${L('/', 'of')} ${P.n(st.holdAnswered)}</small>` : '—',
        st.holdAnswered ? L('HOLD সতর্কতার উত্তর দেওয়া গ্রাহক', 'customers who answered a HOLD warning') : L('এখনো কোনো HOLD সতর্কতার উত্তর আসেনি', 'No HOLD warning has been answered yet'))}
      ${tile(L('সম্ভাব্য ভুল নম্বর', 'Likely wrong numbers'), P.n(st.wrong.length), L(`${P.n(switched)}টিতে গ্রাহক ঠিক নম্বরে বদলেছেন`, `${switched} switched to the number they meant`))}
      ${tile(L('অভিযোগ জমা', 'Complaints filed'), P.n(st.complaints.length), L('১০ কর্মদিবসের মধ্যে উত্তর দিতে হবে', 'each is answered within 10 working days'))}</div>`;

    // -- latest warnings (live first, then the test-window cases the queue already holds)
    const latest = [...st.live, ...S.alerts.filter((a) => a.source !== 'live')].slice(0, 8);
    const rows = latest.map((a) => `<tr data-open="${P.esc(a.id)}" tabindex="0" class="${flash.includes(a.id) ? 'fresh' : ''}">
        <td class="num nw">${P.esc(String(a.created).slice(a.source === 'live' ? 11 : 5, 16).replace('T', ' '))}<div class="src">${a.source === 'live' ? 'LIVE' : L('টেস্ট উইন্ডো', 'test window')}</div></td>
        <td class="nw"><span class="band band-${a.band}">${bandName(a.band)}</span>${a.kind === 'complaint' || a.kind === 'recharge' ? '' : ` <span class="num muted">${Math.round(a.risk_score)}</span>`}</td>
        <td class="num nw"><b>${P.money(a.amount)}</b></td>
        <td><div class="why">${P.esc(a.title || a.top_reason || '')}</div><div class="src num">${P.esc(a.sender_id)} → ${P.esc(a.receiver_id || '?')}</div></td>
        <td>${stPill(a.status)}</td></tr>`).join('');
    const table = `<section class="panel"><div class="row" style="justify-content:space-between;align-items:flex-start;margin-bottom:12px">
          <div><h2>${L('সর্বশেষ সতর্কতা', 'Latest warnings')}</h2><p class="sub">${L('সারিতে ক্লিক করলে প্রমাণসহ কেসটি খুলবে।', 'Click a row to open the case with its evidence.')}</p></div>
          <button class="mini-btn" data-go-tab="alerts">${L('সব অ্যালার্ট দেখুন', 'See all alerts')}</button></div>
        ${rows ? tbl([L('সময়', 'Time'), L('ব্যান্ড', 'Band'), L('পরিমাণ', 'Amount'), L('মূল কারণ, কার থেকে কার কাছে', 'Main reason, from and to'), L('গ্রাহকের সিদ্ধান্ত', 'Customer\'s answer')], rows, 'lt')
          : `<div class="empty">${L('এখনো কোনো অ্যালার্ট নেই।', 'No alerts yet.')}</div>`}</section>`;

    // -- warnings by band, this session
    const maxB = Math.max(1, ...BANDS3.map((b) => st.byBand[b]));
    const byBand = `<section class="panel"><h2>${L('ব্যান্ড অনুযায়ী সতর্কতা', 'Warnings by band')}</h2><p class="sub" style="margin-bottom:8px">${L('এই সেশনে, গ্রাহকের কাছে কী চাওয়া হয়েছে', 'This session, and what each one asks of the customer')}</p>
        ${BANDS3.map((b) => hbar(bandName(b), L(...ASKS[b]), st.byBand[b] / maxB, P.n(st.byBand[b]), `b-${b}`, `${bandName(b)}: ${st.byBand[b]}`)).join('')}</section>`;

    // -- the held-out test window (model card)
    const m = S.model;
    let honest = '', test = '';
    if (m && m.friction && m.bands) {
      const sh = m.friction.legit_txn_share_by_band || {};
      const per = (b) => Math.round(10000 * (sh[b] || 0));
      const warned = BANDS3.map(per);
      const maxW = Math.max(1, ...warned);
      honest = `<section class="panel"><h2>${L('প্রতি ১০,০০০ সৎ লেনদেনে', 'Out of 10,000 honest transfers')}</h2><p class="sub">${L('আলাদা রাখা টেস্ট উইন্ডোতে মাপা', 'Measured on the held-out test window')}</p>
          <p class="big-line"><b>${count(10000 - warned.reduce((a, b) => a + b, 0))}</b> ${L('কোনো সতর্কতা ছাড়াই চলে যায়। বাকিগুলো:', 'go straight through with no warning. The rest:')}</p>
          ${BANDS3.map((b, i) => hbar(bandName(b), L(...ASKS[b]), warned[i] / maxW, count(warned[i]), `b-${b}`, `${bandName(b)}: ${warned[i]} / 10,000`)).join('')}</section>`;
      const fused = (m.comparison || []).find((r) => /fused/i.test(r.model)) || (m.comparison || [])[0] || {};
      const apd = m.friction.alerts_per_day || {};
      const maxA = Math.max(1, ...BANDS3.map((b) => apd[b] || 0));
      const scen = (m.per_scenario || []).map((r) => hbar(P.esc(L(...(SCEN[r.scenario] || [r.scenario, r.scenario]))), L(`${count(r.fraud_txns)}টি লেনদেন`, `${r.fraud_txns} transfers`),
        r.recall_stepup, `${P.n(Math.round(100 * r.recall_stepup))}%`, '', `${L(...(SCEN[r.scenario] || [r.scenario, r.scenario]))}: ${(100 * r.recall_stepup).toFixed(1)}% (${r.fraud_txns})`)).join('');
      test = `<section class="panel"><div class="row" style="justify-content:space-between;align-items:flex-start;margin-bottom:12px">
            <div><h2>${L('আলাদা রাখা টেস্ট উইন্ডো: ১০ দিন, যা মডেল কখনো দেখেনি', 'Held-out test window: 10 days the model never saw')}</h2>
              <p class="sub">${L('সিন্থেটিক ডেটা, তাই সংখ্যাগুলো ঊর্ধ্বসীমা হিসেবে পড়ুন।', 'Synthetic data, so read these numbers as upper bounds.')}</p></div>
            <button class="mini-btn" data-go-tab="model">${L('মডেল ও ন্যায্যতা', 'Model and fairness')}</button></div>
          <div class="kv">
            <div><span>${L('স্কোর করা লেনদেন', 'Transactions scored')}</span><b>${count(fused.n || 0)}</b></div>
            <div><span>${L('প্রতারণার লেনদেন', 'Scam transactions among them')}</span><b>${count(fused.positives || 0)}</b></div>
            <div><span>${L('প্রতারণায় সতর্কতা গেছে (NUDGE বা বেশি)', 'Scam transactions that got a warning')}</span><b>${pct((m.bands['NUDGE+'] || {}).recall)}</b></div>
            <div><span>${L('HOLD সতর্কতা যা সত্যিই প্রতারণা', 'HOLD warnings that were real scams')}</span><b>${pct((m.bands['HOLD+'] || {}).precision)}</b></div>
            <div><span>${L('কোনো সতর্কতা ছাড়া সৎ লেনদেন', 'Honest transfers with no warning')}</span><b>${sh.ALLOW == null ? '—' : `${(100 * sh.ALLOW).toFixed(2)}%`}</b></div></div>
          <div class="ov-two" style="--lbl:150px">
            <div><h3>${L('প্রতারণার ধরন অনুযায়ী ধরা পড়া', 'Scam types caught')}</h3><p class="sub" style="margin:-6px 0 8px">${L('STEP-UP বা তার বেশি সতর্কতা পাওয়া প্রতারণার লেনদেনের অংশ', 'Share of scam transfers that reached STEP-UP or above')}</p>${scen}</div>
            <div style="--lbl:96px"><h3>${L('দিনে গড়ে কতগুলো সতর্কতা', 'Warnings on an average day')}</h3><p class="sub" style="margin:-6px 0 8px">${L('১০ দিনের গড়, ব্যান্ড অনুযায়ী', 'Mean over the 10 days, by band')}</p>
              ${BANDS3.map((b) => hbar(bandName(b), L(...ASKS[b]), (apd[b] || 0) / maxA, P.n(apd[b] ?? '—'), `b-${b}`, `${bandName(b)}: ${apd[b]} / ${L('দিন', 'day')}`)).join('')}</div></div>
        </section>`;
    }

    const au = S.auditInfo;
    $('overview').innerHTML = `<div class="ov-head"><div><h1>${L('সারসংক্ষেপ', 'Overview')}</h1>
          <p>${L('এই সেশনে প্রহরী কী নিয়ে সতর্ক করেছে, আর গ্রাহকেরা কী সিদ্ধান্ত নিয়েছেন।', 'What Prohori warned about in this session, and what each customer decided.')}</p></div>
        <div class="ov-sys">${h.clock ? `<span class="chip">${L('ডেমো ঘড়ি', 'Demo clock')} <b class="num">${P.n(h.clock.slice(11, 16))}</b></span>` : ''}
          ${h.model_trees ? `<span class="chip"><b class="num">${count(h.model_trees)}</b> ${L('গাছের মডেল', 'trees in the model')}</span>` : ''}
          ${h.wallets_in_state ? `<span class="chip"><b class="num">${count(h.wallets_in_state)}</b> ${L('ওয়ালেট লাইভ স্টোরে', 'wallets in the live store')}</span>` : ''}
          ${au ? `<span class="chip ${au.ok ? 'ok-chip' : 'bad-chip'}">${au.ok ? L(`✓ অডিট চেইন ঠিক আছে, ${P.n(au.entries)}টি এন্ট্রি`, `✓ Audit chain verified, ${au.entries} entries`) : L('✗ অডিট চেইন ভাঙা', '✗ Audit chain broken')}</span>` : ''}</div></div>
      ${flow}${tiles}<div class="ov-grid">${table}<div class="ov-side">${byBand}${honest}</div></div>${test}`;
  }

  function openCase(id) {
    S.pinned = true;
    openTab('alerts');
    window.scrollTo(0, 0);
    select(id).then(() => { const el = document.querySelector('#feed .al.sel'); if (el) el.scrollIntoView({ block: 'nearest' }); });
  }
  $('overview').addEventListener('click', (e) => {
    const go = e.target.closest('[data-go-tab]');
    if (go) { openTab(go.dataset.goTab); window.scrollTo(0, 0); return; }
    const row = e.target.closest('[data-open]');
    if (row) openCase(row.dataset.open);
  });
  $('overview').addEventListener('keydown', (e) => {
    const row = e.key === 'Enter' && e.target.closest('[data-open]');
    if (row) openCase(row.dataset.open);
  });

  // one tooltip for every chart mark: hover or keyboard focus on anything with data-tip
  const tip = document.createElement('div');
  tip.className = 'tip';
  tip.setAttribute('role', 'tooltip');
  document.body.appendChild(tip);
  function showTip(el) {
    tip.textContent = el.dataset.tip;
    tip.classList.add('on');
    const r = el.getBoundingClientRect();
    tip.style.left = `${Math.max(8, Math.min(window.innerWidth - tip.offsetWidth - 8, r.left + r.width / 2 - tip.offsetWidth / 2))}px`;
    tip.style.top = `${r.top - tip.offsetHeight - 8 < 8 ? r.bottom + 8 : r.top - tip.offsetHeight - 8}px`;
  }
  ['mouseover', 'focusin'].forEach((ev) => document.addEventListener(ev, (e) => {
    const el = e.target.closest && e.target.closest('[data-tip]');
    if (el) showTip(el); else tip.classList.remove('on');
  }));
  ['mouseout', 'focusout', 'scroll'].forEach((ev) => document.addEventListener(ev, () => tip.classList.remove('on'), true));

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
        <span class="band band-${d.band}" style="font-size:14px">${bandName(d.band)}</span>
        <b class="case-amt">${P.tk(d.amount)}</b>
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
          <span><i style="background:#b23b3b"></i>${L('সাজানো প্রতারণার ভূমিকা', 'planted fraud role')}</span><span><i style="background:#fff;border:2px solid #c62828"></i>${L('১৬২৬৮-এ অভিযোগ', 'reported to 16268')}</span><span>🚩 ${L('চিহ্নিত', 'flagged')}</span></div></div>
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
    const fits = (k) => (d.kind === 'complaint' ? !['VERIFY_OWNER', 'REVIEW_AGENT'].includes(k)
      : d.kind === 'recharge' ? ['VERIFY_OWNER', 'WATCHLIST', 'DISMISS'].includes(k) : !COMPLAINT_ONLY.includes(k));
    const order = [...rep.actions, ...Object.keys(labels).filter((k) => !rec.has(k) && fits(k))];
    return `<div class="panel">
        <h3>${L('পরবর্তী পদক্ষেপ', 'Follow up')}</h3>
        ${d.kind === 'complaint' ? '' : `<div class="small muted" style="margin-bottom:8px">${L('গ্রাহক সতর্কবার্তা পেয়েছেন এবং নিজেই সিদ্ধান্ত নেন; কোনো লেনদেন এখানে অপেক্ষায় থাকে না।', 'The customer has been warned and decides; no transfer waits here.')}</div>`}
        <div class="actions" id="acts">${order.map((k) => `<button data-act="${k}" class="${rec.has(k) ? 'rec' : ''} ${k === 'DISMISS' ? 'warn' : ''}" title="${P.esc(L(labels[k].en, labels[k].bn))}">${P.esc(L(labels[k].bn, labels[k].en))}</button>`).join('')}</div>
        <input class="field" id="note" placeholder="${L('অডিট লগের জন্য নোট (বাতিল করতে আবশ্যক)', 'Note for the audit log (required to dismiss)')}" style="margin-top:10px;font-size:14px;padding:9px">
        <div class="small muted" style="margin-top:6px">${d.flagged_recipient ? L('🚩 প্রাপক চিহ্নিত: সেখানে নতুন যেকোনো লেনদেনে গ্রাহক সবচেয়ে জোরালো সতর্কবার্তা পাবেন, সিদ্ধান্ত গ্রাহকেরই। ', '🚩 The recipient is flagged: any new transfer to it gets the strongest warning; the customer still decides. ') : ''}${d.hold_amount ? L(`আটকানোর অনুরোধ: ${P.tk(d.hold_amount)}। `, `Hold requested: ${P.tk(d.hold_amount)}. `) : ''}${L('প্রতিটি পদক্ষেপ আপনার নামে লগ হয়।', 'Every action is logged with your name.')}</div>
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
      if (!analyst) { $('analyst').focus(); alert(L('আগে আপনার নাম লিখুন: প্রতিটি পদক্ষেপ নামসহ লগ হয়।', 'Enter your name first: every action is logged with a name.')); return; }
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
        <div class="gauge" style="margin-top:14px" role="img" aria-label="${L('ঝুঁকি স্কোর', 'Risk score')} ${d.risk_score}/100"><i style="left:calc(${Math.min(99.4, d.risk_score)}% - 2px)"></i></div>
        <div class="gauge-scale"><span style="left:0">ALLOW</span><span style="left:30%">NUDGE 30</span><span style="left:60%">STEP-UP 60</span><span style="left:80%">HOLD 80</span></div>
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
          <span class="band band-${d.band}" style="font-size:14px">${bandName(d.band)}</span><span class="chip">📱 ${L('মোবাইল রিচার্জ', 'Mobile recharge')}</span>
          <b class="case-amt">${P.tk(d.amount)}</b><span class="num">${P.esc(d.sender_id)} → ${P.esc(rc.number)}</span>
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
      ${threadPanel(c, d.status)}
      ${wrongNumberPanel(c.slip, c.slip && c.slip.typed, null)}
      ${evidence(d)}${report(d)}${decide(d)}`;
    wire(d);
  }

  function threadPanel(c, status) {
    const thread = c.thread || [];
    if (!thread.length && status !== 'details_requested') return '';
    const bubble = (m) => `<div class="thread-msg ${m.role}"><span class="thread-ic">${m.role === 'analyst' ? '🕵️' : '🧑'}</span>
      <div class="thread-body"><div class="thread-who">${m.role === 'analyst' ? L('বিশ্লেষক', 'Analyst') : L('গ্রাহক', 'Customer')} <span class="small muted">· ${P.esc(String(m.at).replace('T', ' ').slice(0, 16))}</span></div>
      <div>${P.esc(m.text)}</div></div></div>`;
    const waiting = status === 'details_requested'
      ? `<div class="thread-msg analyst wait"><span class="thread-ic">⏳</span><div class="thread-body"><div class="small muted">${L('গ্রাহকের উত্তরের অপেক্ষায়', 'Waiting for the customer to reply (asked in the customer app)')}</div></div></div>` : '';
    return `<div class="panel"><h3>💬 ${L('আরও তথ্যের জন্য অনুরোধ', 'Follow-up on this case')}</h3>
      <div class="thread">${thread.map(bubble).join('')}${waiting}</div></div>`;
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
        <text x="${x}" y="${y + r + 12}" text-anchor="middle" font-size="10.5" fill="#33405a" font-family="ui-monospace,Consolas,monospace">${P.esc(label)}${n.flagged ? ' 🚩' : ''}</text>
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
    const demo = (m.demo || []).map((r) => `<tr><td class="nw">${P.esc(r.id)}</td><td>${P.esc(r.title)}</td><td>${P.esc(r.expected)}</td><td><span class="band band-${r.actual === 'FLAGGED' ? 'HOLD' : r.actual}">${P.esc(r.actual)}</span></td><td class="num">${r.risk_score}</td></tr>`).join('');
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
    S.auditInfo = a.verify;
    const rows = a.entries.slice().reverse().map((e) => `<tr><td>${e.seq}</td><td>${P.esc(e.at.replace('T', ' '))}</td>
      <td class="who"><b>${P.esc(e.actor)}</b> <span class="muted">${P.esc(e.role)}</span></td><td>${P.esc(e.action)}</td><td>${P.esc(e.alert_id || '')}</td>
      <td class="who">${e.detail && e.detail.note ? `“${P.esc(e.detail.note)}”` : ''}</td>
      <td title="${P.esc(e.hash)}">${P.esc(e.hash.slice(0, 16))}…</td><td class="muted" title="${P.esc(e.prev)}">${P.esc(e.prev.slice(0, 8))}…</td></tr>`).join('');
    $('audit').innerHTML = `<h3>${L('অডিট লগ', 'Audit log')} <span class="chip ${a.verify.ok ? 'ok-chip' : 'bad-chip'}">${a.verify.ok ? L('✓ হ্যাশ চেইন যাচাই হয়েছে', '✓ hash chain verified') : `✗ broken at #${a.verify.broken_at}`}</span> <span class="small muted">${P.n(a.verify.entries)} ${L('এন্ট্রি', 'entries')}</span></h3>
      <p class="small muted" style="margin-top:0">${L('মডেলের প্রতিটি সতর্কতা, গ্রাহকের প্রতিটি সিদ্ধান্ত, অভিযোগ ও বিশ্লেষকের পদক্ষেপ এখানে জমা হয়। প্রতিটি সারি আগের সারির হ্যাশ বহন করে, তাই কোনো সারি বদলালে চেইন ভেঙে যায়।',
        'Every model warning, customer decision, complaint and analyst action lands here. Each row carries the hash of the row before it, so changing any row breaks the chain.')}</p>
      ${tbl(['#', L('সময়', 'When'), L('কে', 'Who'), L('কী', 'Action'), L('অ্যালার্ট', 'Alert'), L('নোট', 'Note'), L('হ্যাশ', 'Hash'), L('আগের হ্যাশ', 'Previous')], rows, 'audit-t')}`;
  }

  // ---------------------------------------------------------------- language switch
  P.onLang(() => {
    renderFeed();
    if (S.detail) renderDetail(S.detail);
    if (S.tab !== 'alerts') openTab(S.tab);
    if (TS.open) tourRender();
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
      try {
        const h = await P.api('/health');
        S.health = h;
        $('clock').textContent = `${L('ডেমো ঘড়ি', 'demo clock')} ${h.clock.replace('T', ' ').slice(0, 16)}`;
      } catch (e) { /* offline */ }
    }, 5000);
  });

  // the showcase's reset: start over without reloading the page (the in-browser engine stays up)
  window.ProhoriCopilot = {
    async restart() {
      Object.assign(S, { alerts: [], sel: null, detail: null, pinned: false, first: true, model: null, auditInfo: null, ovSig: '' });
      S.seen.clear();
      $('detail').innerHTML = `<div class="panel empty">${L('একটি অ্যালার্ট বেছে নিন।', 'Pick an alert.')}</div>`;
      await boot();
      if (S.tab !== 'alerts') openTab(S.tab);
    },
  };
})();
