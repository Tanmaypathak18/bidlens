"""Deploy the demo to a private Hugging Face Space (step 4.4).

Usage:
    uv run python scripts/deploy_space.py --dry-run   # build build/space/ only
    uv run python scripts/deploy_space.py             # build and upload (private Space)
    uv run python scripts/deploy_space.py --check     # also run the Kumo check at startup

The Space ships the committed sample and the compact data bundle the live engine runs on
(no database, no bid PDFs). Listed jobs read the track record's saved Kumo prices from the
bundle; uploaded lists run Kumo Tabular small live on the Space's CPU (PyTorch CPU build,
weights fetched from Hugging Face when the image is built). It uses
the Hugging Face account this computer is signed in to (`uv run hf auth whoami`).
"""

from __future__ import annotations

import argparse
import json
import shutil
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build" / "space"
PACKAGES = ("streamlit", "pandas", "pyarrow", "openpyxl", "altair", "numpy", "lightgbm", "duckdb",
            "beautifulsoup4", "structured-data-models", "huggingface-hub")  # fmt: skip
TORCH_INDEX = "https://download.pytorch.org/whl/cpu"  # CPU-only build: no CUDA libraries
KUMO_FILES = ("config.json", "small/regressor.pt")
COPY = {
    "app": "app",
    "src/bidlens": "src/bidlens",
    "data/sample/app": "data/sample/app",
    "data/sample/engine": "data/sample/engine",
    "data/sample/example_bid_items.csv": "data/sample/example_bid_items.csv",
    "outputs/13_model_comparison/contract_totals_refreshed.csv": "outputs/13_model_comparison/contract_totals_refreshed.csv",
    "outputs/22_live_evaluation/results.json": "outputs/22_live_evaluation/results.json",
    ".streamlit/config.toml": ".streamlit/config.toml",
    "outputs/13_model_comparison/results.json": "outputs/13_model_comparison/results.json",
    "outputs/15_market_context/results.json": "outputs/15_market_context/results.json",
    "LICENSE": "LICENSE",
}
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")

DOCKERFILE = """FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \\
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONPATH=/home/user/app/src \\
    HF_HOME=/home/user/.cache/huggingface
WORKDIR /home/user/app
RUN pip install --no-cache-dir --user torch=={torch} --index-url {index}
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
RUN python -c "from huggingface_hub import hf_hub_download as get; \\
[get('nvidia/Kumo-Tabular', f, revision='v1.0.1') for f in {files}]"
COPY --chown=user . .
EXPOSE 7860
CMD {cmd}
"""
STREAMLIT = "streamlit run app/Home.py --server.port 7860 --server.address 0.0.0.0"

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
- **Evaluate** any of about 200 Caltrans jobs bid in 2024 to 2026, or upload your own bid
  item list (CSV or Excel). If your list has unit prices, BidLens checks each one against
  its range.
- Listed jobs open instantly: their prices are the ones in the track record, computed ahead
  of time with NVIDIA Kumo Tabular on a laptop, so every total matches the published
  results. An uploaded list is priced live by Kumo Tabular on this free CPU, which takes
  about 1 to 3 minutes.
- Uploads are read in memory and never saved.
- Document findings for the sample job 04-0W0504 were pre-computed on a laptop with local
  models (qwen3:8b and llama3.1:8b through Ollama, plus plain pattern rules).
- No bidder is named anywhere: bids are identified by rank only.

Source code, method and results: https://github.com/Tanmaypathak18/bidlens
"""


def locked(name: str) -> str:
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    return next(p["version"] for p in lock["package"] if p["name"] == name)


def dockerfile(check: bool) -> str:
    cmd = (
        f'["sh", "-c", "python -m bidlens.live.space_check & exec {STREAMLIT}"]'
        if check
        else json.dumps(STREAMLIT.split())
    )
    return DOCKERFILE.format(torch=locked("torch"), index=TORCH_INDEX, files=KUMO_FILES, cmd=cmd)


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


def build(check: bool = False) -> Path:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    for src, dst in COPY.items():
        s, d = ROOT / src, BUILD / dst
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.is_dir():
            shutil.copytree(s, d, ignore=IGNORE)
        else:
            shutil.copy2(s, d)
    (BUILD / "Dockerfile").write_text(dockerfile(check))
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
    ap.add_argument("--check", action="store_true", help="run the Kumo check at startup")
    args = ap.parse_args()
    folder = build(args.check)
    size = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
    print(f"Built {folder.relative_to(ROOT)} ({size / 1e6:.1f} MB)")
    if not args.dry_run:
        print("Space:", upload(folder, args.name))


if __name__ == "__main__":
    main()
