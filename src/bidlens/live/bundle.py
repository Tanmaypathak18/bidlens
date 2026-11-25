"""The data bundle the live evaluation runs on.

Usage:
    uv run python -m bidlens.live.bundle     # writes data/sample/engine/ from the database

The bundle holds only public Caltrans facts, with no bidder names:
- bids.parquet: every low bid (rank 1) with its flags, contract fields, model features and
  target. Each row's features use only strictly earlier bids, so they are the same
  whatever date is evaluated later.
- lines.parquet: the low bidders' full item lists from the bid summaries (history pricing
  for items outside the top 100, and the item lists of past contracts).
- contracts.parquet: one row per bid opening (engineer's estimate, low and second bid,
  bidders, plan holders, work and location).
- item_master.parquet, cost_index.parquet, scope.parquet, meta.json.

`load()` reads it with pandas only, so the hosted demo needs no database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / "data" / "sample" / "engine"
DB = ROOT / "data" / "bidlens.duckdb"
ITEMS = ROOT / "data" / "interim" / "bid_summary_items.parquet"
SUMMARIES = ROOT / "data" / "interim" / "bid_summaries.parquet"
BASELINES = ROOT / "outputs" / "10_baselines" / "results.json"

LINE_COLS = ["contract_number", "bid_open_date", "item_no", "item_code", "description", "unit",
             "quantity", "unit_price", "amount"]  # fmt: skip


def build(out: Path = BUNDLE) -> dict:
    import duckdb

    from bidlens.pricing import features as F
    from bidlens.pricing.compare import load_scope
    from bidlens.pricing.escalate import SERIES, CostIndex
    from bidlens.pricing.setup import use_cost_index

    con = duckdb.connect(str(DB), read_only=True)
    ci = con.execute(
        "SELECT year, quarter, value FROM cost_index WHERE series = ? ORDER BY 1, 2", [SERIES]
    ).df()
    use_cost_index(CostIndex(ci))
    rows = F.load_model_rows(con)
    src = con.execute("SELECT bid_item_id, source_row_id FROM bid WHERE bid_rank = 1").df()
    rows = rows.merge(src, on="bid_item_id", how="left")
    X = F.build(rows, rows)
    bids = rows.copy()
    for c in F.NUMERIC:
        bids[c] = X[c].to_numpy()
    bids["y"] = np.log(F.to_ref(bids["unit_price"].clip(lower=1e-9), bids["bid_open_date"]))
    bids = bids.drop(columns=["contract_id", "split"]).sort_values("bid_item_id")

    master = con.execute(
        "SELECT item_code, unit, item_family, description FROM item_master ORDER BY 1"
    ).df()
    contracts = con.execute(
        """SELECT contract_id, contract_number, bid_open_date, district, county, location,
                  type_of_work, n_items, working_days, proposals_issued, is_a_plus_b,
                  has_bid_summary, n_bidders,
                  CAST(engineers_estimate AS DOUBLE) AS engineers_estimate,
                  CAST(low_bid_cost AS DOUBLE) AS low_bid_cost,
                  CAST(low_bid_total AS DOUBLE) AS low_bid_total,
                  CAST(second_bid_total AS DOUBLE) AS second_bid_total,
                  EXISTS (SELECT 1 FROM contract_flag f WHERE f.contract_id = c.contract_id
                          AND f.flag = 'low_bidder_disagrees') AS low_bidder_disagrees
           FROM contract c ORDER BY bid_open_date, contract_id"""
    ).df()
    con.close()
    lines = pd.read_parquet(ITEMS)[LINE_COLS].sort_values(
        ["contract_number", "bid_open_date", "item_no"]
    )
    lines["bid_open_date"] = pd.to_datetime(lines["bid_open_date"])
    contracts["bid_open_date"] = pd.to_datetime(contracts["bid_open_date"])
    scope = pd.DataFrame(sorted(load_scope()), columns=["item_code", "unit"])

    out.mkdir(parents=True, exist_ok=True)
    bids.to_parquet(out / "bids.parquet", index=False, compression="zstd")
    lines.to_parquet(out / "lines.parquet", index=False, compression="zstd")
    contracts.to_parquet(out / "contracts.parquet", index=False, compression="zstd")
    master.to_parquet(out / "item_master.parquet", index=False, compression="zstd")
    ci.to_parquet(out / "cost_index.parquet", index=False)
    scope.to_parquet(out / "scope.parquet", index=False)
    lgb = json.loads(BASELINES.read_text())["models"]["lightgbm"]
    meta = {
        "built": date.today().isoformat(),
        "bids_through": bids["bid_open_date"].max().strftime("%Y-%m-%d"),
        "cost_index_series": SERIES,
        "lightgbm": {"params": lgb["params"], "trees": int(lgb["trees"])},
        "rows": {"bids": len(bids), "lines": len(lines), "contracts": len(contracts)},
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


@dataclass
class Bundle:
    bids: pd.DataFrame
    lines: pd.DataFrame
    contracts: pd.DataFrame
    master: pd.DataFrame
    cost_index: pd.DataFrame
    scope: set[tuple[str, str]]
    meta: dict


def load(path: Path = BUNDLE) -> Bundle:
    bids = pd.read_parquet(path / "bids.parquet")
    lines = pd.read_parquet(path / "lines.parquet")
    contracts = pd.read_parquet(path / "contracts.parquet")
    for df in (bids, lines, contracts):
        df["bid_open_date"] = pd.to_datetime(df["bid_open_date"])
    scope = pd.read_parquet(path / "scope.parquet")
    return Bundle(
        bids=bids,
        lines=lines,
        contracts=contracts,
        master=pd.read_parquet(path / "item_master.parquet"),
        cost_index=pd.read_parquet(path / "cost_index.parquet"),
        scope=set(zip(scope["item_code"], scope["unit"], strict=True)),
        meta=json.loads((path / "meta.json").read_text()),
    )


def main() -> None:
    meta = build()
    size = sum(p.stat().st_size for p in BUNDLE.iterdir())
    print(json.dumps(meta["rows"]), f"{size / 1e6:.2f} MB in {BUNDLE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
