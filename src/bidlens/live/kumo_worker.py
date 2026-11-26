"""Kumo Tabular for the live engine, in its own process.

Usage (called by `bidlens.live.engine`, not by hand):
    python -m bidlens.live.kumo_worker <job folder>

The folder holds `request.json` (cutoff date, whether to calibrate) and `query.parquet`
(the features of the items to price). The worker reads the data bundle, uses every cleaned
low bid opened before the cutoff as Kumo's context, and writes `result.parquet` (median,
10th and 90th percentile log prices) and `result.json`. With calibration, it also prices
the year before the cutoff from an older context and returns the conformal (CQR)
widening of Kumo's 10th to 90th percentile range, for lump sum and unit-priced items.

PyTorch and LightGBM each ship their own OpenMP runtime and crash when loaded into one
process on macOS, so Kumo never runs inside the app's process.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd


def cpu_quota() -> int | None:
    """CPUs this container may use (Linux cgroup quota), when it is below the CPU count.
    A hosted container can report 16 CPUs while allowed 2; PyTorch's default of one thread
    per reported CPU then spends its time throttled."""
    try:
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
    except (OSError, ValueError):
        return None
    if quota == "max":
        return None
    return max(1, round(int(quota) / int(period)))


def main(folder: str) -> int:
    import torch

    if (n := cpu_quota()) is not None:
        torch.set_num_threads(n)

    from bidlens.live.bundle import load
    from bidlens.pricing import features as F
    from bidlens.pricing.escalate import CostIndex
    from bidlens.pricing.kumo import KumoPricer
    from bidlens.pricing.ranges import conformity, cqr_adjustment
    from bidlens.pricing.setup import use_cost_index

    d = Path(folder)
    req = json.loads((d / "request.json").read_text())
    b = load()
    use_cost_index(CostIndex(b.cost_index))
    bids = b.bids
    clean = bids[~bids["low_bidder_disagrees"] & ~bids["is_outlier"] & (bids["unit_price"] > 0)]
    cutoff = pd.Timestamp(req["cutoff"])
    t0 = time.perf_counter()
    pricer = KumoPricer()
    out = {"load_seconds": time.perf_counter() - t0}

    t0 = time.perf_counter()
    ctx = clean[clean["bid_open_date"] < cutoff]
    q = pd.read_parquet(d / "query.parquet")
    pred = pricer.predict(ctx[F.FEATURES], ctx["y"], q[F.FEATURES], with_range=True)
    pd.DataFrame(pred, columns=["q50", "q10", "q90"]).to_parquet(d / "result.parquet")
    out |= {"rows": len(ctx), "fit_seconds": time.perf_counter() - t0}

    if req.get("calibrate"):
        t0 = time.perf_counter()
        start = cutoff - pd.Timedelta(days=int(req["cal_days"]))
        old = clean[clean["bid_open_date"] < start]
        held = clean[(clean["bid_open_date"] >= start) & (clean["bid_open_date"] < cutoff)]
        p = pricer.predict(old[F.FEATURES], old["y"], held[F.FEATURES], with_range=True)
        actual = np.exp(held["y"].to_numpy())
        score = conformity(np.exp(p[:, 1]), np.exp(p[:, 2]), actual)
        lump = (held["unit"] == "LS").to_numpy()
        out["adjustment"] = {
            "LS" if ls else "unit": cqr_adjustment(score[lump == ls]) for ls in (True, False)
        }
        out |= {"cal_rows": len(held), "cal_seconds": time.perf_counter() - t0}
    (d / "result.json").write_text(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
