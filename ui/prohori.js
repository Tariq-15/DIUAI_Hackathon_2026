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
  let lang = ['bn', 'en'].includes(params.get('lang')) ? params.get('lang')
    : (sget(LKEY) || document.documentElement.dataset.lang || 'bn');
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
    el.innerHTML = `<div class="boot-card"><div class="spin"></div><b>${L('প্রহরী চালু হচ্ছে', 'Starting Prohori')}</b>
      <div class="small" id="boot-msg"></div><div class="boot-bar"><i id="boot-bar"></i></div>
      <p class="small muted">${L('প্রশিক্ষিত মডেলগুলো আপনার ব্রাউজারের ভেতরেই চলে (Pyodide / WebAssembly): কোনো সার্ভার নেই, আপনি যা লেখেন তা এই ডিভাইস থেকে কোথাও যায় না। প্রথমবার প্রায় ৫০ MB নামবে; পরে ব্রাউজারের ক্যাশ থেকে চালু হবে।',
    'The trained models run inside your browser (Pyodide / WebAssembly): no server, and nothing you type leaves this device. The first visit downloads about 50 MB; later visits load from the browser cache.')}</p></div>`;
    document.body.appendChild(el);
    eng.onState((s) => {
      const m = el.querySelector('#boot-msg');
      if (m) m.textContent = s.failed ? `${L('চালু করা যায়নি', 'Could not start')}: ${s.failed}` : s.msg;
      const b = el.querySelector('#boot-bar');
      if (b) b.style.width = `${s.pct || 0}%`;
      if (s.ready) el.remove();
    });
  }
  function start() { applyLang(); bootScreen(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();

  window.Prohori = {
    base, api, bn, ascii, esc, tk, tkbn, time, phone, speak, numDiff, L, n, money, setLang, applyLang,
    onLang: (f) => subs.push(f), get lang() { return lang; }, store: { get: sget, set: sset },
    embed: params.get('embed') === '1',
  };
})();
