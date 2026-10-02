"""Deploy Prohori (API + UI + trained models) to a Hugging Face Docker Space.

    pip install huggingface_hub
    hf auth login                                   # paste a token with WRITE access (or set HF_TOKEN)
    python tools/deploy_space.py --space YOUR-HF-USERNAME/prohori

    python tools/deploy_space.py --space ... --static       # FREE static Space: the models run in the visitor's
                                                            # browser (Pyodide); see tools/build_static.py
    python tools/deploy_space.py --space ... --dry-run      # build the upload folder and list it, upload nothing
    python tools/deploy_space.py --space ... --llm          # also set PROHORI_LLM=anthropic and the
                                                            # ANTHROPIC_API_KEY secret from your environment

Uploads only what the image needs: Dockerfile, pinned requirements, config.yaml, src/, ui/ and three artifacts
(about 9 MB). Never the dataset. The Space builds the Dockerfile and serves on port 8000. Binary files (.joblib,
.woff2) go through the Hub API; a plain `git push` to a Space rejects them. Re-running the script mirrors the
folder (files you deleted locally are deleted in the Space).
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ("serve_bundle.joblib", "demo_state.joblib", "demo_world.joblib")
FILES = ("Dockerfile", ".dockerignore", "requirements-serve.txt", "config.yaml")
DIRS = ("src", "ui")

SPACE_README = """---
title: Prohori
emoji: 🛡️
colorFrom: yellow
colorTo: blue
sdk: docker
app_port: 8000
pinned: false
short_description: Stops a scam transfer before money leaves the wallet
---

# প্রহরী Prohori: upay scam shield (prototype)

Track 01 (Trust & Risk Intelligence), AI Hackathon 2026, DIU CPC × upay.
**Prototype on synthetic data. Not an upay product; the wallet screens are an upay-style mock.**

Open the app: the upay-style phone is on the left, the analyst investigation copilot on the right.
- Send Money → PIN → Prohori scores the transfer live with the trained models (LightGBM + Isolation Forest +
  graph rules + a plain-code policy) and warns in Bangla with the evidence. ALLOW / NUDGE / STEP-UP / HOLD.
- The analyst sees the same alert with SHAP evidence, the money network, a four-part case report, and action
  buttons that need a person's name. Every decision is in a hash-chained audit log.
- `/ui/app.html` phone only · `/ui/analyst.html` copilot only · `/docs` API · `/health` status.

The first load after the Space wakes takes about a minute (the image starts, then the demo world is staged).
{source}
"""


def stage(dest: Path, source_url: str | None) -> list[str]:
    missing = [a for a in ARTIFACTS if not (ROOT / "artifacts" / a).exists()]
    if missing:
        sys.exit(f"missing artifacts {missing}: run `python -m src.pipeline` (or `--from export`) first")
    for f in FILES:
        shutil.copy2(ROOT / f, dest / f)
    for d in DIRS:
        shutil.copytree(ROOT / d, dest / d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.log"))
    (dest / "artifacts").mkdir()
    for a in ARTIFACTS:
        shutil.copy2(ROOT / "artifacts" / a, dest / "artifacts" / a)
    src = f"\nSource code, data generator, training pipeline and results: {source_url}\n" if source_url else ""
    (dest / "README.md").write_text(SPACE_README.format(source=src), encoding="utf-8")
    return sorted(str(p.relative_to(dest)).replace("\\", "/") for p in dest.rglob("*") if p.is_file())


def app_url(space: str, static: bool = False) -> str:
    owner, name = space.split("/", 1)
    clean = lambda s: s.lower().replace("_", "-").replace(".", "-")        # noqa: E731
    return f"https://{clean(owner)}-{clean(name)}.{'static.' if static else ''}hf.space"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--space", required=True, help="USERNAME/space-name on Hugging Face")
    ap.add_argument("--private", action="store_true", help="create the Space as private (judges then cannot open it)")
    ap.add_argument("--source", default=None, help="public GitHub URL to show in the Space README")
    ap.add_argument("--llm", action="store_true", help="enable the optional Claude wording (needs ANTHROPIC_API_KEY)")
    ap.add_argument("--static", action="store_true",
                    help="free static Space: models run in the browser (Docker Spaces need Hugging Face PRO)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.space.count("/") != 1:
        sys.exit("--space must look like USERNAME/space-name")
    if a.static and a.llm:
        sys.exit("--llm needs a server; the static build has no secrets and makes no API calls")

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        if a.static:
            sys.path.insert(0, str(ROOT / "tools"))
            from build_static import build
            shutil.rmtree(dest)
            shutil.copytree(build(a.source), dest)
            files = sorted(str(p.relative_to(dest)).replace("\\", "/") for p in dest.rglob("*") if p.is_file())
        else:
            files = stage(dest, a.source)
        size = sum((dest / f).stat().st_size for f in files) / 1e6
        print(f"{len(files)} files, {size:.1f} MB to upload")
        if a.dry_run:
            print("\n".join(f"  {f}" for f in files if not f.startswith(("src/", "ui/"))))
            print(f"  src/ ({sum(f.startswith('src/') for f in files)} files), ui/ ({sum(f.startswith('ui/') for f in files)} files)")
            print(f"dry run: nothing uploaded. The app would be at {app_url(a.space, a.static)}")
            return

        from huggingface_hub import HfApi
        api = HfApi()
        try:
            user = api.whoami()["name"]
        except Exception:
            sys.exit("not logged in to Hugging Face: run `hf auth login` (token with write access) or set HF_TOKEN")
        print(f"logged in as {user}")
        api.create_repo(a.space, repo_type="space", space_sdk="static" if a.static else "docker", exist_ok=True,
                        visibility="private" if a.private else "public")
        if a.llm:
            key = os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                sys.exit("--llm needs ANTHROPIC_API_KEY in your environment (it is stored as a Space secret)")
            api.add_space_secret(a.space, "ANTHROPIC_API_KEY", key)
            api.add_space_variable(a.space, "PROHORI_LLM", "anthropic")
        api.upload_folder(repo_id=a.space, repo_type="space", folder_path=str(dest), delete_patterns=["*"],
                          commit_message="Deploy Prohori: API, UI and trained models")
    print(f"uploaded. Space: https://huggingface.co/spaces/{a.space}  ·  app: {app_url(a.space, a.static)}")


if __name__ == "__main__":
    main()
