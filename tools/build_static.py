"""Build the server-less site: the real models run in the visitor's browser (Pyodide / WebAssembly).

    python tools/build_static.py            # -> site/  (serve it from any static host, e.g. a free Hugging Face static Space)
    python -m http.server -d site 8080      # try it locally: http://localhost:8080

site/ = the same ui/ pages + config.js in 'browser' mode + py/prohori-<hash>.zip (the Python package and the
portable models from src/serve/portable.py). Pyodide and its packages (numpy, pandas, SciPy, LightGBM) come from
the jsDelivr CDN.

Caching, so a refresh is fast and a new deploy is never hidden behind an old copy:
  - the zip is named by its content hash; the in-browser worker keeps it in Cache Storage under that name and
    deletes older ones (ui/pyworker.js). Same name = same bytes, so it is safe to read it from the cache first.
  - config.js carries the build id and the zip name; every page loads its scripts and styles with ?v=<build id>,
    so after a deploy the browser fetches the new files instead of reusing old ones.
"""
from __future__ import annotations

import hashlib
import io
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PORTABLE = ROOT / "artifacts" / "portable"

SPACE_README = """---
title: Prohori
emoji: 🛡️
colorFrom: yellow
colorTo: blue
sdk: static
app_file: index.html
pinned: false
short_description: Stops a scam transfer before money leaves the wallet
---

# প্রহরী Prohori: upay scam shield (prototype)

Track 01 (Trust & Risk Intelligence), AI Hackathon 2026, DIU CPC × upay.
**Prototype on synthetic data. Not an upay product; the wallet screens are an upay-style mock.**

The trained models run **inside your browser**: Pyodide (Python compiled to WebAssembly) loads LightGBM, the
Isolation Forest, the graph features and the plain-code policy, and answers the same API the server version
does. Nothing you type leaves your device. The first visit downloads about 30 MB and keeps it on the device;
a refresh starts from that copy (nothing is downloaded again).

- `index.html`: the upay-style phone and the analyst investigation copilot side by side (switch to phone only or
  copilot only in the header; 🧪 Test numbers lists numbers from the dataset to try)
- `app.html`: phone only · `analyst.html`: copilot only (in separate tabs they share one engine where the browser
  supports SharedWorker)
{source}
"""


def build(source_url: str | None = None) -> Path:
    if not (PORTABLE / "world.pkl.gz").exists():
        sys.path.insert(0, str(ROOT))
        from src.serve.portable import export
        export()
    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(ROOT / "ui", SITE, ignore=shutil.ignore_patterns("config.js"))
    (SITE / "py").mkdir()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        files = [(p, p.relative_to(ROOT).as_posix()) for p in sorted((ROOT / "src").rglob("*.py"))]
        files += [(ROOT / "config.yaml", "config.yaml")] + [(p, p.relative_to(ROOT).as_posix()) for p in sorted(PORTABLE.iterdir())]
        for p, name in files:                      # fixed timestamps: the same inputs give the same bytes (and hash)
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if p.suffix in (".gz", ".npz") else zipfile.ZIP_DEFLATED
            z.writestr(info, p.read_bytes())
    data = buf.getvalue()
    zname = f"prohori-{hashlib.sha256(data).hexdigest()[:12]}.zip"
    (SITE / "py" / zname).write_bytes(data)
    ui = hashlib.sha256(data)
    for p in sorted((ROOT / "ui").rglob("*")):
        if p.is_file() and p.name != "config.js":
            ui.update(p.read_bytes())
    build_id = ui.hexdigest()[:10]
    (SITE / "config.js").write_text("/* static build: the models run in the browser (Pyodide) */\n"
                                    "window.PROHORI_MODE = 'browser';\n"
                                    f"window.PROHORI_BUILD = {{ v: '{build_id}', zip: 'py/{zname}' }};\n", encoding="utf-8")
    for page in SITE.glob("*.html"):               # versioned scripts and styles: a deploy is never served stale
        html = page.read_text(encoding="utf-8")
        html = re.sub(r'(src|href)="([\w-]+\.(?:js|css))"', lambda m: f'{m.group(1)}="{m.group(2)}?v={build_id}"', html)
        page.write_text(html, encoding="utf-8")
    src = f"\nSource code, data generator, training pipeline and results: {source_url}\n" if source_url else ""
    (SITE / "README.md").write_text(SPACE_README.format(source=src), encoding="utf-8")
    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file()) / 1e6
    print(f"[static] {SITE} ({size:.1f} MB, build {build_id}, py/{zname}; Pyodide and its packages load from the CDN)")
    return SITE


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else None)
