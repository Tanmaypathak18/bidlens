"""Deploy the demo to a private Hugging Face Space (step 4.4).

Usage:
    uv run python scripts/deploy_space.py --dry-run   # build build/space/ only
    uv run python scripts/deploy_space.py             # build and upload (private Space)

The Space ships the committed sample only: no database, no bid PDFs, no models. It uses
the Hugging Face account this computer is signed in to (`uv run hf auth whoami`).
"""

from __future__ import annotations

import argparse
import shutil
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build" / "space"
PACKAGES = ("streamlit", "pandas", "pyarrow", "openpyxl", "altair", "numpy")
COPY = {
    "app": "app",
    "src/bidlens": "src/bidlens",
    "data/sample/app": "data/sample/app",
    ".streamlit/config.toml": ".streamlit/config.toml",
    "outputs/13_model_comparison/results.json": "outputs/13_model_comparison/results.json",
    "outputs/15_market_context/results.json": "outputs/15_market_context/results.json",
    "LICENSE": "LICENSE",
}
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")

DOCKERFILE = """FROM python:3.12-slim
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONPATH=/home/user/app/src
WORKDIR /home/user/app
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
COPY --chown=user . .
EXPOSE 7860
CMD ["streamlit", "run", "app/Home.py", "--server.port", "7860", "--server.address", "0.0.0.0"]
"""

README = """---
title: BidLens
emoji: 📐
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Estimating copilot demo on a public Caltrans bid package
---

# BidLens demo

BidLens is an estimating copilot for heavy civil bids, built on public Caltrans bid data.
This demo runs on one sample package, Caltrans contract 04-0W0504, which has already been
bid, so the draft can be checked against the real result.

- Prices, ranges and market context were computed from Caltrans bids opened before this
  job and saved with the sample.
- Document findings were pre-computed on a laptop with local models (qwen3:8b and
  llama3.1:8b through Ollama, plus plain pattern rules). This Space shows the saved
  results; it does not run a model, and no bid documents are uploaded.
- No bidder is named anywhere: bids are identified by rank only.
"""


def requirements() -> str:
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    versions = {}
    for p in lock["package"]:
        if p["name"] in PACKAGES:
            versions.setdefault(p["name"], p["version"])
    missing = set(PACKAGES) - set(versions)
    if missing:
        raise SystemExit(f"not in uv.lock: {sorted(missing)}")
    # Several numpy builds can be locked (one per Python version); take the newest.
    numpy = max((p["version"] for p in lock["package"] if p["name"] == "numpy"),
                key=lambda v: tuple(int(x) for x in v.split(".")))  # fmt: skip
    versions["numpy"] = numpy
    return "".join(f"{n}=={versions[n]}\n" for n in PACKAGES)


def build() -> Path:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    for src, dst in COPY.items():
        s, d = ROOT / src, BUILD / dst
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.is_dir():
            shutil.copytree(s, d, ignore=IGNORE)
        else:
            shutil.copy2(s, d)
    (BUILD / "Dockerfile").write_text(DOCKERFILE)
    (BUILD / "requirements.txt").write_text(requirements())
    (BUILD / "README.md").write_text(README)
    return BUILD


def upload(folder: Path, name: str) -> str:
    from huggingface_hub import HfApi

    api = HfApi()
    repo_id = f"{api.whoami()['name']}/{name}"
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", private=True, exist_ok=True)
    api.upload_folder(
        folder_path=str(folder),
        repo_id=repo_id,
        repo_type="space",
        commit_message="Deploy BidLens demo (sample data only)",
        delete_patterns=["app/**", "src/**", "data/**", "outputs/**"],  # drop stale files
    )
    return f"https://huggingface.co/spaces/{repo_id}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="build the bundle only")
    ap.add_argument("--name", default="bidlens", help="Space name under your account")
    args = ap.parse_args()
    folder = build()
    size = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
    print(f"Built {folder.relative_to(ROOT)} ({size / 1e6:.1f} MB)")
    if not args.dry_run:
        print("Space:", upload(folder, args.name))


if __name__ == "__main__":
    main()
