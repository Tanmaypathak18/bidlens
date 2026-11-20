"""Step 2.6: price ranges and comparable bids (decisions D-047, D-048).

Usage:
    uv run python -m bidlens.pricing.ranges   # writes outputs/14_price_ranges

Needs data/interim/refresh_kumo.parquet (`refresh --model kumo`). No model library is
imported here.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from bidlens.pricing import features as F
from bidlens.pricing.comparables import ComparableFinder
from bidlens.pricing.escalate import CostIndex
from bidlens.pricing.refresh import OUT as REFRESH
from bidlens.pricing.setup import CUTOFF, TEST_END, ape, report_family, use_cost_index

ROOT = Path(".")
DB = ROOT / "data" / "bidlens.duckdb"
OUT = ROOT / "outputs" / "14_price_ranges"
COVERAGE = 0.80
EXAMPLES = 3


def conformity(low, high, actual) -> np.ndarray:
    """CQR score: how far the actual price falls outside [low, high], in log terms
    (negative when inside)."""
    la = np.log(actual)
    return np.maximum(np.log(low) - la, la - np.log(high))


def cqr_adjustment(scores, coverage: float = COVERAGE) -> float:
    """The finite-sample conformal quantile of the scores."""
    s = np.sort(np.asarray(scores, dtype=float))
    n = len(s)
    if n == 0:
        return 0.0
    k = min(n, int(np.ceil((n + 1) * coverage)))
    return float(s[k - 1])


def calibrate(df: pd.DataFrame) -> pd.DataFrame:
    """Add CQR low/high to test rows, recalibrated each quarter on all earlier rows
    (validation and earlier test quarters), separately for lump sums (D-047)."""
    df = df.copy()
    df["score"] = conformity(df["q10"], df["q90"], df["unit_price"])
    df["low"], df["high"], df["adjustment"] = np.nan, np.nan, np.nan
    quarters = pd.period_range(pd.Timestamp(CUTOFF), pd.Timestamp(TEST_END), freq="Q")
    is_test = df["kind"] == "test"
    for q in quarters:
        now = is_test & (df["bid_open_date"].dt.to_period("Q") == q)
        past = df["bid_open_date"] < q.start_time
        for ls in (True, False):
            grp = df["lump_sum"] == ls
            adj = cqr_adjustment(df.loc[past & grp, "score"])
            sel = now & grp
            df.loc[sel, "adjustment"] = adj
            df.loc[sel, "low"] = df.loc[sel, "q10"] * np.exp(-adj)
            df.loc[sel, "high"] = df.loc[sel, "q90"] * np.exp(adj)
    return df


def _coverage(df, low, high) -> dict:
    inside = (df["unit_price"] >= df[low]) & (df["unit_price"] <= df[high])
    return {
        "prices": len(df),
        "coverage": float(inside.mean()),
        "median_width": float((df[high] / df[low]).median()),
        "below": float((df["unit_price"] < df[low]).mean()),
        "above": float((df["unit_price"] > df[high]).mean()),
    }


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    con = duckdb.connect(str(DB), read_only=True)
    use_cost_index(CostIndex.from_db(con))
    rows, X, y, train_mask, test, cats = F.prepare(con)
    src = con.execute(
        "SELECT bid_item_id, source_row_id FROM bid WHERE bid_rank = 1 ORDER BY 1"
    ).df()
    con.close()
    rows = rows.merge(src, on="bid_item_id", how="left")
    ref = pd.read_parquet(Path(str(REFRESH).format(model="kumo")))
    ref = ref[ref["kind"].isin(["validation", "test"])]
    df = ref.merge(
        rows[["bid_item_id", "unit_price", "unit", "item_family", "is_outlier"]],
        left_on="key",
        right_on="bid_item_id",
    )
    df = df.rename(columns={"pred_q10": "q10", "pred_q90": "q90", "pred_unit_price": "likely"})
    df["lump_sum"] = df["unit"] == "LS"
    df = calibrate(df)
    t = df[df["kind"] == "test"].copy()
    t["family"] = report_family(t["item_family"])
    t["year"] = t["bid_open_date"].dt.year

    summary = {
        "native": _coverage(t, "q10", "q90"),
        "calibrated": _coverage(t, "low", "high"),
        "validation_native": _coverage(df[df["kind"] == "validation"], "q10", "q90"),
    }
    groups = []
    for by in ("lump_sum", "family", "year"):
        for g, sub in t.groupby(by):
            name = {True: "Lump sum", False: "Priced per unit"}.get(g, g) if by == "lump_sum" else g
            groups.append(
                {
                    "by": by,
                    "group": name,
                    **{f"native_{k}": v for k, v in _coverage(sub, "q10", "q90").items()},
                    **{
                        f"calibrated_{k}": v
                        for k, v in _coverage(sub, "low", "high").items()
                        if k != "prices"
                    },
                }
            )
    groups = pd.DataFrame(groups)

    # Comparable bids (D-048) for every test price, from cleaned earlier low bids.
    clean = rows[~rows["low_bidder_disagrees"] & ~rows["is_outlier"] & (rows["unit_price"] > 0)]
    finder = ComparableFinder(clean)
    comps, comp_check = [], []
    for r in t.merge(
        rows[
            [
                "bid_item_id",
                "item_code",
                "quantity",
                "district",
                "engineers_estimate",
                "contract_number",
            ]
        ],
        on="bid_item_id",
    ).itertuples():
        c = finder.find(
            r.item_code, r.unit, r.bid_open_date, r.quantity, r.district, r.engineers_estimate
        )
        if c.empty:
            continue
        c.insert(0, "bid_item_id", r.bid_item_id)
        c.insert(1, "rank", np.arange(1, len(c) + 1))
        comps.append(c)
        p = c["unit_price_in_query_dollars"]
        comp_check.append(
            {
                "bid_item_id": r.bid_item_id,
                "n": len(c),
                "comparable_median": float(p.median()),
                "inside_comparable_span": bool(p.min() <= r.unit_price <= p.max()),
                "unit_price": r.unit_price,
            }
        )
    comps = pd.concat(comps, ignore_index=True)
    cc = pd.DataFrame(comp_check)
    summary["comparables"] = {
        "test_prices_with_comparables": len(cc),
        "share_with_10": float((cc["n"] == 10).mean()),
        "comparable_median_mdape": float(np.median(ape(cc["comparable_median"], cc["unit_price"]))),
        "inside_comparable_span": float(cc["inside_comparable_span"].mean()),
    }
    write(OUT, t, groups, summary, comps, rows)

    from bidlens.outputs import write_index

    write_index()
    print(json.dumps(summary, indent=2))
    return 0


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def write(out: Path, t, groups, summary, comps, rows) -> None:
    out.mkdir(parents=True, exist_ok=True)
    t[
        [
            "bid_item_id",
            "bid_open_date",
            "unit",
            "family",
            "unit_price",
            "low",
            "likely",
            "high",
            "q10",
            "q90",
            "adjustment",
        ]
    ].rename(
        columns={"unit_price": "low_bid_unit_price", "q10": "kumo_q10", "q90": "kumo_q90"}
    ).to_csv(out / "test_ranges.csv", index=False, float_format="%.4f", date_format="%Y-%m-%d")
    groups.to_csv(out / "coverage_by_group.csv", index=False, float_format="%.4f")
    comps.to_csv(
        out / "comparable_bids.csv", index=False, float_format="%.4f", date_format="%Y-%m-%d"
    )

    n, c, v = summary["native"], summary["calibrated"], summary["validation_native"]

    def _table(by, title):
        sub = groups[groups["by"] == by]
        if by == "family":
            sub = sub.sort_values("native_prices", ascending=False)
        lines = [
            f"| {title} | Prices | Kumo's own range | BidLens range | Typical width (high / low) |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for r in sub.itertuples():
            lines.append(
                f"| {r.group} | {r.native_prices:,} | {_pct(r.native_coverage)} | "
                f"{_pct(r.calibrated_coverage)} | {r.calibrated_median_width:.1f}x |"
            )
        return lines

    # Worked examples: the most common item's first test prices.
    ex_lines = []
    tt = t.merge(
        rows[["bid_item_id", "item_code", "quantity", "contract_number"]], on="bid_item_id"
    )
    for r in tt[tt["item_code"] == tt["item_code"].mode().iloc[0]].head(EXAMPLES).itertuples():
        cs = comps[comps["bid_item_id"] == r.bid_item_id].head(5)
        ex_lines += [
            f"**{r.item_code} ({r.unit}), contract {r.contract_number}, bid "
            f"{r.bid_open_date:%d %b %Y}, quantity {r.quantity:,.0f}:** range "
            f"${r.low:,.2f} / ${r.likely:,.2f} / ${r.high:,.2f}; "
            f"actual low bid ${r.unit_price:,.2f}.",
            "",
            "| Comparable contract | Bid date | District | Quantity | Unit price "
            "| In this bid's dollars |",
            "| --- | --- | --- | ---: | ---: | ---: |",
        ]
        for cr in cs.itertuples():
            ex_lines.append(
                f"| [{cr.contract_number}]({cr.source}) | {cr.bid_open_date:%Y-%m-%d} | "
                f"{cr.district} | {cr.quantity:,.0f} | ${cr.unit_price:,.2f} | "
                f"${cr.unit_price_in_query_dollars:,.2f} |"
            )
        ex_lines.append("")
    k = summary["comparables"]
    body = f"""
A low / likely / high price for every bid item, and the past bids behind it (step 2.6).

## What the range means

For each item BidLens gives three prices: **low**, **likely** and **high**. The range is
built so that the winning bidder's unit price falls between low and high on about
{_pct(COVERAGE)} of items, below low on about 10% and above high on about 10%. Likely is
the model's middle estimate (stage 13).

## How it is built (decision D-047)

Kumo Tabular gives a full spread of possible prices, not just one number. Its own
10th-to-90th percentile range is the starting point. Each quarter, BidLens checks how
often that range held the actual low bid on every earlier priced item, and widens (or
narrows) it until it would have held 80% of them, separately for lump sums and for
unit-priced items, which are much less predictable. Only past results are used.

## Does it hold up on the test years?

On {c["prices"]:,} test prices (2024 to 2026): the BidLens range held the actual low bid on
**{_pct(c["coverage"])}** of items (target 80%); {_pct(c["below"])} came in below low and
{_pct(c["above"])} above high. Kumo's own range, before this adjustment, held
{_pct(n["coverage"])} ({_pct(v["coverage"])} on 2023 validation bids). The typical range is
{c["median_width"]:.1f} times as high at the top as at the bottom, a direct reflection of
how noisy single low-bid prices are (stage 12).

{chr(10).join(_table("lump_sum", "Kind of item"))}

{chr(10).join(_table("year", "Bid year"))}

{chr(10).join(_table("family", "Item family"))}

## Comparable bids (decision D-048)

Every price comes with the 10 most similar earlier low bids for the same item: closest in
quantity first, then recent, same district and similar contract size. Each links to its
Caltrans source page. {_pct(k["share_with_10"])} of test prices have a full 10. As a check,
the median of an item's comparables (in today's dollars) misses the low bid by a median of
{_pct(k["comparable_median_mdape"])}, and the actual price falls inside the comparables' span on
{_pct(k["inside_comparable_span"])} of items.

### Examples

{chr(10).join(ex_lines)}

## Files

- `test_ranges.csv`: every test price with its low / likely / high, Kumo's own 10th and
  90th percentiles, and the quarter's adjustment.
- `coverage_by_group.csv`: the coverage tables above.
- `comparable_bids.csv`: the 10 comparable bids for every test price, with source links.
- `results.json`: the headline numbers.

## How it was produced

`uv run python -m bidlens.pricing.refresh --model kumo`, then
`uv run python -m bidlens.pricing.ranges` (code in `src/bidlens/pricing/ranges.py` and
`comparables.py`). Generated {date.today().isoformat()}.
"""
    (out / "README.md").write_text(
        "# 14 Price ranges and comparable bids\n\n" + body.strip() + "\n", encoding="utf-8"
    )
    (out / "results.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
