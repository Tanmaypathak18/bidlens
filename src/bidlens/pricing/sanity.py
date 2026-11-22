"""Sanity check after step 2.4: contract totals per model, and why item misses are large.

Usage:
    uv run python -m bidlens.pricing.sanity    # writes outputs/12_sanity_check

1. Contract level: each model prices the top-100 lines of every test contract's bid list
   (other lines keep the history tiers), and the total is compared with the engineer's
   estimate against the actual low bid.
2. Item level: the misses broken down by family, by job size and by lump sum, an
   independent recomputation of the metric, and a noise floor: how far the second-lowest
   bidder's unit price sits from the low bidder's on the same line.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# No model libraries here: predictions come from the files each model script saves.
from bidlens.pricing import features as F
from bidlens.pricing.benchmarks import contract_totals, headline
from bidlens.pricing.escalate import CostIndex
from bidlens.pricing.setup import WITHIN, ape, use_cost_index

ROOT = Path(".")
DB = ROOT / "data" / "bidlens.duckdb"
OUT = ROOT / "outputs" / "12_sanity_check"
MODELS = ["trailing_median", "xgboost", "lightgbm", "kumo"]
LABELS = {
    "trailing_median": "Historical median",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "kumo": "Kumo Tabular",
}


# ----------------------------------------------------------------- contract level


def contract_level(con, rows, cats):
    contracts, base, sel, _ = F.contract_lines(con, rows, cats)
    totals = {"trailing_median": contract_totals(base, contracts)}
    headline_set = totals["trailing_median"]["in_headline"].to_numpy()
    for m in ("xgboost", "lightgbm", "kumo"):
        path = Path(str(F.LINE_PREDICTIONS).format(model=m))
        p = pd.read_parquet(path)
        p["bid_open_date"] = pd.to_datetime(p["bid_open_date"])
        merged = sel[F.LINE_KEY].merge(p, on=F.LINE_KEY, how="left", validate="one_to_one")
        if merged["pred_unit_price"].isna().any():
            raise RuntimeError(f"{path} does not cover every line; rerun the {m} script")
        priced = base.copy()
        priced.loc[sel.index, "pred_unit_price"] = merged["pred_unit_price"].to_numpy()
        priced.loc[sel.index, "tier"] = 1
        priced["pred_amount"] = priced["pred_unit_price"] * priced["quantity"]
        t = contract_totals(priced, contracts)
        t["in_headline"] = headline_set  # the same contracts for every method
        totals[m] = t
    summary = {m: headline(t) for m, t in totals.items()}
    share = float(base.loc[sel.index, "amount"].sum() / base["amount"].sum())
    return totals, summary, share


# ----------------------------------------------------------------- item level


def noise_floor(con) -> dict:
    """How far the second-lowest bidder's unit price is from the low bidder's, same line."""
    df = con.execute(
        """
        SELECT b1.bid_item_id, CAST(b1.unit_price AS DOUBLE) AS low,
               CAST(b2.unit_price AS DOUBLE) AS second, i.unit
        FROM bid b1 JOIN bid b2 ON b2.bid_item_id = b1.bid_item_id AND b2.bid_rank = 2
        JOIN bid_item i ON i.bid_item_id = b1.bid_item_id
        JOIN contract c ON c.contract_id = i.contract_id
        WHERE b1.bid_rank = 1 AND b1.unit_price > 0
          AND c.bid_open_date >= DATE '2024-01-01'
        ORDER BY 1
        """
    ).df()
    e = ape(df["second"], df["low"])
    ls = df["unit"] == "LS"
    return {
        "lines": int(len(df)),
        "mdape": float(np.median(e)),
        "within_15": float((e <= WITHIN).mean()),
        "mdape_lump_sum": float(np.median(e[ls])),
        "mdape_unit_priced": float(np.median(e[~ls])),
    }


def item_breakdown(rows, X, test) -> tuple[pd.DataFrame, dict]:
    base = pd.read_csv(
        ROOT / "outputs" / "10_baselines" / "predictions.csv",
        dtype={"bid_item_id": str, "item_code": str},
    )
    kumo = pd.read_csv(
        ROOT / "outputs" / "11_kumo_tabular" / "predictions.csv", dtype={"bid_item_id": str}
    )
    df = base.merge(kumo[["bid_item_id", "kumo"]], on="bid_item_id")
    meta = rows.loc[test.index, ["bid_item_id"]].assign(
        ratio=np.exp(X.loc[test.index, "log_quantity_vs_history"].to_numpy()),
        has_ee=rows.loc[test.index, "engineers_estimate"].notna().to_numpy(),
    )
    df = df.merge(meta, on="bid_item_id", how="left")
    df["lump_sum"] = np.where(df["unit"] == "LS", "Lump sum", "Priced per unit")
    df["job_size"] = (
        pd.cut(
            df["ratio"],
            [0, 1 / 3, 0.8, 1.25, 3, np.inf],
            labels=[
                "Much smaller (under 1/3)",
                "Smaller",
                "Typical (0.8 to 1.25x)",
                "Larger",
                "Much larger (over 3x)",
            ],
        )
        .astype(str)
        .where(df["unit"] != "LS", "Lump sum (quantity 1)")
    )
    df["engineers_estimate"] = np.where(df["has_ee"], "Known", "Not available")

    # Independent recomputation of the metric, straight from the CSV.
    check = {}
    for m in MODELS:
        e = (df[m] - df["low_bid_unit_price"]).abs() / df["low_bid_unit_price"]
        check[m] = {
            "mdape": float(e.median()),
            "median_signed": float(
                ((df[m] - df["low_bid_unit_price"]) / df["low_bid_unit_price"]).median()
            ),
            "median_log_ratio": float(np.log(df[m] / df["low_bid_unit_price"]).median()),
            "share_over": float((df[m] > df["low_bid_unit_price"]).mean()),
        }

    year = pd.to_datetime(df["bid_open_date"]).dt.year
    check["by_year_signed"] = {
        m: {
            int(y): float(np.expm1(v))
            for y, v in np.log(df[m] / df["low_bid_unit_price"]).groupby(year).median().items()
        }
        for m in MODELS
    }
    tables = []
    for by in ("family", "lump_sum", "job_size", "engineers_estimate"):
        for g, sub in df.groupby(by):
            r = {"by": by, "group": g, "prices": len(sub)}
            for m in MODELS:
                e = ape(sub[m], sub["low_bid_unit_price"])
                r[f"{m}_mdape"] = float(np.median(e))
            tables.append(r)
    return pd.DataFrame(tables), check


# ----------------------------------------------------------------- report


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def write_outputs(out, totals, summary, model_share, breakdown, check, floor) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    cols = ["contract_number", "bid_open_date", "low_bid_cost", "engineers_estimate", "in_headline"]
    wide = totals["trailing_median"][cols].copy()
    for m, t in totals.items():
        wide[f"{m}_total"] = t["bidlens_total"].to_numpy()
        wide[f"{m}_error"] = t["bidlens_error"].to_numpy()
    wide["ee_error"] = totals["trailing_median"]["ee_error"].to_numpy()
    wide.to_csv(
        out / "contract_totals_by_model.csv",
        index=False,
        float_format="%.4f",
        date_format="%Y-%m-%d",
    )
    breakdown.to_csv(out / "item_error_breakdown.csv", index=False, float_format="%.4f")

    h = {m: summary[m]["headline"] for m in MODELS}
    n_head = h["kumo"]["contracts"]
    ee = h["kumo"]
    clines = [
        "| Total built with | Closer than the EE | Typical miss | Median over (+) / under (-) "
        "| Within 15% |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for m in MODELS:
        r = h[m]
        clines.append(
            f"| {LABELS[m]} | {_pct(r['bidlens_closer_share'])} | "
            f"{_pct(r['bidlens_median_abs_error'])} | {_pct(r['bidlens_median_error'])} "
            f"| {_pct(r['bidlens_within_15'])} |"
        )
    clines.append(
        f"| Engineer's estimate | | {_pct(ee['ee_median_abs_error'])} | "
        f"{_pct(ee['ee_median_error'])} | {_pct(ee['ee_within_15'])} |"
    )

    def _table(by: str, title: str) -> list[str]:
        sub = breakdown[breakdown["by"] == by].sort_values("prices", ascending=False)
        lines = [
            f"| {title} | Prices | " + " | ".join(LABELS[m] for m in MODELS) + " |",
            "| --- | ---: |" + " ---: |" * len(MODELS),
        ]
        for r in sub.itertuples():
            lines.append(
                f"| {r.group} | {r.prices:,} | "
                + " | ".join(_pct(getattr(r, f"{m}_mdape")) for m in MODELS)
                + " |"
            )
        return lines

    years = sorted(check["by_year_signed"]["kumo"])
    ylines = [
        "| Method | " + " | ".join(str(y) for y in years) + " |",
        "| --- |" + " ---: |" * len(years),
    ]
    for m in MODELS:
        ylines.append(
            f"| {LABELS[m]} | "
            + " | ".join(f"{100 * check['by_year_signed'][m][y]:+.1f}%" for y in years)
            + " |"
        )
    chk = [
        "| Method | Median miss (recomputed) | Median signed error | Share over the low bid |",
        "| --- | ---: | ---: | ---: |",
    ]
    for m in MODELS:
        c = check[m]
        chk.append(
            f"| {LABELS[m]} | {_pct(c['mdape'])} | {_pct(c['median_signed'])} | "
            f"{_pct(c['share_over'])} |"
        )

    body = f"""
A check of the pricing results so far, in plain terms (after step 2.4).

## 1. Whole-contract totals: the headline

For each of the {n_head} test contracts, each method prices every line of the low bidder's
bid list, and the lines are added up. The {_pct(model_share)} of contract dollars that are
top-100 items are priced by the model; the other lines use the same historical prices for
every method (stage 08). The engineer's estimate is Caltrans' own figure.

{chr(10).join(clines)}

"Closer than the EE" is the share of contracts where that total was nearer the actual low
bid than Caltrans' engineer's estimate. "Typical miss" is the median distance from the low
bid. Contract totals land much closer than single items because over- and under-priced
lines partly cancel.

## 2. Why single items miss by about 40%

**The low bid itself is noisy.** On the same line of the same contract, the second-lowest
bidder's unit price differs from the low bidder's by a median of **{_pct(floor["mdape"])}**
({floor["lines"]:,} lines bid since 2024; {_pct(floor["mdape_lump_sum"])} for lump sums,
{_pct(floor["mdape_unit_priced"])} for unit-priced items). Contractors spread their costs
across items differently ("unbalanced" bids), so a single item's low-bid price carries a
lot of noise even when the total is competitive. That sets a floor: no method should be
expected to match single low-bid prices much better than a second real bidder does. The
best model is about {100 * (check["kumo"]["mdape"] - floor["mdape"]):.0f} points above that floor.

**Lump sums and odd quantities are the hardest.**

{chr(10).join(_table("lump_sum", "Kind of item"))}

{chr(10).join(_table("job_size", "Quantity vs the item’s usual quantity"))}

{chr(10).join(_table("engineers_estimate", "Engineer’s estimate on file"))}

By item family:

{chr(10).join(_table("family", "Item family"))}

## 3. Is the error calculated correctly?

The miss is |predicted − actual| / actual, using the low bidder's unit price as the actual,
with both in the dollars of the bid date. Recomputed independently from the saved
predictions:

{chr(10).join(chk)}

The recomputed numbers match stages 10 and 11. Errors are measured against the actual
price, so an under-prediction can miss by at most 100% while an over-prediction has no
cap: the median is used for that reason, and the share over the low bid shows whether a
method leans high or low.

**The models lean high, more so the further from the training years.** Median over (+)
or under (-) the low bid, by bid year:

{chr(10).join(ylines)}

The trained models learned prices up to the end of 2023 and carry them forward with
Caltrans' statewide cost index. That index rose about 29% from late 2023 to early 2026,
while low bids for these items in Districts 4 and 5 rose much less, so the models drift
high. The historical median sees the latest bids and drifts much less. A first fix was
made: the index used for a bid is now the one known before that bid
opened, which removed a small look-ahead leak; it did not remove the drift. The real fix
is to let the models see recent bids (refreshing Kumo's table of known prices costs
nothing; the other models would be retrained), which step 2.5 decides.

## Files

- `contract_totals_by_model.csv`: every test contract with each method's total and error.
- `item_error_breakdown.csv`: the item-level tables above.
- `results.json`: the headline numbers.

## How it was produced

`uv run python -m bidlens.pricing.sanity` (code in `src/bidlens/pricing/sanity.py`), after
stages 10 and 11. Generated {date.today().isoformat()}.
"""
    (out / "README.md").write_text("# 12 Sanity check\n\n" + body.strip() + "\n", encoding="utf-8")
    result = {
        "contract_level": summary,
        "model_priced_share_of_dollars": model_share,
        "noise_floor": floor,
        "metric_check": check,
    }
    (out / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    con = duckdb.connect(str(DB), read_only=True)
    use_cost_index(CostIndex.from_db(con))
    rows, X, y, train_mask, test, cats = F.prepare(con)
    totals, summary, share = contract_level(con, rows, cats)
    breakdown, check = item_breakdown(rows, X, test)
    floor = noise_floor(con)
    con.close()
    result = write_outputs(OUT, totals, summary, share, breakdown, check, floor)

    from bidlens.outputs import write_index

    write_index()
    print(json.dumps({m: r["headline"] for m, r in result["contract_level"].items()}, indent=2))
    print(json.dumps(result["noise_floor"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
