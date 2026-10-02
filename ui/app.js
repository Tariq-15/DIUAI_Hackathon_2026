/* Customer app (Layer 1, Pre-Transaction Guardian): Send Money -> wrong-number check -> PIN -> Prohori check ->
   warning in Bangla or English; plus "Report a problem" (Banglish complaints) and the scam checker. */
(function () {
  const P = window.Prohori;
  const { L } = P;
  const $ = (id) => document.getElementById(id);
  const S = {
    customers: [], limits: null, me: null, to: '', toName: '', toNameEn: '', amount: 0, device: null, pin: '', history: [],
    poll: null, view: 'home', pendingAmount: null, hint: null, problem: 'wrong_number', transfers: [], pick: null, cases: [],
    redraw: null, casePoll: null,
  };

  if (P.embed) { $('proto').classList.add('hidden'); $('stage').classList.add('embed'); }

  function toast(msg) {
    const t = $('toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => t.classList.remove('show'), 3400);
  }
  const money = (v) => P.money(v);
  const cname = (c) => (c ? L(c.name, c.name_en || c.name) : '');
  const nameOf = () => L(S.toName, S.toNameEn || S.toName);

  function show(view) {
    S.view = view;
    document.querySelectorAll('.view').forEach((v) => v.classList.toggle('hidden', v.id !== `v-${view}`));
    document.querySelectorAll('#nav button').forEach((b) => b.classList.toggle('on', b.dataset.go === view));
    if (view === 'history') renderHistory();
    if (view === 'account') renderPersonas();
    if (view === 'complain') openComplain();
    if (view !== 'case') clearInterval(S.casePoll);
  }

  const SOON = { cashout: ['ক্যাশ আউট', 'Cash Out'], recharge: ['রিচার্জ', 'Recharge'], paybill: ['পে বিল', 'Pay Bill'], addmoney: ['অ্যাড মানি', 'Add Money'] };
  document.addEventListener('click', (e) => {
    const go = e.target.closest('[data-go]');
    if (go) { show(go.dataset.go); return; }
    const soon = e.target.closest('[data-soon]');
    if (soon) {
      const s = SOON[soon.dataset.soon];
      toast(L(`${s[0]}: এই ডেমোতে প্রহরী শুধু সেন্ড মানি যাচাই করে দেখায়।`, `${s[1]}: in this demo Prohori checks Send Money only.`));
    }
  });

  // ---------------------------------------------------------------- customer
  function setMe(key) {
    S.me = S.customers.find((c) => c.key === key) || S.customers[0];
    P.store.set('prohori.me', S.me.key);
    S.device = null;
    $('devstrip').classList.add('hidden');
    drawMe();
    renderContacts();
  }
  function drawMe() {
    const nm = L(S.me.name_bn, S.me.name_en);
    $('h-avatar').textContent = nm.charAt(0);
    $('h-name').textContent = nm;
    $('h-phone').textContent = P.phone(S.me.msisdn);
    $('h-balance').textContent = L('ব্যালেন্স দেখুন', 'Show balance');
  }

  $('h-balance').addEventListener('click', () => {
    $('h-balance').textContent = money(S.me.balance);
    setTimeout(() => { $('h-balance').textContent = L('ব্যালেন্স দেখুন', 'Show balance'); }, 4000);
  });

  function renderContacts() {
    $('contacts').innerHTML = S.me.contacts.map((c, i) => `
      <div class="item" data-contact="${i}"><div class="avatar">${P.esc(cname(c).charAt(0))}</div>
        <div class="grow"><b>${P.esc(cname(c))}</b><div class="num small muted">${P.phone(c.msisdn)}</div></div>
        <span class="small muted">${L(`আগে ${P.bn(c.sent_before)} বার`, `${c.sent_before} times before`)}</span></div>`).join('');
    $('scenarios').innerHTML = S.me.scenarios.map((s, i) => `
      <button data-scen="${i}"><b>${P.n(i + 1)}.</b> ${P.esc(L(s.bn, s.en || s.bn))}</button>`).join('');
  }

  $('contacts').addEventListener('click', (e) => {
    const it = e.target.closest('[data-contact]');
    if (!it) return;
    const c = S.me.contacts[+it.dataset.contact];
    pickRecipient(c.msisdn, c.name, c.name_en, null, null);
  });
  $('scenarios').addEventListener('click', (e) => {
    const b = e.target.closest('[data-scen]');
    if (!b) return;
    const s = S.me.scenarios[+b.dataset.scen];
    if (s.key === 'typo') {                        // the wrong-number demo starts where it happens: typing the number
      $('to').value = s.to;
      S.pendingAmount = s.amount;
      checkNumber(true);
      $('to').scrollIntoView({ block: 'center', behavior: 'smooth' });
      return;
    }
    pickRecipient(s.to, s.name, s.name_en, s.amount, s.device || null);
    if (s.device) toast(L('টেস্ট: প্রতারক চক্রের ফোন থেকে এই অ্যাকাউন্টে লগইন করা হয়েছে (সিম বদল + পিন রিসেট)।',
      'Test: a scam gang\'s phone has logged in to this account (SIM swap + PIN reset).'));
  });

  // ---------------------------------------------------------------- wrong-number check, as the number is typed
  const typedNumber = () => P.ascii($('to').value).replace(/\D/g, '');
  $('to').addEventListener('input', () => {
    S.pendingAmount = null;
    clearTimeout(S.hintTimer);
    S.hintTimer = setTimeout(() => checkNumber(false), 220);
  });

  async function checkNumber(fromScenario) {
    const n = typedNumber();
    if (n.length !== 11) { S.hint = null; drawHint(); return; }
    try {
      S.hint = await P.api('/api/v1/recipient-check', { method: 'POST', body: { customer: S.me.key, to: n } });
      S.hint.fromScenario = fromScenario;
    } catch (err) { S.hint = null; }
    drawHint();
  }

  function slipText(sug) { return sug && sug.slip ? L(sug.slip.bn, sug.slip.en) : ''; }
  function sugName(sug) { return L(sug.name, sug.name_en) || P.phone(sug.msisdn); }
  function privacyNote() {
    return `<div class="fl-note">🔒 ${L('এই মিলটি আপনার নিজের লেনদেনের ইতিহাস দিয়ে করা হয়; আসল অ্যাপে এটি ফোনেই চলবে, আপনার পরিচিত নম্বর কোথাও যাবে না। কোন ভুলগুলো বেশি হয় (পাশের বোতাম, দুই ডিজিট উল্টে যাওয়া) তা শেখা হয়েছে <b>ফেডারেটেড লার্নিং</b>-এ: ফোনগুলো শুধু নয়েজ মেশানো সংখ্যা পাঠায়, সার্ভার কেবল যোগফল দেখে।',
      'This match uses only your own transfer history; in the real app it runs on the phone and your contacts never leave it. Which slips are common (the key next door, two digits swapped) was learned with <b>federated learning</b>: phones send only noisy counts and the server sees only their sum.')}</div>`;
  }

  function drawHint() {
    const h = S.hint;
    const el = $('to-hint');
    if (!h) { el.innerHTML = ''; return; }
    const contact = S.me.contacts.find((c) => c.msisdn === h.number);
    if (contact) {
      el.innerHTML = `<div class="hint ok">✓ <b>${P.esc(cname(contact))}</b> · ${L(`আগে ${P.bn(contact.sent_before)} বার পাঠিয়েছেন`, `you have sent here ${contact.sent_before} times`)}</div>`;
    } else if (h.suggestion) {
      const sug = h.suggestion;
      el.innerHTML = `<div class="hint warn"><b>⚠️ ${L('নম্বরটি কি ঠিক আছে?', 'Is this the right number?')}</b>
        ${P.numDiff(h.number, sug.msisdn, sug.slip && sug.slip.positions)}
        <div>${L(`<b>${P.esc(sugName(sug))}</b>-এর নম্বরের সাথে প্রায় মিলে যায় (আগে ${P.bn(sug.count)} বার পাঠিয়েছেন)। ${P.esc(slipText(sug))}।`,
          `It is almost <b>${P.esc(sugName(sug))}</b>'s number (you have sent there ${sug.count} times): ${P.esc(slipText(sug))}.`)}</div>
        <div class="row"><button class="btn btn-primary" id="hint-use">✓ ${P.esc(L(`${sugName(sug)}-কে পাঠান`, `Send to ${sugName(sug)}`))}</button>
          <button class="btn btn-ghost" id="hint-keep">${L('না, এই নম্বরটিই', 'No, keep this number')}</button></div>
        ${privacyNote()}</div>`;
      $('hint-use').addEventListener('click', () => pickRecipient(sug.msisdn, sug.name || P.phone(sug.msisdn), sug.name_en, S.pendingAmount, null));
      $('hint-keep').addEventListener('click', () => pickRecipient(h.number, 'নতুন নম্বর', 'New number', S.pendingAmount, null));
    } else if (!h.exists) {
      el.innerHTML = `<div class="hint bad">${L('এই নম্বরে কোনো upay অ্যাকাউন্ট নেই (ডেমো ডেটা)।', 'No upay account uses this number (demo data).')}</div>`;
    } else {
      el.innerHTML = `<div class="hint info">${L('নতুন নম্বর: আগে কখনো এখানে টাকা পাঠাননি। পাঠানোর আগে প্রহরী যাচাই করবে।',
        'New number: you have never sent money here. Prohori will check before it goes.')}</div>`;
    }
  }

  $('to-next').addEventListener('click', () => {
    const n = typedNumber();
    if (!/^01\d{9}$/.test(n)) { toast(L('০১ দিয়ে শুরু ১১ ডিজিটের নম্বর লিখুন', 'Enter an 11-digit number starting with 01')); return; }
    const known = S.me.contacts.find((c) => c.msisdn === n);
    pickRecipient(n, known ? known.name : 'নতুন নম্বর', known ? known.name_en : 'New number', S.pendingAmount, null);
  });

  function pickRecipient(num, name, nameEn, amount, device) {
    S.to = num; S.toName = name; S.toNameEn = nameEn || name; S.device = device;
    $('devstrip').classList.toggle('hidden', !device);
    $('amount').value = amount ? String(amount) : '';
    drawAmount();
    show('amount');
  }
  function drawAmount() {
    $('a-av').textContent = nameOf().charAt(0);
    $('a-name').textContent = nameOf();
    $('a-num').textContent = P.phone(S.to);
    $('a-bal').textContent = money(S.me.balance);
    const cap = S.limits?.[S.me.kyc]?.send_money?.per_txn;
    $('a-cap').textContent = cap ? money(cap) : '—';
    $('quick').innerHTML = [500, 1000, 2000, 5000].map((v) => `<button class="chip" data-amt="${v}">${money(v)}</button>`).join('');
  }
  $('quick').addEventListener('click', (e) => {
    const b = e.target.closest('[data-amt]');
    if (b) $('amount').value = b.dataset.amt;
  });

  $('amount-next').addEventListener('click', () => {
    const v = Number(P.ascii($('amount').value).replace(/[^\d.]/g, ''));
    const cap = S.limits?.[S.me.kyc]?.send_money?.per_txn || 50000;
    if (!v || v <= 0) { toast(L('পরিমাণ লিখুন', 'Enter an amount')); return; }
    if (v > cap) { toast(L(`প্রতি লেনদেনে সর্বোচ্চ ${money(cap)} পাঠানো যায়`, `At most ${money(cap)} per transfer`)); return; }
    if (v > S.me.balance) { toast(L('পর্যাপ্ত ব্যালেন্স নেই', 'Not enough balance')); return; }
    S.amount = v;
    drawPinCard();
    S.pin = '';
    drawPin();
    show('pin');
  });
  function drawPinCard() {
    $('p-to').textContent = `${nameOf()} (${P.phone(S.to)})`;
    $('p-amt').textContent = money(S.amount);
    $('p-fee').textContent = money(0);
  }

  // ---------------------------------------------------------------- PIN pad
  function drawKeypad() {
    $('keypad').innerHTML = ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'C', '0', '⌫']
      .map((k) => `<button data-k="${k}">${/\d/.test(k) ? P.n(k) : k}</button>`).join('');
  }
  $('keypad').addEventListener('click', (e) => {
    const b = e.target.closest('[data-k]');
    if (!b) return;
    const k = b.dataset.k;
    if (k === 'C') S.pin = '';
    else if (k === '⌫') S.pin = S.pin.slice(0, -1);
    else if (S.pin.length < 4) S.pin += k;
    drawPin();
  });
  function drawPin() {
    [...$('pinbox').children].forEach((d, i) => d.classList.toggle('on', i < S.pin.length));
    $('pin-send').disabled = S.pin.length !== 4;
  }

  $('pin-send').addEventListener('click', () => scoreAndShow(null));

  async function scoreAndShow(note) {
    $('checking').classList.remove('hidden');
    const started = Date.now();
    try {
      const res = await P.api('/api/v1/risk-score', {
        method: 'POST', body: { customer: S.me.key, to: S.to, amount: S.amount, device_id: S.device },
      });
      await new Promise((r) => setTimeout(r, Math.max(0, 650 - (Date.now() - started))));
      $('checking').classList.add('hidden');
      S.last = res;
      if (res.band === 'ALLOW') { S.me.balance = res.balance; sent(res, note); } else warn(res);
    } catch (err) {
      $('checking').classList.add('hidden');
      toast(err.message.includes('no upay wallet') ? L('এই নম্বরে কোনো upay অ্যাকাউন্ট নেই (ডেমো ডেটা)', 'No upay account uses this number (demo data)')
        : `${L('সমস্যা', 'Problem')}: ${err.message}`);
    }
  }

  // ---------------------------------------------------------------- the warning sheet
  const TITLES = {
    NUDGE: ['⚠️', ['একটু থামুন, দেখে নিন', 'Wait, take a look'], ['প্রহরী সতর্কতা', 'Prohori warning']],
    STEP_UP: ['🔐', ['নিশ্চিত করতে আবার পিন দিন', 'Enter your PIN again to confirm'], ['প্রহরী: অতিরিক্ত যাচাই', 'Prohori: extra check']],
    HOLD: ['🛑', ['লেনদেনটি সাময়িকভাবে স্থগিত', 'This transfer is paused'], ['প্রহরী: আপনার নিরাপত্তার জন্য', 'Prohori: for your safety']],
  };

  function warn(res) {
    const sug = res.suggestion;
    let [icon, title, sub] = TITLES[res.band];
    if (sug && res.band === 'NUDGE') { icon = '🔢'; title = ['ভুল নম্বর হতে পারে', 'This may be the wrong number']; }
    const reasons = res.reasons.filter((r) => r.code !== 'agent_spike' && !(sug && r.code === 'wrong_recipient')).slice(0, sug ? 2 : 3)
      .map((r) => `<li><span>•</span><span>${P.esc(L(r.bn, r.en))}</span></li>`).join('');
    let body = `
      <div class="row" style="align-items:flex-start"><div style="font-size:30px">${icon}</div>
        <div class="grow"><h2>${L(...title)}</h2><div class="small muted">${L(...sub)} · <span class="num">${money(S.amount)}</span> → ${P.esc(nameOf())}</div></div>
        <button class="listen" id="listen">🔊 ${L('শুনুন', 'Listen')}</button></div>`;
    if (sug) {
      body += `${P.numDiff(sug.typed || S.to, sug.msisdn, sug.slip && sug.slip.positions)}
        <p style="margin:0 0 6px;font-size:14.5px;line-height:1.5">${L(
          `আপনি কি <b>${P.esc(sugName(sug))}</b>-কে পাঠাতে চেয়েছিলেন? সেখানে আগে ${P.bn(sug.count)} বার পাঠিয়েছেন। ${P.esc(slipText(sug))}।`,
          `Did you mean <b>${P.esc(sugName(sug))}</b>? You have sent there ${sug.count} times. ${P.esc(slipText(sug))}.`)}</p>`;
    }
    if (reasons) body += `<ul class="reasons">${reasons}</ul>`;
    if (res.policy_override === 'recipient_frozen_by_analyst') {
      body += `<p class="small"><b>${L('এই নম্বরটি upay-এর পর্যালোচনায় আছে।', 'This number is under review by upay.')}</b></p>`;
    }
    const useBtn = sug && res.choices.includes('use_suggested')
      ? `<button class="btn btn-primary btn-block" data-choice="use_suggested" style="margin-bottom:8px">✓ ${P.esc(L(`${sugName(sug)}-কে পাঠান (${P.phone(sug.msisdn)})`, `Send to ${sugName(sug)} (${P.phone(sug.msisdn)})`))}</button>` : '';
    const question = L(res.question_bn, res.question_en || res.question_bn);
    if (res.band === 'NUDGE') {
      body += `<div class="ask">${P.esc(question)}</div>${useBtn}
        <button class="btn ${sug ? 'btn-ghost' : 'btn-primary'} btn-block" data-choice="cancel">${sug ? L('বাতিল করুন', 'Cancel') : L('বাতিল করুন (প্রস্তাবিত)', 'Cancel (recommended)')}</button>
        <button class="btn btn-ghost btn-block" style="margin-top:8px" data-choice="confirm">${sug ? L('না, এই নম্বরটিই ঠিক, পাঠান', 'No, this number is right, send') : L('হ্যাঁ, চিনি, পাঠাতে চাই', 'Yes, I know them, send')}</button>`;
    } else if (res.band === 'STEP_UP') {
      body += `<div class="ask">${P.esc(question)}</div>${useBtn}
        <input class="field num" id="pin2" inputmode="numeric" maxlength="4" placeholder="${L('পিন (ডেমো: যেকোনো ৪ ডিজিট)', 'PIN (demo: any 4 digits)')}" style="margin-bottom:8px">
        <button class="btn ${sug ? 'btn-ghost' : 'btn-primary'} btn-block" data-choice="cancel">${L('বাতিল করুন (প্রস্তাবিত)', 'Cancel (recommended)')}</button>
        <button class="btn btn-ghost btn-block" style="margin-top:8px" data-choice="confirm_pin" id="pin2-go" disabled>${L('পিন দিয়ে পাঠান', 'Send with PIN')}</button>
        <div class="safety">${L('upay কখনো ফোনে আপনার পিন বা ওটিপি চায় না।', 'upay never asks for your PIN or OTP on the phone.')}</div>`;
    } else {
      body += `<p style="font-size:14.5px;line-height:1.5;margin:4px 0 12px">${L('একজন upay কর্মকর্তা দ্রুত বিষয়টি দেখবেন। <b>আপনার টাকা এখনো আপনার ওয়ালেটেই আছে।</b> কেউ ফোনে তাড়া দিলে লেনদেন করবেন না।',
        'An upay officer will look at it shortly. <b>Your money is still in your wallet.</b> If someone is rushing you on the phone, do not send.')}</p>${useBtn}
        <button class="btn btn-primary btn-block" data-choice="wait">${L('ঠিক আছে, অপেক্ষা করব', 'OK, I will wait')}</button>
        <button class="btn btn-ghost btn-block" style="margin-top:8px" data-choice="cancel">${L('লেনদেন বাতিল করুন', 'Cancel the transfer')}</button>
        <a class="btn btn-link btn-block" style="display:block;text-align:center" href="tel:16268">📞 ${L('১৬২৬৮-এ কল করুন', 'Call 16268')}</a>`;
    }
    if (sug) body += privacyNote();
    $('sheet').className = `sheet ${res.band}${sug ? ' WRONG' : ''}`;
    $('sheet').innerHTML = body;
    $('sheet-wrap').classList.remove('hidden');
    $('listen').addEventListener('click', () => {
      const msg = res.message ? L(res.message.bn, res.message.en) : '';
      P.speak(`${msg} ${question || ''}`, () => toast(L('এই ব্রাউজারে বাংলা ভয়েস ইনস্টল করা নেই; মোবাইলের Chrome-এ শোনা যাবে।', 'No Bangla voice in this browser; it works in Chrome on Android.')));
    });
    const pin2 = $('pin2');
    if (pin2) pin2.addEventListener('input', () => { $('pin2-go').disabled = !/^\d{4}$/.test(P.ascii(pin2.value)); });
    S.redraw = () => { if (!$('sheet-wrap').classList.contains('hidden')) warn(res); };
  }

  $('sheet').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-choice]');
    if (!b) return;
    const res = S.last;
    const choice = b.dataset.choice;
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    if (choice === 'wait') { $('sheet-wrap').classList.add('hidden'); held(res); return; }
    try {
      const out = await P.api(`/api/v1/alerts/${res.alert_id}/decision`, {
        method: 'POST', body: { choice, pin: choice === 'confirm_pin' ? P.ascii($('pin2').value) : null },
      });
      $('sheet-wrap').classList.add('hidden');
      S.me.balance = out.balance;
      if (choice === 'use_suggested') {           // same amount, now to the number they meant: Prohori checks it again
        const sug = res.suggestion;
        S.history.unshift({ name: S.toName, nameEn: S.toNameEn, to: S.to, amount: S.amount, band: res.band, score: res.risk_score,
          status: ['নম্বর ঠিক করা হয়েছে', 'number corrected'], at: res.at });
        S.to = sug.msisdn; S.toName = sug.name || P.phone(sug.msisdn); S.toNameEn = sug.name_en || S.toName;
        await scoreAndShow(['আপনি সঠিক নম্বরটি বেছে নিয়েছেন, প্রহরী আবার যাচাই করেছে।', 'You picked the number you meant; Prohori checked it again.']);
      } else if (choice === 'cancel') stopped(res); else sent(res, ['সতর্কবার্তা দেখার পর আপনি পাঠিয়েছেন।', 'You sent it after seeing the warning.']);
    } catch (err) { toast(err.message); }
  });

  // ---------------------------------------------------------------- results
  function record(res, status) {
    S.history.unshift({ name: S.toName, nameEn: S.toNameEn, to: S.to, amount: S.amount, band: res.band, score: res.risk_score, status, at: res.at });
    S.device = null;                                   // the 'new phone' takeover test is one transfer only
    $('devstrip').classList.add('hidden');
  }

  function sent(res, note) {
    record(res, ['পাঠানো হয়েছে', 'sent']);
    const draw = () => {
      $('r-title').textContent = L('টাকা পাঠানো হয়েছে', 'Money sent');
      $('r-body').innerHTML = `<div class="result ok"><div class="badge">✓</div><h2 style="margin:0">${L('টাকা পাঠানো সফল', 'Transfer successful')}</h2>
        <div style="margin-top:8px"><span class="guardchip">🛡️ ${L(`প্রহরী যাচাই: ঝুঁকি ${P.bn(Math.round(res.risk_score))}/১০০`, `Prohori check: risk ${Math.round(res.risk_score)}/100`)} (${res.band})</span></div>
        ${note ? `<p class="small muted">${L(...note)}</p>` : ''}
        <div class="card receipt"><div><span>${L('প্রাপক', 'To')}</span><b>${P.esc(nameOf())}</b></div><div><span>${L('নম্বর', 'Number')}</span><span class="num">${P.phone(S.to)}</span></div>
        <div><span>${L('পরিমাণ', 'Amount')}</span><b class="num">${money(S.amount)}</b></div><div><span>${L('সময়', 'Time')}</span><span class="num">${P.n(P.time(res.at))}</span></div>
        <div><span>${L('নতুন ব্যালেন্স', 'New balance')}</span><b class="num">${money(S.me.balance)}</b></div></div>
        <button class="btn btn-link" data-report-last>${L('ভুল নম্বরে চলে গেছে? সমস্যা জানান', 'Sent to the wrong number? Report it')}</button></div>`;
    };
    S.redraw = draw;
    S.lastSent = { to: S.to, amount: S.amount };
    draw();
    show('result');
  }

  function stopped(res) {
    record(res, ['বাতিল', 'cancelled']);
    const draw = () => {
      $('r-title').textContent = L('পাঠানো হয়নি', 'Not sent');
      $('r-body').innerHTML = `<div class="result stop"><div class="badge">🛡️</div><h2 style="margin:0">${L('ভালো সিদ্ধান্ত', 'Good call')}</h2>
        <p>${L(`${money(S.amount)} আপনার ওয়ালেটেই আছে। কেউ আবার চাপ দিলে ১৬২৬৮ নম্বরে কল করুন।`, `${money(S.amount)} is still in your wallet. If someone pushes you again, call 16268.`)}</p>
        <p class="small muted">${L(`প্রহরী বিষয়টি upay-এর ঝুঁকি বিশ্লেষকদের কাছে পাঠিয়েছে (রেফারেন্স ${P.esc(res.alert_id)})।`, `Prohori has passed this to upay's risk analysts (reference ${P.esc(res.alert_id)}).`)}</p></div>`;
    };
    S.redraw = draw;
    draw();
    show('result');
  }

  function held(res) {
    record(res, ['পর্যালোচনায়', 'under review']);
    let msg = null;
    const draw = () => {
      $('r-title').textContent = L('পর্যালোচনায় আছে', 'Under review');
      $('r-body').innerHTML = `<div class="result held"><div class="badge">⏳</div><h2 style="margin:0">${L('লেনদেনটি পর্যালোচনায়', 'The transfer is under review')}</h2>
        <p id="held-msg">${msg ? `<b>${P.esc(L(msg[0], msg[1]))}</b>` : L('আপনার টাকা আপনার ওয়ালেটেই আছে। একজন upay কর্মকর্তা দেখছেন।', 'Your money is still in your wallet. An upay officer is looking at it.')}</p>
        <p class="small muted">${L(`রেফারেন্স ${P.esc(res.alert_id)} · এই পাতা নিজে থেকেই হালনাগাদ হবে`, `Reference ${P.esc(res.alert_id)} · this page updates by itself`)}</p></div>`;
    };
    S.redraw = draw;
    draw();
    show('result');
    clearInterval(S.poll);
    S.poll = setInterval(async () => {
      try {
        const st = await P.api(`/api/v1/transfers/${res.alert_id}`);
        if (st.status !== 'held_for_review') {
          clearInterval(S.poll);
          S.me.balance = st.balance;
          const h = S.history.find((x) => x.status[1] === 'under review');
          if (h) h.status = st.status === 'released_by_analyst' ? ['পাঠানো হয়েছে', 'sent'] : ['পাঠানো হয়নি', 'not sent'];
          msg = [st.message_bn, st.message_en];
          if (S.view === 'result') draw();
          toast(L(st.message_bn, st.message_en));
        }
      } catch (e) { /* keep polling */ }
    }, 2500);
  }

  function renderHistory() {
    $('history').innerHTML = S.history.length ? S.history.map((h, i) => `
      <div class="item"><div class="avatar">${P.esc(L(h.name, h.nameEn).charAt(0))}</div>
        <div class="grow"><b>${P.esc(L(h.name, h.nameEn))}</b><div class="small muted num">${P.n(P.time(h.at))} · ${P.esc(L(...h.status))}</div>
          ${h.status[1] === 'sent' ? `<button class="mini-btn" data-report="${i}" style="margin-top:4px">${L('সমস্যা জানান', 'Report')}</button>` : ''}</div>
        <div style="text-align:right"><b class="num">${money(h.amount)}</b><div><span class="band band-${h.band}">${h.band}</span></div></div></div>`).join('')
      : `<div class="empty">${L('এখনো কোনো লেনদেন নেই', 'No transfers yet')}</div>`;
    const mine = S.cases.filter((c) => c.persona === S.me.key);
    $('my-cases').innerHTML = mine.length ? mine.map((c) => `
      <div class="item" data-case="${P.esc(c.id)}"><div class="avatar">🙋</div>
        <div class="grow"><b class="num">${P.esc(c.id)}</b><div class="small muted">${P.esc(L(c.label_bn, c.label_en))}</div></div>
        <span class="small muted">›</span></div>`).join('')
      : `<div class="empty" style="padding:14px">${L('কোনো অভিযোগ নেই', 'No complaints')}</div>`;
    S.redraw = renderHistory;
  }
  $('history').addEventListener('click', (e) => {
    const b = e.target.closest('[data-report]');
    if (!b) return;
    const h = S.history[+b.dataset.report];
    S.prefer = { to: h.to, amount: h.amount };
    show('complain');
  });
  $('my-cases').addEventListener('click', (e) => {
    const it = e.target.closest('[data-case]');
    if (it) openCase(it.dataset.case);
  });
  $('r-body').addEventListener('click', (e) => {
    if (!e.target.closest('[data-report-last]')) return;
    S.prefer = S.lastSent;
    show('complain');
  });

  function renderPersonas() {
    $('personas').innerHTML = S.customers.map((c) => `
      <div class="item" data-persona="${c.key}"><div class="avatar">${P.esc(L(c.name_bn, c.name_en).charAt(0))}</div>
        <div class="grow"><b>${P.esc(L(c.name_bn, c.name_en))}</b> ${c.key === S.me.key ? `<span class="chip">${L('এখন', 'current')}</span>` : ''}
          <div class="small muted">${P.esc(L(c.role_bn, c.role_en || c.role_bn))} · <span class="num">${P.phone(c.msisdn)}</span></div></div></div>`).join('');
    $('privacy-card').innerHTML = `<b>🔒 ${L('আপনার তথ্য কোথায় থাকে', 'Where your data stays')}</b><br>${L(
      `ভুল নম্বর যাচাই আপনার নিজের লেনদেনের ইতিহাস দিয়ে ফোনেই হয়। ভুলের ধরন শেখা হয়েছে ফেডারেটেড লার্নিং-এ (${P.esc(S.slipSource || 'hand-set costs')})। প্রতারণা শনাক্তের মডেলটিও আটটি বিভাগের ডেটা এক জায়গায় না এনে প্রশিক্ষণ দেওয়া যায় (বিশ্লেষক প্যানেলের Federated ট্যাব দেখুন)।`,
      `The wrong-number check uses your own transfer history, on the phone. The slip patterns were learned with federated learning (${P.esc(S.slipSource || 'hand-set costs')}). The scam model can also be trained across the eight divisions without pooling their data (see the Federated tab in the analyst copilot).`)}`;
    S.redraw = renderPersonas;
  }
  $('personas').addEventListener('click', (e) => {
    const it = e.target.closest('[data-persona]');
    if (!it) return;
    setMe(it.dataset.persona);
    renderPersonas();
    toast(`${L('গ্রাহক', 'Customer')}: ${L(S.me.name_bn, S.me.name_en)}`);
  });

  // ---------------------------------------------------------------- report a problem (Banglish complaints, from Ferot)
  const C_SAMPLES = [
    'Bhai ajke bhul kore 800 taka onno number e chole gese, number er sesh 4 digit 4275. 2 ta digit ulta hoye gechilo. Please help.',
    'আজ সকালে মা-কে ৮০০ টাকা পাঠাতে গিয়ে ভুল নম্বরে চলে গেছে, শেষের দুইটা ডিজিট উল্টা হয়ে গেছে। টাকাটা ফেরত চাই।',
    'I sent 800 taka to a wrong number by mistake this morning. The last two digits were swapped. Please help me get it back.',
    'Ekjon phone kore bollo upay office theke, OTP chailo, tarpor 15000 taka pathate bollo chakrir jamanot hisebe. Ami pathiye disi.',
  ];
  $('c-samples').innerHTML = C_SAMPLES.map((s, i) => `<button data-csample="${i}">${P.esc(s)}</button>`).join('');
  $('c-samples').addEventListener('click', (e) => {
    const b = e.target.closest('[data-csample]');
    if (!b) return;
    const i = +b.dataset.csample;
    $('c-text').value = C_SAMPLES[i];
    if (i === 3) setProblem('scam'); else setProblem('wrong_number');
    preview();
  });
  function setProblem(p) {
    S.problem = p;
    document.querySelectorAll('#c-problem button').forEach((b) => b.classList.toggle('on', b.dataset.problem === p));
  }
  $('c-problem').addEventListener('click', (e) => {
    const b = e.target.closest('[data-problem]');
    if (b) setProblem(b.dataset.problem);
  });

  async function openComplain() {
    $('c-consent').checked = false;                    // consent is never pre-ticked
    try {
      S.transfers = await P.api(`/api/v1/customers/${S.me.key}/transfers`);
    } catch (e) { S.transfers = []; }
    S.pick = null;
    if (S.prefer) {
      const t = S.transfers.find((x) => x.number === S.prefer.to && Math.abs(x.amount - S.prefer.amount) < 0.5);
      if (t) S.pick = t.id;
      S.prefer = null;
    }
    drawTransfers();
    preview();
  }
  function drawTransfers() {
    const rows = S.transfers.map((t) => `
      <div class="item ${S.pick === t.id ? 'on' : ''}" data-tid="${P.esc(t.id)}"><div class="avatar">${P.esc((L(t.name, t.name_en) || '?').charAt(0))}</div>
        <div class="grow"><b>${P.esc(L(t.name, t.name_en) || L('অপরিচিত নম্বর', 'Unknown number'))}</b>
          <div class="small muted num">${P.phone(t.number)} · ${P.n(String(t.at).slice(5, 16).replace('T', ' '))}</div></div>
        <b class="num">${money(t.amount)}</b></div>`).join('');
    $('c-transfers').innerHTML = rows + `<div class="item ${S.pick === null ? 'on' : ''}" data-tid=""><div class="avatar">?</div>
      <div class="grow"><b>${L('নিশ্চিত নই / তালিকায় নেই', 'Not sure / not listed')}</b><div class="small muted">${L('আপনার লেখা থেকে প্রহরী লেনদেনটি খুঁজবে', 'Prohori will find it from your words')}</div></div></div>`;
  }
  $('c-transfers').addEventListener('click', (e) => {
    const it = e.target.closest('[data-tid]');
    if (!it) return;
    S.pick = it.dataset.tid || null;
    drawTransfers();
  });
  $('c-text').addEventListener('input', () => { clearTimeout(S.pvTimer); S.pvTimer = setTimeout(preview, 350); });

  async function preview() {
    const text = $('c-text').value.trim();
    if (text.length < 3) { $('c-preview').innerHTML = ''; return; }
    try {
      const e = await P.api('/api/v1/complaints/preview', { method: 'POST', body: { text } });
      const chips = [];
      if (e.amount) chips.push(`${L('পরিমাণ', 'amount')} ${money(e.amount)}`);
      if (e.number) chips.push(`${L('নম্বর', 'number')} ${P.phone(e.number)}`);
      else if (e.number_last4) chips.push(`${L('নম্বরের শেষ ৪ ডিজিট', 'number ending')} ${e.number_last4}`);
      if (e.day_offset !== null && e.day_offset !== undefined) chips.push(({ 0: L('আজ', 'today'), 1: L('গতকাল', 'yesterday') })[e.day_offset] || L(`${P.bn(e.day_offset)} দিন আগে`, `${e.day_offset} days ago`));
      if (e.hour !== null && e.hour !== undefined) chips.push(L(`প্রায় ${P.bn(e.hour)}টা`, `about ${String(e.hour).padStart(2, '0')}:00`));
      if (e.trx_id) chips.push(`TrxID ${e.trx_id}`);
      const lang = { bn: 'বাংলা', banglish: 'Banglish', en: 'English', mixed: L('মিশ্র', 'mixed') }[e.language] || e.language;
      $('c-preview').innerHTML = `<div class="hint info" style="margin-top:10px"><b>${L('প্রহরী যা বুঝেছে', 'What Prohori understood')}</b> <span class="small muted">(${P.esc(lang)}, ${L('নিয়ম দিয়ে, কোনো AI নয়', 'read by rules, no AI')})</span>
        <div class="understood">${chips.length ? chips.map((c) => `<span class="chip">${P.esc(c)}</span>`).join('') : `<span class="small muted">${L('নির্দিষ্ট কিছু পাওয়া যায়নি; উপরে লেনদেনটি বেছে নিন।', 'Nothing specific yet; pick the transfer above.')}</span>`}</div></div>`;
    } catch (err) { $('c-preview').innerHTML = ''; }
  }

  $('c-submit').addEventListener('click', async () => {
    const text = $('c-text').value.trim();
    if (text.length < 3) { toast(L('কী হয়েছে লিখুন', 'Describe what happened')); return; }
    if (!$('c-consent').checked) { toast(L('জমা দিতে সম্মতির ঘরে টিক দিন', 'Tick the consent box to submit')); return; }
    try {
      const st = await P.api('/api/v1/complaints', {
        method: 'POST', body: { customer: S.me.key, text, problem: S.problem, transfer_id: S.pick, consent: true },
      });
      const lab = { wrong_number: ['ভুল নম্বরে পাঠানো', 'Wrong number'], scam: ['প্রতারণা', 'Scam'], other: ['অন্য সমস্যা', 'Other'] }[S.problem];
      S.cases.unshift({ id: st.case_id, persona: S.me.key, label_bn: lab[0], label_en: lab[1] });
      $('c-text').value = '';
      $('c-preview').innerHTML = '';
      openCase(st.case_id, st);
    } catch (err) { toast(err.message); }
  });

  async function openCase(cid, first) {
    let st = first || null;
    const draw = () => {
      if (!st) return;
      const steps = st.steps_en && P.lang === 'en' ? st.steps_en : st.steps_bn;
      const u = st.understood || {};
      const chips = [];
      if (u.amount) chips.push(`${L('পরিমাণ', 'amount')} ${money(u.amount)}`);
      if (u.number) chips.push(`${L('নম্বর', 'number')} ${u.number}`);
      if (u.day_offset !== null && u.day_offset !== undefined) chips.push(({ 0: L('আজ', 'today'), 1: L('গতকাল', 'yesterday') })[u.day_offset] || L(`${P.bn(u.day_offset)} দিন আগে`, `${u.day_offset} days ago`));
      const t = st.transfer;
      $('case-body').innerHTML = `<div class="card">
          <div class="row" style="justify-content:space-between"><b class="num" style="font-size:18px">${P.esc(st.case_id)}</b>
            <span class="chip">${L('শেষ তারিখ', 'Due')} <span class="num">${P.n(st.deadline)}</span></span></div>
          <div class="tracker">${steps.map((s, i) => `<div class="${i < st.step ? 'done' : ''}">${P.esc(s)}</div>`).join('')}</div>
          <p style="font-size:14px;line-height:1.5;margin:6px 0">${P.esc(L(st.message_bn, st.message_en))}</p>
          <p class="small" style="margin:6px 0"><b>${L('পরের ধাপ', 'Next')}:</b> ${P.esc(L(st.next_bn, st.next_en))}</p></div>
        ${t ? `<div class="card" style="margin-top:10px"><div class="small muted">${L('মিলে যাওয়া লেনদেন', 'Matched transfer')}</div>
          <div class="receipt" style="margin-top:4px"><div><span>ID</span><b class="num">${P.esc(t.id)}</b></div><div><span>${L('নম্বর', 'Number')}</span><span class="num">${P.phone(t.number)}</span></div>
          <div><span>${L('পরিমাণ', 'Amount')}</span><b class="num">${money(t.amount)}</b></div><div><span>${L('সময়', 'Time')}</span><span class="num">${P.n(String(t.at).replace('T', ' ').slice(0, 16))}</span></div></div></div>` : ''}
        ${chips.length ? `<div class="understood" style="margin-top:10px">${chips.map((c) => `<span class="chip">${P.esc(c)}</span>`).join('')}</div>` : ''}
        <p class="small muted" style="margin-top:10px">${P.esc(L(st.escalation_bn, st.escalation_en))}</p>`;
    };
    show('case');
    S.redraw = draw;
    if (!st) { try { st = await P.api(`/api/v1/complaints/${cid}`); } catch (err) { toast(err.message); return; } }
    draw();
    clearInterval(S.casePoll);
    S.casePoll = setInterval(async () => {
      try {
        const nx = await P.api(`/api/v1/complaints/${cid}`);
        if (nx.status !== st.status) {
          st = nx;
          draw();
          toast(L(st.next_bn, st.next_en));
        }
      } catch (e) { /* keep polling */ }
    }, 3000);
  }

  // ---------------------------------------------------------------- scam checker
  const SAMPLES = [
    'আমি upay অফিস থেকে বলছি। আপনার অ্যাকাউন্ট ২৪ ঘণ্টার মধ্যে বন্ধ হয়ে যাবে। এখনই মোবাইলে আসা ওটিপি কোডটা বলুন।',
    'অভিনন্দন! আপনি লটারিতে ৫০,০০০ টাকা জিতেছেন। পুরস্কার পেতে ৫০০ টাকা রেজিস্ট্রেশন ফি এই নম্বরে পাঠান।',
    'ভাই, ভুল করে আপনার নম্বরে ৫০০০ টাকা চলে গেছে, প্লিজ এখনই ফেরত পাঠান, খুব বিপদে আছি।',
    'আপনার ছেলে থানায় আটক আছে। মামলা না চাইলে এখনই ২০,০০০ টাকা পাঠান, কাউকে বলবেন না।',
    'Ma, ami notun number theke bolchi, phone hariye geche. 3000 taka pathao, kal ferot dibo.',
  ];
  $('scam-samples').innerHTML = SAMPLES.map((s, i) => `<button data-sample="${i}">${P.esc(s)}</button>`).join('');
  $('scam-samples').addEventListener('click', (e) => {
    const b = e.target.closest('[data-sample]');
    if (b) $('scam-text').value = SAMPLES[+b.dataset.sample];
  });
  let lastScam = null;
  function drawScam() {
    const r = lastScam;
    if (!r) return;
    $('scam-out').innerHTML = `<div class="verdict ${r.verdict}"><b style="font-size:16px">${P.esc(L(r.verdict_bn, r.verdict_en))}</b>
      ${r.cues.map((c) => `<div class="cue"><b>${P.esc(L(c.bn, c.en))}</b> <q>${P.esc(c.matched)}</q><div>${P.esc(L(c.advice_bn, c.advice_en || c.advice_bn))}</div></div>`).join('')}
      <div class="cue"><b>${P.esc(L(r.always_bn, r.always_en || r.always_bn))}</b></div>
      <div class="small muted" style="margin-top:6px">${P.esc(r.method)}</div></div>`;
  }
  $('scam-go').addEventListener('click', async () => {
    const text = $('scam-text').value.trim();
    if (text.length < 3) { toast(L('কিছু লিখুন', 'Type something')); return; }
    try {
      lastScam = await P.api('/api/v1/scam-check', { method: 'POST', body: { text } });
      drawScam();
    } catch (err) { toast(err.message); }
  });

  // ---------------------------------------------------------------- language switch: redraw what is on screen
  P.onLang(() => {
    if (!S.me) return;
    drawMe();
    renderContacts();
    drawKeypad();
    drawHint();
    if (S.view === 'amount') drawAmount();
    if (S.view === 'pin') drawPinCard();
    if (S.view === 'complain') { drawTransfers(); preview(); }
    if (S.view === 'scam') drawScam();
    if (S.redraw && ['result', 'case', 'history', 'account'].includes(S.view)) S.redraw();
    if (!$('sheet-wrap').classList.contains('hidden') && S.last) warn(S.last);
  });

  // ---------------------------------------------------------------- start
  setInterval(() => {
    if (!S.clockBase) return;
    const t = new Date(S.clockBase.getTime() + (Date.now() - S.clockAt));
    $('clock').textContent = P.n(`${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`);
  }, 1000);

  drawKeypad();
  (async function boot() {
    try {
      const c = await P.api('/api/v1/customers');
      S.customers = c.customers;
      S.limits = c.limits;
      S.slipSource = c.slip_costs;
      S.clockBase = new Date(c.clock);
      S.clockAt = Date.now();
      setMe(P.store.get('prohori.me') || 'rahim');
      show('home');
    } catch (err) {
      toast(`${L('প্রহরী API পাওয়া যায়নি', 'Prohori API not reachable')}: ${err.message}`);
    }
  })();
})();
