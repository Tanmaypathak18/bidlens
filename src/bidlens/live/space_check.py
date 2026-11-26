"""Check that Kumo Tabular runs for an uploaded list on this machine, and how fast.

Usage:
    uv run python -m bidlens.live.space_check

Runs the real upload path (the example bid item list, priced by Kumo in its worker
process) three times: a first run (which also calibrates the ranges), a second run on the
same day (calibration reused), and a 1,000-row list (the upload limit). Prints the CPU
count, memory limit, disk used by the Python packages and model weights, run times and
peak memory, each line starting with SPACE_CHECK so it can be read from a server log.
"""

from __future__ import annotations

import json
import os
import resource
import sys
import time
from pathlib import Path

import pandas as pd


def _say(**kw) -> None:
    print("SPACE_CHECK " + json.dumps(kw), flush=True)


def _du(path: Path) -> float:
    if not path.exists():
        return 0.0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())  # follows links


def _memory_limit() -> float | None:
    for f in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            v = Path(f).read_text().strip()
            return None if v == "max" else float(v)
        except OSError:
            continue
    return None


def _peak_mb(who) -> float:
    kb = resource.getrusage(who).ru_maxrss
    return kb / 1024 / (1024 if sys.platform == "darwin" else 1)  # macOS reports bytes


def main() -> int:
    import site

    from bidlens.live.bundle import ROOT, load
    from bidlens.live.engine import Engine, read_upload, upload_job
    from bidlens.live.kumo_worker import cpu_quota

    pkgs = Path(site.getsitepackages()[0]) if site.getsitepackages() else None
    user = Path(site.getusersitepackages())
    hf = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    _say(
        cpus=os.cpu_count(),
        cpu_quota=cpu_quota(),
        memory_limit_gb=(m / 1e9) if (m := _memory_limit()) else None,
        packages_gb=round((_du(user) + (_du(pkgs) if pkgs else 0)) / 1e9, 2),
        torch_gb=round(max(_du(user / "torch"), _du(pkgs / "torch") if pkgs else 0) / 1e9, 2),
        weights_gb=round(_du(hf / "hub" / "models--nvidia--Kumo-Tabular" / "blobs") / 1e9, 2),
    )
    eng = Engine(load(), model="kumo")
    example = (ROOT / "data" / "sample" / "example_bid_items.csv").read_bytes()
    df = read_upload("example.csv", example)
    info = {"district": "04", "county": "ALA", "engineers_estimate": 22_700_000.0,
            "working_days": 300, "type_of_work": "TRASH CAPTURE, MGS, LIGHTING"}  # fmt: skip
    big = pd.concat([df] * 9, ignore_index=True).head(1000)
    big["item_no"] = [f"{i:04d}" for i in range(1, len(big) + 1)]
    for name, frame in (("first run, 120 items", df), ("second run, 120 items", df),
                        ("1,000 items", big)):  # fmt: skip
        job = upload_job(eng, frame, info)
        t0 = time.perf_counter()
        est, market = eng.evaluate(job)
        run = est.attrs["run"]
        _say(
            run=name,
            seconds=round(time.perf_counter() - t0, 1),
            model=est.attrs["model"],
            kumo_load_s=round(run.get("load_seconds", 0), 1),
            kumo_price_s=round(run.get("fit_seconds", 0), 1),
            calibration_s=round(run.get("cal_seconds", 0), 1) if not run.get("reused") else 0,
            context_rows=run.get("rows"),
            draft_total=round(float(est["pred_amount"].sum())),
            worker_peak_mb=round(_peak_mb(resource.RUSAGE_CHILDREN)),
            app_peak_mb=round(_peak_mb(resource.RUSAGE_SELF)),
        )
    _say(done=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
