"""Step 4.1: build the draft estimate the app shows for one bid package (decision D-064).

Usage:
    uv run python -m bidlens.estimate 04-0W0504     # about 30 s; writes data/interim/app/

Every number uses only what was known before bids opened:
- Bid items and quantities come from the package's bid item list (step 3.2), not the bid
  results.
- Top-100 items are priced by the production model (Kumo Tabular, refreshed each quarter
  on every earlier bid, D-045) with its calibrated 80% range (D-047). Other items use the
  D-038 history tiers and have no modeled range.
- Comparable bids are the 10 nearest earlier low bids (D-048).
- Market context (expected spread to the engineer's estimate and bidder count) is the
  quarterly-refreshed step 2.7 prediction (D-049).

The actual bid results are added separately, for the check panel only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from bidlens.pricing import features as F
from bidlens.pricing.benchmarks import TIERS, LinePricer, prepare_lines
from bidlens.pricing.comparables import ComparableFinder
from bidlens.pricing.compare import ITEMS, load_scope
from bidlens.pricing.escalate import CostIndex
from bidlens.pricing.ranges import calibrate
from bidlens.pricing.refresh import OUT as REFRESH
from bidlens.pricing.setup import use_cost_index

ROOT = Path(".")
DB = ROOT / "data" / "bidlens.duckdb"
DOCS = ROOT / "data" / "interim" / "docs"
APP = ROOT / "data" / "interim" / "app"
MARKET = ROOT / "outputs" / "15_market_context" / "test_predictions.csv"

TIER_TEXT = {
    1: "Recent low bids for this item (past 12 months)",
    2: "Earlier low bids for this item code",
    3: "Earlier low bids for the same special item description",
    4: "Typical price for this item family and unit (rough)",
    5: "No price history",
}
assert set(TIER_TEXT) >= set(TIERS)


def _contract(con, contract: str) -> pd.Series:
    df = con.execute(
        """SELECT contract_number, bid_open_date, district, county, type_of_work, working_days,
                  CAST(engineers_estimate AS DOUBLE) AS engineers_estimate,
                  CAST(low_bid_cost AS DOUBLE) AS low_bid_cost, n_bidders AS n_bidders_ranked
           FROM contract WHERE contract_number = ? ORDER BY bid_open_date DESC""",
        [contract],
    ).df()
    if df.empty:
        raise SystemExit(f"{contract} is not in the database")
    r = df.iloc[0].copy()
    r["bid_open_date"] = pd.Timestamp(r["bid_open_date"])
    return r


def build(contract: str) -> dict:
    con = duckdb.connect(str(DB), read_only=True)
    use_cost_index(CostIndex.from_db(con))
    info = _contract(con, contract)
    on = info["bid_open_date"]
    rows, _, _, _, _, _ = F.prepare(con)
    src = con.execute(
        "SELECT bid_item_id, source_row_id FROM bid WHERE bid_rank = 1 ORDER BY 1"
    ).df()
    master = con.execute("SELECT item_code, unit, item_family FROM item_master ORDER BY 1").df()
    raw = con.execute(
        f"SELECT * FROM read_parquet('{ITEMS}') ORDER BY contract_number, bid_open_date, item_no"
    ).df()
    con.close()
    rows = rows.merge(src, on="bid_item_id", how="left")

    # The package's bid item list (step 3.2) is what gets priced.
    pkg = pd.read_parquet(DOCS / contract / "bid_items.parquet")
    pkg = pkg.assign(
        contract_number=contract,
        bid_open_date=on,
        unit_price=np.nan,
        amount=np.nan,
    )
    lines = prepare_lines(pkg, master)
    history = prepare_lines(raw, master)
    history = history[history["bid_open_date"] < on]
    scope = load_scope()
    priced = LinePricer(rows[rows["bid_open_date"] < on], history, scope).price_lines(lines)

    # Production model for the top-100 lines: refreshed Kumo with CQR ranges.
    ref = pd.read_parquet(Path(str(REFRESH).format(model="kumo")))
    key = contract + "|" + on.strftime("%Y-%m-%d") + "|" + priced["item_no"].astype(str)
    line_ref = ref[ref["kind"] == "line"].set_index("key")
    model = key.isin(line_ref.index)
    adj = quarter_adjustment(ref, rows, on)
    priced["source"] = priced["tier"].map(TIER_TEXT)
    priced["low"] = np.nan
    priced["high"] = np.nan
    m = model.to_numpy()
    k = key[m]
    lump = (priced.loc[m, "unit"] == "LS").to_numpy()
    a = np.where(lump, adj[True], adj[False])
    priced.loc[m, "pred_unit_price"] = line_ref.loc[k, "pred_unit_price"].to_numpy()
    priced.loc[m, "low"] = line_ref.loc[k, "pred_q10"].to_numpy() * np.exp(-a)
    priced.loc[m, "high"] = line_ref.loc[k, "pred_q90"].to_numpy() * np.exp(a)
    priced.loc[m, "source"] = "Pricing model (Kumo Tabular), with comparable bids"
    priced.loc[m, "tier"] = 0
    priced["pred_amount"] = priced["pred_unit_price"] * priced["quantity"]
    priced["low_amount"] = priced["low"] * priced["quantity"]
    priced["high_amount"] = priced["high"] * priced["quantity"]

    # Comparable bids for every line with same-item history.
    clean = rows[~rows["low_bidder_disagrees"] & ~rows["is_outlier"] & (rows["unit_price"] > 0)]
    finder = ComparableFinder(clean[clean["bid_open_date"] < on])
    comps = []
    for r in priced.itertuples():
        c = finder.find(
            r.item_code, r.unit, on, r.quantity, info["district"], info["engineers_estimate"]
        )
        if not c.empty:
            comps.append(c.assign(item_no=r.item_no, rank=np.arange(1, len(c) + 1)))
    comps = pd.concat(comps, ignore_index=True) if comps else pd.DataFrame()

    # Actual results, for the check panel only (rank 1 is the low bid; no names).
    actual = raw[(raw["contract_number"] == contract)]
    actual = actual[pd.to_datetime(actual["bid_open_date"]) == on]
    priced = priced.merge(
        actual[["item_no", "unit_price", "amount"]].rename(
            columns={"unit_price": "low_bid_unit_price", "amount": "low_bid_amount"}
        ),
        on="item_no",
        how="left",
    )

    mk = pd.read_csv(MARKET, dtype={"district": str})
    mk = mk[(mk["contract_number"] == contract) & (mk["bid_open_date"] == on.strftime("%Y-%m-%d"))]
    market = mk.iloc[0].to_dict() if len(mk) else {}

    out = APP / contract
    out.mkdir(parents=True, exist_ok=True)
    keep = [
        "item_no",
        "item_code",
        "description",
        "unit",
        "quantity",
        "item_family",
        "pred_unit_price",
        "low",
        "high",
        "pred_amount",
        "low_amount",
        "high_amount",
        "tier",
        "n_history",
        "source",
        "changed_by",
        "low_bid_unit_price",
        "low_bid_amount",
    ]
    priced[keep].to_parquet(out / "estimate.parquet", index=False)
    if len(comps):
        comps.to_parquet(out / "comparables.parquet", index=False)
    summary = {
        "contract": contract,
        "bid_open_date": on.strftime("%Y-%m-%d"),
        "district": str(info["district"]),
        "county": str(info["county"]),
        "type_of_work": str(info["type_of_work"]),
        "working_days": float(info["working_days"]),
        "engineers_estimate": float(info["engineers_estimate"]),
        "low_bid_cost": float(info["low_bid_cost"]),
        "bidders": int(info["n_bidders_ranked"]),
        "estimate_total": float(priced["pred_amount"].sum()),
        "model_lines": int(m.sum()),
        "lines": len(priced),
        "model_share": float(priced.loc[m, "pred_amount"].sum() / priced["pred_amount"].sum()),
        "range_adjustment": {"lump_sum": adj[True], "per_unit": adj[False]},
        "market": {k: (None if pd.isna(v) else v) for k, v in market.items()},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    return summary


def quarter_adjustment(ref: pd.DataFrame, rows: pd.DataFrame, on: pd.Timestamp) -> dict:
    """The D-047 CQR widening for the bid's quarter, from earlier priced bids only."""
    df = ref[ref["kind"].isin(["validation", "test"])].merge(
        rows[["bid_item_id", "unit_price", "unit"]], left_on="key", right_on="bid_item_id"
    )
    df = df.rename(columns={"pred_q10": "q10", "pred_q90": "q90"})
    df["lump_sum"] = df["unit"] == "LS"
    cal = calibrate(df)
    q = cal[cal["bid_open_date"].dt.to_period("Q") == on.to_period("Q")]
    return {ls: float(q.loc[q["lump_sum"] == ls, "adjustment"].iloc[0]) for ls in (True, False)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("contract")
    s = build(ap.parse_args(argv).contract)
    print(json.dumps({k: v for k, v in s.items() if k != "market"}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
