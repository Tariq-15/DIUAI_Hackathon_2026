/* In-browser engine for static hosting (window.PROHORI_MODE === 'browser', set by config.js).
   One Pyodide worker per top-level page; pages embedded in the showcase share their parent's engine, so an
   alert raised on the phone appears in the analyst copilot. In server mode this file does nothing. */
(function () {
  if (window.PROHORI_MODE !== 'browser') return;
  try {
    if (window.parent !== window && window.parent.ProhoriEngine) {
      window.ProhoriEngine = window.parent.ProhoriEngine;
      return;
    }
  } catch (e) { /* cross-origin parent: start our own */ }

  const worker = new Worker('pyworker.js');
  const waiting = new Map();
  const listeners = new Set();
  let seq = 0;
  let state = { ready: false, failed: null, msg: 'শুরু হচ্ছে…', pct: 0 };
  const notify = () => listeners.forEach((f) => { try { f(state); } catch (e) { listeners.delete(f); } });

  worker.onmessage = (e) => {
    const m = e.data;
    if (m.type === 'progress') { state = { ...state, msg: m.msg, pct: m.pct }; notify(); }
    else if (m.type === 'ready') { state = { ...state, ready: true, pct: 100 }; notify(); }
    else if (m.type === 'failed') { state = { ...state, failed: m.msg }; notify(); }
    else if (m.type === 'reply') {
      const done = waiting.get(m.id);
      if (done) { waiting.delete(m.id); done(m); }
    }
  };
  worker.onerror = (e) => { state = { ...state, failed: e.message || 'worker error' }; notify(); };

  window.ProhoriEngine = {
    call(method, path, body) {
      return new Promise((resolve) => {
        const id = ++seq;
        waiting.set(id, resolve);
        worker.postMessage({ id, method, path, body: body === undefined ? null : body });
      });
    },
    onState(f) { listeners.add(f); f(state); return () => listeners.delete(f); },
    get state() { return state; },
  };
})();
