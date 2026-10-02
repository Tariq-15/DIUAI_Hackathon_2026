"""Build the server-less site: the real models run in the visitor's browser (Pyodide / WebAssembly).

    python tools/build_static.py            # -> site/  (serve it from any static host, e.g. a free Hugging Face static Space)
    python -m http.server -d site 8080      # try it locally: http://localhost:8080

site/ = the same ui/ pages + config.js in 'browser' mode + py/prohori.zip (the Python package and the portable
models from src/serve/portable.py). Pyodide and its packages (numpy, pandas, LightGBM) come from the jsDelivr CDN.
"""
from __future__ import annotations

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
does. Nothing you type leaves your device. The first visit downloads about 50 MB (cached afterwards).

- `index.html`: the upay-style phone and the analyst investigation copilot side by side
- `app.html`: phone only · `analyst.html`: copilot only
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
    (SITE / "config.js").write_text("/* static build: the models run in the browser (Pyodide) */\nwindow.PROHORI_MODE = 'browser';\n",
                                    encoding="utf-8")
    (SITE / "py").mkdir()
    with zipfile.ZipFile(SITE / "py" / "prohori.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted((ROOT / "src").rglob("*.py")):
            z.write(p, p.relative_to(ROOT).as_posix())
        z.write(ROOT / "config.yaml", "config.yaml")
        for p in sorted(PORTABLE.iterdir()):
            stored = p.suffix in (".gz", ".npz")
            z.write(p, p.relative_to(ROOT).as_posix(), compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED)
    src = f"\nSource code, data generator, training pipeline and results: {source_url}\n" if source_url else ""
    (SITE / "README.md").write_text(SPACE_README.format(source=src), encoding="utf-8")
    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file()) / 1e6
    print(f"[static] {SITE} ({size:.1f} MB; Pyodide and its packages load from the CDN)")
    return SITE


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else None)
