"""The committed app sample, so a fresh clone runs the app (decision D-069).

Usage:
    uv run python -m bidlens.sample 04-0W0504   # writes data/sample/app/<contract>/

Copies the prepared app files, the closure charts and the default extraction run's findings
(contacts masked; rejected answers and call logs left out). No bidder names: rank only.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INTERIM = ROOT / "data" / "interim"
SAMPLE = ROOT / "data" / "sample" / "app"
APP_FILES = ("summary.json", "estimate.parquet", "comparables.parquet", "history.parquet")


def app_dir(contract: str, root: Path = ROOT) -> Path:
    """Prepared app files: `data/interim/app/` first, else the committed sample."""
    built = root / "data" / "interim" / "app" / contract
    return (
        built if (built / "summary.json").exists() else root / "data" / "sample" / "app" / contract
    )


def docs_dir(contract: str, root: Path = ROOT) -> Path:
    """Parsed documents and extraction runs: `data/interim/docs/` first, else the sample."""
    built = root / "data" / "interim" / "docs" / contract
    return built if built.exists() else root / "data" / "sample" / "app" / contract


def write_sample(contract: str) -> Path:
    import pandas as pd

    from bidlens.documents.extract import DEFAULT_RUN
    from bidlens.documents.report import mask

    out = SAMPLE / contract
    out.mkdir(parents=True, exist_ok=True)
    for name in APP_FILES:
        shutil.copy2(INTERIM / "app" / contract / name, out / name)
    shutil.copy2(INTERIM / "docs" / contract / "charts.parquet", out / "charts.parquet")
    run = json.loads((INTERIM / "docs" / contract / f"extraction_{DEFAULT_RUN}.json").read_text())
    items = mask(pd.DataFrame(run["items"])).to_dict("records")
    kept = {k: run[k] for k in ("contract", "mode", "model") if k in run}
    (out / f"extraction_{DEFAULT_RUN}.json").write_text(
        json.dumps({**kept, "items": items}, indent=1)
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("contract")
    out = write_sample(ap.parse_args().contract)
    total = sum(p.stat().st_size for p in out.iterdir())
    print(f"Wrote {out.relative_to(ROOT)} ({total / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
