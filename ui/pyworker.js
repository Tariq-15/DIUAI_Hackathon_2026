/* Web Worker: runs the Prohori API inside the browser with Pyodide (CPython compiled to WebAssembly).
   The same Python code and the same trained models as the server (exported version-neutrally by
   src/serve/portable.py) answer every /api/v1 request; nothing leaves the visitor's browser. */
const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.28.3/full/';
importScripts(PYODIDE + 'pyodide.js');

let handle = null;
const say = (msg, pct) => postMessage({ type: 'progress', msg, pct });

const ready = (async () => {
  say('Python (WebAssembly) চালু হচ্ছে…', 5);
  const py = await loadPyodide({ indexURL: PYODIDE });
  say('মডেলের লাইব্রেরি নামানো হচ্ছে: numpy, pandas, LightGBM (প্রথমবার ~৫০ MB)…', 20);
  let n = 0;
  await py.loadPackage(['numpy', 'pandas', 'lightgbm', 'pyyaml'], {
    messageCallback: (m) => { if (/^Loaded/.test(m)) say('লাইব্রেরি প্রস্তুত হচ্ছে…', Math.min(65, 25 + 4 * ++n)); },
  });
  say('প্রহরী মডেল ও ডেটা নামানো হচ্ছে…', 70);
  const res = await fetch('py/prohori.zip');
  if (!res.ok) throw new Error(`py/prohori.zip: HTTP ${res.status}`);
  py.unpackArchive(await res.arrayBuffer(), 'zip', { extractDir: '/home/pyodide/prohori' });
  say('ফিচার স্টোর ও সাজানো ডেমো লোড হচ্ছে…', 85);
  py.runPython(`
import sys
sys.path.insert(0, "/home/pyodide/prohori")
from src.serve.browser import Dispatcher
D = Dispatcher("/home/pyodide/prohori/artifacts/portable")
`);
  handle = py.globals.get('D').handle;
  postMessage({ type: 'ready' });
})().catch((e) => {
  postMessage({ type: 'failed', msg: String((e && e.message) || e) });
  throw e;
});

onmessage = async (e) => {
  const { id, method, path, body } = e.data;
  try {
    await ready;
    const out = handle(method, path, body === null || body === undefined ? null : JSON.stringify(body));
    postMessage({ type: 'reply', id, ...JSON.parse(out) });
  } catch (err) {
    postMessage({ type: 'reply', id, status: 503, detail: `in-browser engine failed: ${(err && err.message) || err}` });
  }
};
