"""Step 2.5: refreshed predictions, one model library per process (decision D-045).

Usage:
    uv run python -m bidlens.pricing.refresh --model xgboost
    uv run python -m bidlens.pricing.refresh --model lightgbm
    uv run python -m bidlens.pricing.refresh --model kumo

For each test quarter, the model sees every cleaned bid opened before the quarter starts
(Kumo: as context; XGBoost and LightGBM: refit with their step 2.3 settings). It also
writes 2023 validation predictions from a model that saw only bids before 2023, which
step 2.5 uses to choose the production model (D-046). Results go to
data/interim/refresh_<model>.parquet. PyTorch and the GBM libraries never share a
process (see features.py).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from bidlens.pricing import features as F
from bidlens.pricing.escalate import CostIndex
from bidlens.pricing.setup import CUTOFF, TEST_END, use_cost_index

DB = Path("data") / "bidlens.duckdb"
OUT = Path("data") / "interim" / "refresh_{model}.parquet"
VALIDATION_START = pd.Timestamp("2023-01-01")


def _predictor(model: str):
    """A function (X_fit, y_fit, X_query) -> log price, for the given library."""
    if model == "kumo":
        from bidlens.pricing.kumo import KumoPricer

        pricer = KumoPricer()
        return lambda Xf, yf, Xq: pricer.predict(Xf, yf, Xq, with_range=True)

    from bidlens.pricing import baseline as BL

    info = json.loads(Path("outputs/10_baselines/results.json").read_text())["models"][model]
    params, trees = info["params"], int(info["trees"])

    def predict(X_fit, y_fit, X_query):
        fits = [
            BL.fit(model, BL.make_model(model, params, trees, s, False), X_fit, y_fit)
            for s in range(BL.SEED, BL.SEED + BL.N_SEEDS)
        ]
        return BL.predict_saved(fits, X_query)

    return predict


def _cols(p: np.ndarray, sl: slice = slice(None)) -> dict:
    """Prediction columns: the median, plus the 10th and 90th percentiles when present."""
    p = p.reshape(len(p), -1)[sl]
    out = {"log_ref_pred": p[:, 0]}
    if p.shape[1] == 3:
        out |= {"log_ref_q10": p[:, 1], "log_ref_q90": p[:, 2]}
    return out


def run(model: str) -> pd.DataFrame:
    con = duckdb.connect(str(DB), read_only=True)
    use_cost_index(CostIndex.from_db(con))
    rows, X, y, train_mask, test, cats = F.prepare(con)
    _, _, sel, X_lines = F.contract_lines(con, rows, cats)
    con.close()
    predict = _predictor(model)
    d = rows["bid_open_date"]
    clean = ~rows["low_bidder_disagrees"] & ~rows["is_outlier"] & (rows["unit_price"] > 0)
    out = []

    # 2023 validation, model frozen before 2023 (D-046).
    val = train_mask & (d >= VALIDATION_START)
    fit = train_mask & (d < VALIDATION_START)
    p = predict(X[fit], y[fit], X[val])
    out.append(
        pd.DataFrame(
            {
                "kind": "validation",
                "key": rows.loc[val, "bid_item_id"],
                "bid_open_date": d[val],
                **_cols(p),
            }
        )
    )

    # Test, refreshed each quarter (D-045).
    quarters = pd.period_range(pd.Timestamp(CUTOFF), pd.Timestamp(TEST_END), freq="Q")
    t_q = test["bid_open_date"].dt.to_period("Q")
    l_q = sel["bid_open_date"].dt.to_period("Q")
    timing = []
    for q in quarters:
        ti, li = test.index[t_q == q], sel.index[l_q == q]
        if len(ti) + len(li) == 0:
            continue
        fit = clean & (d < q.start_time)
        Xq = pd.concat([X.loc[ti], X_lines.loc[li]], ignore_index=True)
        t0 = time.perf_counter()
        p = predict(X[fit], y[fit], Xq)
        timing.append(time.perf_counter() - t0)
        out.append(
            pd.DataFrame(
                {
                    "kind": "test",
                    "key": rows.loc[ti, "bid_item_id"].to_numpy(),
                    "bid_open_date": test.loc[ti, "bid_open_date"].to_numpy(),
                    **_cols(p, slice(None, len(ti))),
                }
            )
        )
        keys = sel.loc[li, F.LINE_KEY]
        out.append(
            pd.DataFrame(
                {
                    "kind": "line",
                    "key": keys["contract_number"]
                    + "|"
                    + keys["bid_open_date"].dt.strftime("%Y-%m-%d")
                    + "|"
                    + keys["item_no"].astype(str),
                    "bid_open_date": keys["bid_open_date"].to_numpy(),
                    **_cols(p, slice(len(ti), None)),
                }
            )
        )
    res = pd.concat(out, ignore_index=True)
    res["pred_unit_price"] = F.from_ref(np.exp(res["log_ref_pred"]), res["bid_open_date"])
    for q in ("q10", "q90"):
        if f"log_ref_{q}" in res:
            res[f"pred_{q}"] = F.from_ref(np.exp(res[f"log_ref_{q}"]), res["bid_open_date"])
    res.attrs["seconds_per_quarter"] = float(np.mean(timing))
    path = Path(str(OUT).format(model=model))
    path.parent.mkdir(parents=True, exist_ok=True)
    res.to_parquet(path, index=False)
    Path(str(path).replace(".parquet", ".json")).write_text(
        json.dumps({"seconds_per_quarter": float(np.mean(timing)), "quarters": len(timing)})
    )
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True, choices=["xgboost", "lightgbm", "kumo"])
    args = ap.parse_args(argv)
    res = run(args.model)
    print(res.groupby("kind").size().to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
