/* Web Worker: runs the Prohori API inside the browser with Pyodide (CPython compiled to WebAssembly).
   The same Python code and the same trained models as the server (exported version-neutrally by
   src/serve/portable.py) answer every /api/v1 request; nothing leaves the visitor's browser.

   Started as a SharedWorker where the browser has one (engine.js): every tab of the demo (phone only, copilot only,
   showcase) then talks to ONE engine, so an alert raised on the phone tab appears in the copilot tab.

   Caching (so a refresh does not download everything again):
   - Pyodide and its packages: versioned CDN URLs, kept in Cache Storage ('prohori-pyodide-<version>') and read from
     there first; the HTTP cache alone gets evicted and is partitioned per site.
   - The models and code: py/prohori-<content hash>.zip (tools/build_static.py names it by its hash, engine.js passes
     the name). Kept in Cache Storage ('prohori-models') under that name: a new deploy has a new name, so a stale
     copy can never be served, and old copies are deleted. This matters on Hugging Face, which answers the zip with a
     redirect to a fresh signed URL marked no-store: without this the 6 MB came down on every refresh.
   - scikit-learn is not loaded: LightGBM only needs it for its scikit-learn wrapper, which serving does not use. */
const PYODIDE_VERSION = '0.28.3';
const PYODIDE = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const CDN_CACHE = `prohori-pyodide-${PYODIDE_VERSION}`;
const MODEL_CACHE = 'prohori-models';
const params = new URLSearchParams(self.location.search);
const ZIP = params.get('zip') || 'py/prohori.zip';
const T = (bn, en) => ({ bn, en });                 // every tab picks its own language (shared worker)

const ports = new Set();
let state = { type: 'progress', msg: T('শুরু হচ্ছে…', 'Starting…'), pct: 0, cached: null };
const shared = typeof SharedWorkerGlobalScope !== 'undefined' && self instanceof SharedWorkerGlobalScope;
const send = (port, m) => { if (port) port.postMessage(m); else postMessage(m); };
// a shared worker starts before its first tab connects: the state is kept and handed to each tab on connect
const broadcast = (m) => { if (shared) ports.forEach((p) => p.postMessage(m)); else postMessage(m); };
const say = (msg, pct) => { state = { ...state, type: 'progress', msg, pct }; broadcast(state); };

// ---------------------------------------------------------------- Cache Storage, read first, for the Pyodide CDN
const hasCaches = typeof caches !== 'undefined';
let fromCache = 0, fromNet = 0;
if (hasCaches) {
  const netFetch = self.fetch.bind(self);
  self.fetch = async (input, init) => {
    const url = String(typeof Request !== 'undefined' && input instanceof Request ? input.url : input);   // string or URL
    if (!url.startsWith(PYODIDE)) return netFetch(input, init);
    try {
      const c = await caches.open(CDN_CACHE);
      const hit = await c.match(url);
      if (hit) { fromCache++; return hit; }
      const res = await netFetch(input, init);
      if (res.ok) { fromNet++; c.put(url, res.clone()).catch(() => {}); }
      return res;
    } catch (e) { return netFetch(input, init); }
  };
}

async function modelZip() {
  const key = new URL(ZIP, self.location.href).href;
  let c = null;
  if (hasCaches) {
    try {
      c = await caches.open(MODEL_CACHE);
      const hit = await c.match(key);
      if (hit) return { buf: await hit.arrayBuffer(), cached: true };
    } catch (e) { c = null; }
  }
  const res = await fetch(ZIP);
  if (!res.ok) throw new Error(`${ZIP}: HTTP ${res.status}`);
  const buf = await res.arrayBuffer();
  if (c) {
    try {
      await c.put(key, new Response(buf.slice(0), { headers: { 'Content-Type': 'application/zip' } }));
      for (const k of await c.keys()) if (k.url !== key) await c.delete(k);      // older builds
    } catch (e) { /* storage full or blocked: still works, just downloads next time */ }
  }
  return { buf, cached: false };
}

let handle = null;
const ready = (async () => {
  let warm = false;
  if (hasCaches) {
    try { warm = !!(await (await caches.open(CDN_CACHE)).match(PYODIDE + 'pyodide.asm.wasm')); } catch (e) { warm = false; }
  }
  state.cached = warm;
  say(warm ? T('এই ডিভাইসের ক্যাশ থেকে চালু হচ্ছে (কিছু নামাতে হবে না)…', 'Starting from this device\'s cache (nothing to download)…')
    : T('Python (WebAssembly) চালু হচ্ছে…', 'Starting Python (WebAssembly)…'), 5);
  importScripts(PYODIDE + 'pyodide.js');
  const py = await loadPyodide({ indexURL: PYODIDE });
  say(warm ? T('লাইব্রেরি প্রস্তুত হচ্ছে…', 'Preparing the libraries…')
    : T('মডেলের লাইব্রেরি নামানো হচ্ছে: numpy, pandas, SciPy, LightGBM (প্রথমবার ~৩০ MB)…', 'Downloading the model libraries: numpy, pandas, SciPy, LightGBM (first visit ~30 MB)…'), 20);
  let n = 0;
  const messageCallback = (m) => { if (/^Loaded/.test(m)) say(T('লাইব্রেরি প্রস্তুত হচ্ছে…', 'Preparing the libraries…'), Math.min(62, 25 + 4 * ++n)); };
  await py.loadPackage(['numpy', 'pandas', 'pyyaml', 'scipy', 'joblib'], { messageCallback });
  let lgbm = 'lightgbm';
  try {                                               // by file name: Pyodide then does not pull in scikit-learn
    const lock = await (await fetch(PYODIDE + 'pyodide-lock.json')).json();
    if (lock.packages && lock.packages.lightgbm) lgbm = PYODIDE + lock.packages.lightgbm.file_name;
  } catch (e) { /* fall back to the name (also loads scikit-learn) */ }
  await py.loadPackage([lgbm], { messageCallback });
  say(T('প্রহরী মডেল ও ডেটা লোড হচ্ছে…', 'Loading the Prohori models and data…'), 70);
  const zip = await modelZip();
  py.unpackArchive(zip.buf, 'zip', { extractDir: '/home/pyodide/prohori' });
  say(T('ফিচার স্টোর ও সাজানো ডেমো লোড হচ্ছে…', 'Loading the feature store and the staged demo…'), 85);
  py.runPython(`
import sys
sys.path.insert(0, "/home/pyodide/prohori")
from src.serve.browser import Dispatcher
D = Dispatcher("/home/pyodide/prohori/artifacts/portable")
`);
  handle = py.globals.get('D').handle;
  state = { type: 'ready', cached: warm && zip.cached, fromCache, fromNet };
  broadcast(state);
})().catch((e) => {
  state = { type: 'failed', msg: String((e && e.message) || e) };
  broadcast(state);
  throw e;
});

async function answer(e, port) {
  const { id, method, path, body } = e.data;
  try {
    await ready;
    const out = handle(method, path, body === null || body === undefined ? null : JSON.stringify(body));
    send(port, { type: 'reply', id, ...JSON.parse(out) });
  } catch (err) {
    send(port, { type: 'reply', id, status: 503, detail: `in-browser engine failed: ${(err && err.message) || err}` });
  }
}

// dedicated worker: one page; shared worker: every tab that connects, each told the current start-up state
self.onmessage = (e) => answer(e, null);
self.onconnect = (e) => {
  const port = e.ports[0];
  ports.add(port);
  port.onmessage = (m) => (m.data && m.data.type === 'bye' ? ports.delete(port) : answer(m, port));
  port.start();
  port.postMessage(state);
};
