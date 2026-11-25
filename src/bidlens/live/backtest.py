"""Check the live engine the way the app runs it, on every 2024 to 2026 test contract.

Usage:
    uv run python -m bidlens.live.backtest    # about 2 minutes; writes outputs/22_live_evaluation

Each contract is priced exactly as the Evaluate page prices it: LightGBM fit on the bids
opened before the contract's quarter, ranges from the year before, a linear market model.
The actual results are used only to score.
"""

from __future__ import annotations

import json
import time
from datetime import date

import pandas as pd

from bidlens.live.bundle import ROOT, load
from bidlens.live.engine import MODEL_NAME, Engine

OUT = ROOT / "outputs" / "22_live_evaluation"
STAGE13 = ROOT / "outputs" / "13_model_comparison" / "contract_totals_refreshed.csv"


def second_bid_gap(contracts: pd.DataFrame, keys: pd.DataFrame) -> pd.Series:
    """Second-lowest total over the lowest total, minus 1, for the given contracts."""
    k = keys[["contract_number", "bid_open_date"]].copy()
    k["bid_open_date"] = pd.to_datetime(k["bid_open_date"])
    c = contracts.merge(k, on=["contract_number", "bid_open_date"], how="inner")
    gap = c["second_bid_total"] / c["low_bid_total"] - 1
    return gap.dropna()


def run() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    eng = Engine(load(), model="lightgbm")  # the hosted demo's model; Kumo is stage 13
    tc = eng.test_contracts()
    rows, items = [], []
    t0 = time.perf_counter()
    for c in tc.itertuples():
        job = eng.contract_job(c.contract_number, c.bid_open_date)
        est, mk = eng.evaluate(job)
        a = job.actual
        rows.append({
            "contract_number": c.contract_number,
            "bid_open_date": c.bid_open_date.date().isoformat(),
            "lines": len(est),
            "model_share": float(est.loc[est["tier"] == 0, "pred_amount"].sum() / est["pred_amount"].sum()),
            "live_total": float(est["pred_amount"].sum()),
            "engineers_estimate": job.engineers_estimate,
            "low_bid_cost": a.get("low_bid"),
            "bidders": a.get("bidders"),
            "spread_likely": mk.get("spread", {}).get("likely"),
            "spread_low": mk.get("spread", {}).get("low"),
            "spread_high": mk.get("spread", {}).get("high"),
            "bidders_likely": mk.get("bidders", {}).get("likely"),
            "bidders_low": mk.get("bidders", {}).get("low"),
            "bidders_high": mk.get("bidders", {}).get("high"),
        })  # fmt: skip
        items.append(
            est[
                ["item_no", "unit", "tier", "range_kind", "check_price", "low", "high", "check"]
            ].assign(contract_number=c.contract_number)
        )
    seconds = time.perf_counter() - t0
    df, it = pd.DataFrame(rows), pd.concat(items, ignore_index=True)

    head = pd.read_csv(STAGE13)
    head = head[head["in_headline"]][["contract_number", "bid_open_date", "production_total"]]
    df = df.merge(head, on=["contract_number", "bid_open_date"], how="left")
    df["in_headline"] = df["production_total"].notna()
    low = df["low_bid_cost"]
    df["live_error"] = df["live_total"] / low - 1
    df["ee_error"] = df["engineers_estimate"] / low - 1
    df["kumo_error"] = df["production_total"] / low - 1

    h = df[df["in_headline"]]
    has = it[it["check"].isin(["inside", "below", "above"])]
    cov = {k: float((g["check"] == "inside").mean()) for k, g in has.groupby("range_kind")}
    mk = df.dropna(subset=["spread_likely", "low_bid_cost", "engineers_estimate"])
    spread = mk["low_bid_cost"] / mk["engineers_estimate"] - 1
    bid = df.dropna(subset=["bidders_likely", "bidders"])
    gap = second_bid_gap(eng.b.contracts, h)
    res = {
        "model": MODEL_NAME,
        "contracts": len(df),
        "headline": {
            "contracts": len(h),
            "live_closer_than_ee": float((h["live_error"].abs() < h["ee_error"].abs()).mean()),
            "kumo_closer_than_ee": float((h["kumo_error"].abs() < h["ee_error"].abs()).mean()),
            "live_median_abs_error": float(h["live_error"].abs().median()),
            "kumo_median_abs_error": float(h["kumo_error"].abs().median()),
            "ee_median_abs_error": float(h["ee_error"].abs().median()),
            "live_within_15": float((h["live_error"].abs() <= 0.15).mean()),
            "live_median_error": float(h["live_error"].median()),
        },
        "item_range_coverage": cov,
        "item_range_coverage_all": float((has["check"] == "inside").mean()),
        "items_checked": {k: int(len(g)) for k, g in has.groupby("range_kind")},
        "market": {
            "spread_mae": float((mk["spread_likely"] - spread).abs().mean()),
            "spread_range_coverage": float(((spread >= mk["spread_low"]) & (spread <= mk["spread_high"])).mean()),
            "bidders_mae": float((bid["bidders_likely"] - bid["bidders"]).abs().mean()),
            "bidders_within_1": float(((bid["bidders_likely"] - bid["bidders"]).abs() <= 1).mean()),
            "bidders_range_coverage": float(((bid["bidders"] >= bid["bidders_low"]) & (bid["bidders"] <= bid["bidders_high"])).mean()),
        },
        "second_bid_gap_median": float(gap.median()),
        "second_bid_gap_contracts": int(len(gap)),
        "seconds_total": seconds,
        "seconds_per_contract": seconds / len(df),
    }  # fmt: skip
    return df, it, res


def write(df: pd.DataFrame, res: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "contract_totals.csv", index=False, float_format="%.4f")
    (OUT / "results.json").write_text(json.dumps(res, indent=2) + "\n")
    h, m, cov = res["headline"], res["market"], res["item_range_coverage"]

    def p(x):
        return f"{100 * x:.1f}%"

    (OUT / "README.md").write_text(
        f"""# 22 Live evaluation

How the light live model behind the hosted demo's Evaluate page does on the
{res["contracts"]} test contracts bid in 2024 to 2026, priced exactly as the page prices them.
On a computer with Kumo Tabular installed, the Evaluate page runs Kumo instead, which
reproduces the production totals of stage 13.

## Method

For each contract, {res["model"]} (the step 2.3 settings, one seed) is fit at run time on
every cleaned low bid opened before the contract's quarter, and prices the top-100 items;
the other items come from earlier bids for the same item. Ranges are 80%: model items take
the 10th to 90th percentile of the errors a model fit one year earlier made on that last
year's bids (lump sum and unit-priced items separately); other items with at least 5
earlier prices take the 10th to 90th percentile of those prices. The market view is a
linear model on earlier contracts. The actual results are used only to score. Kumo Tabular
(PyTorch plus its weights) is too heavy for the free hosted demo, so the demo uses this
light model; Kumo's stage 13 results are shown for comparison.

## Results

On the {h["contracts"]} headline contracts (the same ones as stage 13):

| | Closer to the low bid than the engineer's estimate | Typical miss |
| --- | ---: | ---: |
| Light live model ({res["model"]}, hosted demo) | {p(h["live_closer_than_ee"])} | {p(h["live_median_abs_error"])} |
| Kumo Tabular (production, stage 13; live on a laptop) | {p(h["kumo_closer_than_ee"])} | {p(h["kumo_median_abs_error"])} |
| Engineer's estimate | | {p(h["ee_median_abs_error"])} |

- The live total is within 15% of the low bid on {p(h["live_within_15"])} of these
  contracts; its median miss is {100 * h["live_median_error"]:+.1f}%.
- Item ranges held the actual low-bid unit price on {p(cov.get("model", float("nan")))} of
  {res["items_checked"].get("model", 0):,} model-priced items and
  {p(cov.get("history", float("nan")))} of {res["items_checked"].get("history", 0):,}
  history-priced items (target 80%).
- Market view: low bid against the engineer's estimate missed by {100 * m["spread_mae"]:.1f}
  points on average (80% range held {p(m["spread_range_coverage"])}); bidder count missed by
  {m["bidders_mae"]:.2f} (within 1 bidder on {p(m["bidders_within_1"])}; range held
  {p(m["bidders_range_coverage"])}).
- For scale: the second-lowest bid was a median {p(res["second_bid_gap_median"])} above the
  low bid on these contracts. Bidders themselves disagree by about that much.
- Run time on this laptop: {res["seconds_total"]:.0f} seconds for all contracts
  ({res["seconds_per_contract"]:.1f} s each, with one model fit per quarter reused).

## Files

- `contract_totals.csv`: one row per contract: live total, engineer's estimate, low bid,
  errors, market view and its range.
- `results.json`: the numbers above.

## How it was produced

`uv run python -m bidlens.live.backtest` (code in `src/bidlens/live/`). Data from the
committed bundle in `data/sample/engine/` (`uv run python -m bidlens.live.bundle`).
Generated {date.today().isoformat()}.
""",
        encoding="utf-8",
    )
    from bidlens.outputs import write_index

    write_index()


def main() -> int:
    df, _, res = run()
    write(df, res)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
