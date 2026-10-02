/* In-browser engine for static hosting (window.PROHORI_MODE === 'browser', set by config.js).
   One Pyodide engine for the whole demo:
   - pages embedded in the showcase use their parent's engine (an alert raised on the phone appears in the copilot)
   - separate tabs (phone only, copilot only, showcase) share one SharedWorker where the browser has it (desktop
     Chrome, Edge, Firefox, Safari), so the copilot tab sees what the phone tab does; otherwise each tab starts its own
   - the worker keeps Pyodide and the models in Cache Storage (ui/pyworker.js), so a refresh does not download again
   In server mode this file does nothing. */
(function () {
  if (window.PROHORI_MODE !== 'browser') return;
  try {
    if (window.parent !== window && window.parent.ProhoriEngine) {
      window.ProhoriEngine = window.parent.ProhoriEngine;
      return;
    }
  } catch (e) { /* cross-origin parent: start our own */ }

  const build = window.PROHORI_BUILD || {};              // {v, zip} written by tools/build_static.py
  const url = `pyworker.js?v=${encodeURIComponent(build.v || 'dev')}&zip=${encodeURIComponent(build.zip || 'py/prohori.zip')}`;
  const waiting = new Map();
  const listeners = new Set();
  let seq = 0;
  let state = { ready: false, failed: null, msg: { bn: 'শুরু হচ্ছে…', en: 'Starting…' }, pct: 0, cached: null, shared: false };
  const notify = () => listeners.forEach((f) => { try { f(state); } catch (e) { listeners.delete(f); } });
  const fail = (msg) => { state = { ...state, failed: msg }; notify(); };

  let port = null;
  function onMessage(e) {
    const m = e.data;
    if (m.type === 'progress') { state = { ...state, msg: m.msg, pct: m.pct, cached: m.cached }; notify(); }
    else if (m.type === 'ready') { state = { ...state, ready: true, failed: null, pct: 100, cached: m.cached }; notify(); }
    else if (m.type === 'failed') { if (state.shared) dedicated(); else fail(m.msg); }
    else if (m.type === 'reply') {
      const w = waiting.get(m.id);
      if (w) { waiting.delete(m.id); w.done(m); }
    }
  }
  // this tab's own engine; also the fallback when the shared one fails to start
  function dedicated() {
    if (port) port.onmessage = null;                  // ignore whatever the failed engine still answers
    state = { ...state, shared: false, ready: false, failed: null };
    const w = new Worker(url);
    w.onerror = (e) => fail((e && e.message) || 'worker error');
    w.onmessage = onMessage;
    port = w;
    waiting.forEach((x) => port.postMessage(x.msg));  // requests already made go to the new engine
  }
  if (typeof SharedWorker === 'function' && !/[?&]shared=0\b/.test(location.search)) {
    try {
      const sw = new SharedWorker(url, { name: `prohori-${build.v || 'dev'}` });
      sw.onerror = () => { if (state.shared) dedicated(); };
      port = sw.port;
      state.shared = true;
      port.onmessage = onMessage;
      port.start();
    } catch (e) { port = null; }
  }
  if (!port) dedicated();
  // a shared engine that stops making progress (e.g. stuck in another tab) is replaced by this tab's own
  let seen = Date.now(), lastPct = -1;
  const watch = setInterval(() => {
    if (state.ready || state.failed || !state.shared) { clearInterval(watch); return; }
    if (state.pct !== lastPct) { lastPct = state.pct; seen = Date.now(); } else if (Date.now() - seen > 120000) dedicated();
  }, 5000);

  window.ProhoriEngine = {
    call(method, path, body) {
      return new Promise((resolve) => {
        const msg = { id: ++seq, method, path, body: body === undefined ? null : body };
        waiting.set(msg.id, { done: resolve, msg });
        port.postMessage(msg);
      });
    },
    onState(f) { listeners.add(f); f(state); return () => listeners.delete(f); },
    get state() { return state; },
  };
})();
