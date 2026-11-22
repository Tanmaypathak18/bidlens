"""Step 2.7: market context for a contract.

Usage:
    uv run python -m bidlens.market.context    # writes outputs/15_market_context

Two questions an estimator asks before bidding:
- spread: how far below (or above) the engineer's estimate is the low bid likely to be?
- bidders: how many contractors are likely to bid?

Methods: Kumo Tabular (with an 80% range), a linear model and the trailing 12-month median,
each refreshed every quarter on the contracts opened before it. PyTorch loads only
when Kumo runs, and this module never imports XGBoost or LightGBM (see pricing/features.py).
"""

from __future__ import annotations

import argparse
import json
import warnings
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from bidlens.pricing.features import WORK_TYPES, work_type_flags
from bidlens.pricing.setup import CUTOFF, TEST_END

ROOT = Path(".")
DB = ROOT / "data" / "bidlens.duckdb"
OUT = ROOT / "outputs" / "15_market_context"
VALIDATION_START = pd.Timestamp("2023-01-01")
START = pd.Timestamp("2018-01-01")
TARGETS = {"spread": "Low bid vs engineer's estimate", "bidders": "Number of bidders"}
CATEGORICAL = ["district", "county"]
NUMERIC = [
    "log_engineers_estimate",
    "log_working_days",
    "n_items",
    "is_a_plus_b",
    "bid_quarter",
    "months_since_2018",
    *WORK_TYPES,
    "proposals_issued",
    "recent_spread",
    "recent_bidders",
    "recent_spread_district",
    "recent_bidders_district",
]
NO_PLANHOLDERS = [c for c in NUMERIC if c != "proposals_issued"]
COVERAGE = 0.80
LAMBDA = 1.0
SEED = 0


# ----------------------------------------------------------------- data


def load(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    df = con.execute(
        """
        SELECT contract_id, contract_number, bid_open_date, district, county, type_of_work,
               n_items, working_days, proposals_issued, is_a_plus_b,
               CAST(engineers_estimate AS DOUBLE) AS engineers_estimate,
               CAST(low_bid_cost AS DOUBLE) AS low_bid_cost, n_bidders
        FROM contract
        WHERE has_bid_summary AND engineers_estimate > 0 AND low_bid_cost > 0
          AND n_bidders IS NOT NULL
        ORDER BY bid_open_date, contract_id
        """
    ).df()
    df["bid_open_date"] = pd.to_datetime(df["bid_open_date"])
    df["spread"] = (df["low_bid_cost"] - df["engineers_estimate"]) / df["engineers_estimate"]
    df["bidders"] = df["n_bidders"].astype(float)
    return df.reset_index(drop=True)


def _recent(df: pd.DataFrame, col: str, by_district: bool) -> np.ndarray:
    """Median of `col` over contracts opened in the 12 months before each contract."""
    out = np.full(len(df), np.nan)
    d = df["bid_open_date"].to_numpy()
    for i, (on, dist) in enumerate(zip(d, df["district"], strict=True)):
        m = (d < on) & (d >= on - np.timedelta64(365, "D"))
        if by_district:
            m &= (df["district"] == dist).to_numpy()
        if m.sum():
            out[i] = np.median(df.loc[m, col])
    return out


def features(df: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=df.index)
    X["district"] = df["district"].astype(str)
    X["county"] = df["county"].fillna("<missing>").astype(str)
    X["log_engineers_estimate"] = np.log(df["engineers_estimate"])
    X["log_working_days"] = np.log(df["working_days"].astype(float))
    X["n_items"] = df["n_items"].astype(float)
    X["is_a_plus_b"] = df["is_a_plus_b"].astype(float)
    X["bid_quarter"] = df["bid_open_date"].dt.quarter.astype(float)
    X["months_since_2018"] = (
        (df["bid_open_date"].dt.year - START.year) * 12 + df["bid_open_date"].dt.month - START.month
    ).astype(float)
    X = X.join(work_type_flags(df["type_of_work"]))
    X["proposals_issued"] = df["proposals_issued"].astype(float)
    for col in ("spread", "bidders"):
        X[f"recent_{col}"] = _recent(df, col, False)
        X[f"recent_{col}_district"] = _recent(df, col, True)
    return X


# ----------------------------------------------------------------- methods


class Kumo:
    def __init__(self) -> None:
        import sdm

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.model = sdm.models.KumoTabular(task="regression", size="small", device="cpu")

    def predict(self, Xc, yc, Xq, cols) -> np.ndarray:
        """Columns: q10, q50, q90."""
        import sdm
        import torch

        use = CATEGORICAL + cols
        df = pd.concat(
            [Xc[use].assign(target=np.asarray(yc, float)), Xq[use].assign(target=0.0)],
            ignore_index=True,
        )
        st = sdm.infer_stypes(df, overrides={c: sdm.Stype.categorical for c in CATEGORICAL})
        tab = sdm.TableTensor.from_pandas(df, stypes=st, device="cpu")
        n = len(Xc)
        with warnings.catch_warnings(), torch.no_grad():
            warnings.simplefilter("ignore")
            out = self.model(
                x_context=tab[:n].drop_columns("target"),
                y_context=tab[:n]["target"],
                x_query=tab[n:].drop_columns("target"),
                generator=torch.Generator().manual_seed(SEED),
            )
        return np.column_stack(
            [out[q].numerical.squeeze(-1).numpy() for q in ("q100", "q500", "q900")]
        )


def linear(Xc, yc, Xq, cols) -> np.ndarray:
    """Ridge-regularized least squares on standardized features plus a district dummy."""

    def design(X, med, mu, sd):
        Z = (X[cols].fillna(med) - mu) / sd
        Z["district_05"] = (X["district"] == "05").astype(float)
        Z["const"] = 1.0
        return Z.to_numpy(dtype=float)

    med = Xc[cols].median()
    filled = Xc[cols].fillna(med)
    mu, sd = filled.mean(), filled.std().replace(0, 1).fillna(1)
    A, B = design(Xc, med, mu, sd), design(Xq, med, mu, sd)
    reg = LAMBDA * np.eye(A.shape[1])
    reg[-1, -1] = 0.0  # do not shrink the intercept
    w = np.linalg.solve(A.T @ A + reg, A.T @ np.asarray(yc, float))
    return B @ w


def trailing(X: pd.DataFrame, target: str) -> np.ndarray:
    return X[f"recent_{target}"].to_numpy()


def cqr_add(scores, coverage: float = COVERAGE) -> float:
    s = np.sort(np.asarray(scores, dtype=float))
    if len(s) == 0:
        return 0.0
    return float(s[min(len(s), int(np.ceil((len(s) + 1) * coverage))) - 1])


# ----------------------------------------------------------------- evaluation


def run(df: pd.DataFrame, X: pd.DataFrame, kumo: Kumo) -> pd.DataFrame:
    d = df["bid_open_date"]
    parts = []

    def _predict(fit, q_rows, kind):
        res = pd.DataFrame({"contract_id": df.loc[q_rows, "contract_id"].to_numpy(), "kind": kind})
        for target in TARGETS:
            y = df[target]
            for label, cols in (("", NUMERIC), ("_no_planholders", NO_PLANHOLDERS)):
                k = kumo.predict(X[fit], y[fit], X[q_rows], cols)
                res[f"{target}_kumo{label}"] = k[:, 1]
                if not label:
                    res[f"{target}_kumo_q10"], res[f"{target}_kumo_q90"] = k[:, 0], k[:, 2]
                res[f"{target}_linear{label}"] = linear(X[fit], y[fit], X[q_rows], cols)
            res[f"{target}_median"] = trailing(X.loc[q_rows], target)
        return res

    val = (d >= VALIDATION_START) & (d < pd.Timestamp(CUTOFF))
    parts.append(_predict(d < VALIDATION_START, val, "validation"))
    for q in pd.period_range(pd.Timestamp(CUTOFF), pd.Timestamp(TEST_END), freq="Q"):
        rows = d.dt.to_period("Q") == q
        if rows.any():
            parts.append(_predict(d < q.start_time, rows, "test"))
    out = pd.concat(parts, ignore_index=True).merge(
        df[
            [
                "contract_id",
                "contract_number",
                "bid_open_date",
                "district",
                "spread",
                "bidders",
                "engineers_estimate",
                "low_bid_cost",
            ]
        ],
        on="contract_id",
    )

    # Additive CQR on Kumo's q10 / q90, recalibrated each quarter on earlier contracts.
    for target in TARGETS:
        lo, hi = out[f"{target}_kumo_q10"], out[f"{target}_kumo_q90"]
        score = np.maximum(lo - out[target], out[target] - hi)
        out[f"{target}_low"], out[f"{target}_high"] = np.nan, np.nan
        for q in pd.period_range(pd.Timestamp(CUTOFF), pd.Timestamp(TEST_END), freq="Q"):
            now = (out["kind"] == "test") & (out["bid_open_date"].dt.to_period("Q") == q)
            adj = cqr_add(score[out["bid_open_date"] < q.start_time])
            out.loc[now, f"{target}_low"] = lo[now] - adj
            out.loc[now, f"{target}_high"] = hi[now] + adj
    return out


def score(out: pd.DataFrame) -> dict:
    t = out[out["kind"] == "test"]
    res = {}
    for target, tol in (("spread", 0.10), ("bidders", 1.0)):
        methods = {}
        for m in ("kumo", "linear", "median", "kumo_no_planholders", "linear_no_planholders"):
            p = t[f"{target}_{m}"]
            if target == "bidders":
                p = p.round().clip(lower=1)
            e = (p - t[target]).abs()
            methods[m] = {
                "mae": float(e.mean()),
                "within": float((e <= tol + 1e-9).mean()),
                "median_signed": float((p - t[target]).median()),
            }
        inside = (t[target] >= t[f"{target}_low"]) & (t[target] <= t[f"{target}_high"])
        native = (t[target] >= t[f"{target}_kumo_q10"]) & (t[target] <= t[f"{target}_kumo_q90"])
        res[target] = {
            "methods": methods,
            "range_coverage": float(inside.mean()),
            "native_range_coverage": float(native.mean()),
            "median_range_width": float((t[f"{target}_high"] - t[f"{target}_low"]).median()),
            "actual_mean": float(t[target].mean()),
            "contracts": int(len(t)),
        }
    return res


# ----------------------------------------------------------------- report


def _pt(x: float) -> str:
    return f"{100 * x:.1f} points"


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def write(out_dir: Path, out: pd.DataFrame, res: dict, n_train: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    t = out[out["kind"] == "test"].copy()
    cols = [
        "contract_number",
        "bid_open_date",
        "district",
        "engineers_estimate",
        "low_bid_cost",
        "spread",
        "spread_low",
        "spread_kumo",
        "spread_high",
        "spread_linear",
        "spread_median",
        "bidders",
        "bidders_low",
        "bidders_kumo",
        "bidders_high",
        "bidders_linear",
        "bidders_median",
    ]
    t[cols].to_csv(
        out_dir / "test_predictions.csv", index=False, float_format="%.4f", date_format="%Y-%m-%d"
    )
    names = {
        "kumo": "Kumo Tabular",
        "linear": "Linear model",
        "median": "Trailing 12-month median",
        "kumo_no_planholders": "Kumo Tabular, without plan holders",
        "linear_no_planholders": "Linear model, without plan holders",
    }
    s, b = res["spread"], res["bidders"]
    sl = [
        "| Method | Typical miss (mean) | Within 10 points | Median over (+) / under (-) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for m, r in s["methods"].items():
        sl.append(
            f"| {names[m]} | {_pt(r['mae'])} | {_pct(r['within'])} | "
            f"{100 * r['median_signed']:+.1f} points |"
        )
    bl = [
        "| Method | Typical miss (mean) | Within 1 bidder | Median over (+) / under (-) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for m, r in b["methods"].items():
        bl.append(
            f"| {names[m]} | {r['mae']:.2f} bidders | {_pct(r['within'])} | "
            f"{r['median_signed']:+.1f} |"
        )
    ex = t.sort_values("bid_open_date").tail(5)
    el = [
        "| Contract | Bid date | Engineer's estimate | Expected low bid vs EE (range) | Actual | "
        "Expected bidders (range) | Actual |",
        "| --- | --- | ---: | --- | ---: | --- | ---: |",
    ]
    for r in ex.itertuples():
        el.append(
            f"| {r.contract_number} | {r.bid_open_date:%Y-%m-%d} | ${r.engineers_estimate:,.0f} | "
            f"{100 * r.spread_kumo:+.0f}% "
            f"({100 * r.spread_low:+.0f}% to {100 * r.spread_high:+.0f}%) | "
            f"{100 * r.spread:+.0f}% | {max(1, round(r.bidders_kumo))} "
            f"({max(1, round(r.bidders_low))} to {max(1, round(r.bidders_high))}) | "
            f"{int(r.bidders)} |"
        )
    body = f"""
What the market is likely to do on a contract: how the low bid will compare with the
engineer's estimate, and how many contractors will bid (step 2.7).

## What we did

Each contract with a bid summary and an engineer's estimate is one row
({n_train} before {CUTOFF:%B %Y}, {s["contracts"]} after). The models see only what is known
before bids open: the engineer's estimate, working days, number of items,
location, time of year, the type of work, the number of plan holders (contractors who
took out the plans), and how the market behaved over the previous 12 months. As in stage
13, each method is refreshed every quarter with all earlier contracts. Three methods are
compared: Kumo Tabular (which also gives a range), a simple linear model, and the
trailing 12-month median.

## Low bid vs the engineer's estimate

On test contracts the low bid averaged {100 * s["actual_mean"]:+.1f}% against the engineer's
estimate. Misses are in percentage points of the estimate.

{chr(10).join(sl)}

The 80% range held the actual spread on **{_pct(s["range_coverage"])}** of test contracts
(Kumo's own range: {_pct(s["native_range_coverage"])}); a typical range is
{_pt(s["median_range_width"])} wide.

## Number of bidders

On test contracts the average was {b["actual_mean"]:.1f} bidders. Predictions are rounded to
whole bidders.

{chr(10).join(bl)}

The 80% range held the actual count on **{_pct(b["range_coverage"])}** of test contracts
(Kumo's own range: {_pct(b["native_range_coverage"])}); a typical range is
{b["median_range_width"]:.1f} bidders wide.

## Examples (the five latest test contracts)

{chr(10).join(el)}

## What this means for an estimator

The spread is hard to predict for a single contract: even the best method misses by
several points on average, so the range matters more than the middle number. The
bidder count is more predictable, mostly from the plan-holder list.

## Files

- `test_predictions.csv`: every test contract with the actual spread and bidder count,
  Kumo's middle estimate and range, and the other methods.
- `results.json`: all the scores above.

## How it was produced

`uv run python -m bidlens.market.context` (code in `src/bidlens/market/context.py`).
Generated {date.today().isoformat()}.
"""
    (out_dir / "README.md").write_text(
        "# 15 Market context\n\n" + body.strip() + "\n", encoding="utf-8"
    )
    (out_dir / "results.json").write_text(json.dumps(res, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    con = duckdb.connect(str(DB), read_only=True)
    df = load(con)
    con.close()
    X = features(df)
    out = run(df, X, Kumo())
    res = score(out)
    write(OUT, out, res, int((df["bid_open_date"] < pd.Timestamp(CUTOFF)).sum()))

    from bidlens.outputs import write_index

    write_index()
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
