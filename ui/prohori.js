/* Shared helpers for the Prohori pages. Same-origin API by default; ?api=https://host to point elsewhere. */
(function () {
  const params = new URLSearchParams(location.search);
  const base = (params.get('api') || '').replace(/\/+$/, '');
  const BN = '০১২৩৪৫৬৭৮৯';
  const sget = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  const sset = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } };

  async function api(path, { method = 'GET', body } = {}) {
    const eng = window.ProhoriEngine;                 // static hosting: the API runs in this browser (engine.js)
    if (eng) {
      const r = await eng.call(method, path, body);
      if (r.status >= 400) throw new Error(r.detail || `error ${r.status}`);
      return r.data;
    }
    const res = await fetch(base + path, {
      method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data = null;
    try { data = await res.json(); } catch (e) { /* not JSON */ }
    if (!res.ok) {
      const d = data && data.detail;
      throw new Error(typeof d === 'string' ? d : (Array.isArray(d) ? d.map((x) => x.msg).join('; ') : res.statusText));
    }
    return data;
  }

  const bn = (v) => String(v).replace(/[0-9]/g, (d) => BN[d]);
  const ascii = (v) => String(v).replace(/[০-৯]/g, (d) => String(BN.indexOf(d)));
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const tk = (v) => `৳ ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  const tkbn = (v) => `৳${bn(Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 }))}`;
  const time = (iso) => String(iso || '').slice(11, 16);
  const phone = (m) => (/^\d{11}$/.test(m) ? `${m.slice(0, 5)}-${m.slice(5)}` : m);

  // ---------------------------------------------------------------- language: Bangla <-> English
  // Static text: an element carries its other language in data-en (Bangla pages) or data-bn (English pages);
  // placeholders in data-en-ph / data-bn-ph. Text built in JS uses L(bangla, english). The choice is remembered
  // and shared by every page and iframe of the demo.
  const LKEY = 'prohori.lang';
  const parentLang = () => { try { return window.parent !== window && window.parent.Prohori ? window.parent.Prohori.lang : null; } catch (e) { return null; } };
  let lang = ['bn', 'en'].includes(params.get('lang')) ? params.get('lang')        // a screen inside the showcase follows it
    : (parentLang() || sget(LKEY) || document.documentElement.dataset.lang || 'bn');
  const subs = [];
  const L = (bnText, enText) => (lang === 'en' ? enText : bnText);
  const n = (v) => (lang === 'en' ? String(v) : bn(v));
  const money = (v) => (lang === 'en' ? `Tk ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : tkbn(v));

  function applyLang(root = document) {
    document.documentElement.lang = lang;
    root.querySelectorAll('[data-en], [data-bn]').forEach((el) => {
      if (!('bn' in el.dataset)) el.dataset.bn = el.innerHTML;
      if (!('en' in el.dataset)) el.dataset.en = el.innerHTML;
      el.innerHTML = lang === 'en' ? el.dataset.en : el.dataset.bn;
    });
    root.querySelectorAll('[data-en-ph], [data-bn-ph]').forEach((el) => {
      if (!('bnPh' in el.dataset)) el.dataset.bnPh = el.placeholder;
      if (!('enPh' in el.dataset)) el.dataset.enPh = el.placeholder;
      el.placeholder = lang === 'en' ? el.dataset.enPh : el.dataset.bnPh;
    });
    root.querySelectorAll('[data-lang-toggle]').forEach((b) => {
      b.innerHTML = `<span class="${lang === 'bn' ? 'on' : ''}">বাং</span><span class="${lang === 'en' ? 'on' : ''}">EN</span>`;
      b.title = lang === 'en' ? 'বাংলায় দেখুন' : 'Switch to English';
      b.setAttribute('aria-label', b.title);
    });
  }

  function setLang(l) {
    if (!['bn', 'en'].includes(l) || l === lang) return;
    lang = l;
    sset(LKEY, l);
    applyLang();
    subs.forEach((f) => { try { f(l); } catch (e) { console.error(e); } });
    document.querySelectorAll('iframe').forEach((f) => {                 // the showcase passes it to both screens
      try { if (f.contentWindow.Prohori) f.contentWindow.Prohori.setLang(l); } catch (e) { /* other origin */ }
    });
    try { if (window.parent !== window && window.parent.Prohori) window.parent.Prohori.setLang(l); } catch (e) { /* other origin */ }
  }
  document.addEventListener('click', (e) => {
    if (e.target.closest('[data-lang-toggle]')) setLang(lang === 'en' ? 'bn' : 'en');
  });
  window.addEventListener('storage', (e) => { if (e.key === LKEY && e.newValue) setLang(e.newValue); });
  // moving between the demo's pages keeps the language on screen
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a[href]');
    if (!a || a.target || !/^[\w-]+\.html(\?[^#]*)?(#.*)?$/.test(a.getAttribute('href'))) return;
    const u = new URL(a.href, location.href);
    u.searchParams.set('lang', lang);
    if (params.get('api')) u.searchParams.set('api', params.get('api'));
    a.href = u.href;
  });

  /* A phone number typed vs the one probably meant, with the digits that differ marked (1-based positions). */
  function numDiff(typed, meant, positions) {
    let pos = new Set(positions || []);
    if (!pos.size && typed.length === meant.length) [...typed].forEach((d, i) => { if (d !== meant[i]) pos.add(i + 1); });
    const row = (num, cls) => [...num].map((d, i) => `${i === 5 ? '<b class="sep">-</b>' : ''}<i class="${pos.has(i + 1) ? cls : ''}">${d}</i>`).join('');
    return `<div class="numdiff">
      <div><span class="lbl">${L('আপনি লিখেছেন', 'You typed')}</span><span class="digits">${row(typed, 'bad')}</span></div>
      <div><span class="lbl">${L('সম্ভবত চেয়েছিলেন', 'You probably meant')}</span><span class="digits">${row(meant, 'good')}</span></div></div>`;
  }

  /* Read text aloud with the browser's own speech engine (no network). */
  function speak(text, onNoVoice) {
    if (!('speechSynthesis' in window)) { onNoVoice && onNoVoice(); return; }
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang === 'en' ? 'en-IN' : 'bn-BD';
    const voices = speechSynthesis.getVoices();
    const v = voices.find((x) => (lang === 'en' ? /^en/i : /^bn/i).test(x.lang)) || null;
    if (v) u.voice = v; else if (lang !== 'en') onNoVoice && onNoVoice();
    u.rate = 0.92;
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
  }
  if ('speechSynthesis' in window) speechSynthesis.getVoices();

  /* First visit in browser mode: show what is loading until the in-browser engine is ready. */
  function bootScreen() {
    const eng = window.ProhoriEngine;
    if (!eng || params.get('embed') === '1' || eng.state.ready) return;
    const el = document.createElement('div');
    el.className = 'boot';
    el.innerHTML = `<div class="boot-card"><img class="boot-logo" src="img/prohori-logo.png" alt="Prohori" width="132" height="153">
      <div class="spin"></div><b>${L('প্রহরী চালু হচ্ছে', 'Starting Prohori')}</b>
      <div class="small" id="boot-msg"></div><div class="boot-bar"><i id="boot-bar"></i></div>
      <p class="small muted" id="boot-note"></p></div>`;
    document.body.appendChild(el);
    eng.onState((s) => {
      const m = el.querySelector('#boot-msg');
      const msg = s.msg && typeof s.msg === 'object' ? L(s.msg.bn, s.msg.en) : (s.msg || '');
      if (m) m.textContent = s.failed ? `${L('চালু করা যায়নি', 'Could not start')}: ${s.failed}` : msg;
      const note = el.querySelector('#boot-note');
      if (note) {
        note.textContent = s.cached
          ? L('মডেলগুলো আগেই এই ডিভাইসে রাখা আছে: কিছু নামাতে হচ্ছে না, শুধু Python চালু হচ্ছে (কয়েক সেকেন্ড)।',
            'The models are already stored on this device: nothing is downloaded, only Python starts (a few seconds).')
          : L('প্রশিক্ষিত মডেলগুলো আপনার ব্রাউজারের ভেতরেই চলে (Pyodide / WebAssembly): কোনো সার্ভার নেই, আপনি যা লেখেন তা এই ডিভাইস থেকে কোথাও যায় না। প্রথমবার প্রায় ৩০ MB নামবে এবং এই ডিভাইসে রাখা থাকবে; পরেরবার কিছু নামাতে হবে না।',
            'The trained models run inside your browser (Pyodide / WebAssembly): no server, and nothing you type leaves this device. The first visit downloads about 30 MB and keeps it on this device; after that nothing is downloaded again.');
      }
      el.classList.toggle('mini', !!s.cached && !s.failed);   // from the cache: a corner card, the page stays usable
      const b = el.querySelector('#boot-bar');
      if (b) b.style.width = `${s.pct || 0}%`;
      if (s.ready) el.remove();
    });
  }
  /* How much this customer usually sends / recharges, next to this amount: the last 30 amounts as dots on a log
     scale, this one in red, the 'unusual from' line dashed. Used by the phone warning and the analyst copilot. */
  function habitStrip(h, opts = {}) {
    if (!h || !h.history || !h.history.length) return '';
    const W = 300, H = opts.h || 54, pad = 10;
    const usual = h.usual || 1, line = usual * (h.threshold || 1);
    const vals = [...h.history, h.amount || usual, line];
    const lo = Math.log10(Math.max(1, Math.min(...vals) * 0.8)), hi = Math.log10(Math.max(...vals) * 1.25);
    const x = (v) => pad + ((Math.log10(Math.max(v, 1)) - lo) / Math.max(hi - lo, 1e-6)) * (W - 2 * pad);
    const dots = h.history.map((v, i) => `<circle cx="${x(v).toFixed(1)}" cy="${(H / 2 - 6 + (i % 3) * 6).toFixed(1)}" r="3.4" fill="#7b8bb0" opacity=".75"><title>${money(v)}</title></circle>`).join('');
    const mid = `<line x1="${x(usual)}" x2="${x(usual)}" y1="6" y2="${H - 14}" stroke="#0f8a5f" stroke-width="2"/>`;
    const thr = `<line x1="${x(line)}" x2="${x(line)}" y1="4" y2="${H - 14}" stroke="#c2570c" stroke-width="1.5" stroke-dasharray="3 3"/>`;
    const cur = h.amount ? `<path d="M${x(h.amount)},4 l5,8 h-10 z" fill="#c62828"/><line x1="${x(h.amount)}" x2="${x(h.amount)}" y1="10" y2="${H - 14}" stroke="#c62828" stroke-width="2.5"/>` : '';
    const lab = (v, t, c, anchor) => `<text x="${x(v)}" y="${H - 2}" font-size="10" fill="${c}" text-anchor="${anchor}">${esc(t)}</text>`;
    const near = h.amount && Math.abs(x(h.amount) - x(line)) < 60;
    return `<svg class="hstrip" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(L('আগের পরিমাণগুলোর তুলনায় এই পরিমাণ', 'This amount against the earlier ones'))}">
      <line x1="${pad}" x2="${W - pad}" y1="${H / 2}" y2="${H / 2}" stroke="#e3e7ee"/>${dots}${mid}${thr}${cur}
      ${lab(usual, L(`সাধারণ ${money(usual)}`, `usual ${money(usual)}`), '#0f8a5f', 'middle')}
      ${near ? '' : lab(line, L(`অস্বাভাবিক ${money(line)}+`, `unusual ${money(line)}+`), '#c2570c', 'middle')}
      ${h.amount ? lab(h.amount, money(h.amount), '#c62828', x(h.amount) > W - 40 ? 'end' : 'middle') : ''}</svg>`;
  }

  function start() {
    applyLang();
    bootScreen();
    document.querySelectorAll('iframe').forEach((f) => {           // the showcase's screens follow its language
      try { if (f.contentWindow.Prohori) f.contentWindow.Prohori.setLang(lang); } catch (e) { /* other origin */ }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();

  window.Prohori = {
    base, api, bn, ascii, esc, tk, tkbn, time, phone, speak, numDiff, habitStrip, L, n, money, setLang, applyLang,
    onLang: (f) => subs.push(f), get lang() { return lang; }, store: { get: sget, set: sset },
    embed: params.get('embed') === '1',
  };
})();
