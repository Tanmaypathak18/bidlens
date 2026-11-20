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
                  CAST(low_bid_cost AS DOUBLE) AS low_bid_cost, n_bidders AS n_bidders_ranked,
                  proposals_issued
           FROM contract WHERE contract_number = ? ORDER BY bid_open_date DESC""",
        [contract],
    ).df()
    if df.empty:
        raise SystemExit(f"{contract} is not in the database")
    r = df.iloc[0].copy()
    r["bid_open_date"] = pd.Timestamp(r["bid_open_date"])
    return r


def notice(contract: str) -> dict:
    """Work description, location and routes from the Notice to Bidders page."""
    import re

    pages = pd.read_parquet(DOCS / contract / "pages.parquet")
    hit = pages[pages["text"].str.contains("General work description", na=False)]
    if hit.empty:
        return {}
    t = re.sub(r"\s+", " ", hit.iloc[0]["text"])
    out = {}
    m = re.search(r"General work description: (.+?\.)(?= [A-Z])", t)
    if m:
        out["work"] = m.group(1).rstrip(".")
    m = re.search(r"following work: (.+?)\.(?= )", t)
    if m:
        out["where"] = m.group(1).capitalize()
    m = re.search(r"District-County-Route-Post Mile: \d+-([^-]+)-(.+?)-", t)
    if m:
        out["routes"] = "Routes " + m.group(2).replace(",", ", ").replace("  ", " ")
    return out


def key_dates(contract: str) -> list[dict]:
    """Notice and addendum dates, the prebid meeting and bid opening, each with its page."""
    import re

    from bidlens.documents.patterns import MONTH, match

    pages = pd.read_parquet(DOCS / contract / "pages.parquet")
    chunks = pd.read_parquet(DOCS / contract / "chunks.parquet")
    out = []
    note = pages[pages["text"].str.contains("General work description", na=False)]
    if len(note):
        m = re.search(r"Dated (" + MONTH + ")", note.iloc[0]["text"])
        if m:
            out.append(
                {
                    "date": m.group(1),
                    "label": "Bid package issued",
                    "file": note.iloc[0]["file"],
                    "page": int(note.iloc[0]["page"]),
                }  # fmt: skip
            )
    for r in pages[(pages["kind"] == "addendum") & (pages["page"] == 1)].itertuples():
        m = re.search(MONTH, r.text)
        n = re.search(r"ADDENDUM NO\.? ?(\d+)", r.text, re.I)
        if m and n:
            out.append({"date": m.group(0), "label": f"Addendum {n.group(1)}",
                        "file": r.file, "page": int(r.page)})  # fmt: skip
    found = {f["rule"]: f for f in match(chunks)}
    for rule, label in (("prebid", "Mandatory prebid meeting"), ("bid_open", "Bids open")):
        if rule in found:
            f = found[rule]
            m = re.search(MONTH, f["value"])
            file, pg = f["chunk_id"].split(":")[0], int(f["chunk_id"].split(":p")[1].split(":")[0])
            out.append({"date": m.group(0), "label": label, "file": file, "page": pg})
    for d in out:
        d["date"] = pd.to_datetime(re.sub(r"\bSept\b", "Sep", d["date"])).strftime("%Y-%m-%d")
    return sorted(out, key=lambda d: d["date"])


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

    # Price history per line: every earlier cleaned low bid for the same code and unit.
    from bidlens.pricing.setup import escalate

    past = clean[clean["bid_open_date"] < on]
    hist = []
    for r in priced.itertuples():
        h = past[(past["item_code"] == r.item_code) & (past["unit"] == r.unit)]
        if h.empty and not r.special:  # other items: low bidders' lines in bid summaries
            h = history[(history["item_code"] == r.item_code) & (history["unit"] == r.unit)]
            h = h[h["unit_price"] > 0]
        if len(h):
            hist.append(
                pd.DataFrame(
                    {
                        "item_no": r.item_no,
                        "bid_open_date": h["bid_open_date"].to_numpy(),
                        "quantity": h["quantity"].to_numpy(),
                        "unit_price": h["unit_price"].to_numpy(dtype=float),
                        "unit_price_in_bid_dollars": escalate(
                            h["unit_price"].to_numpy(dtype=float), h["bid_open_date"], on
                        ),
                    }
                )
            )
    history_df = pd.concat(hist, ignore_index=True) if hist else pd.DataFrame()

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
    if len(history_df):
        history_df.to_parquet(out / "history.parquet", index=False)
    summary = {
        "contract": contract,
        "bid_open_date": on.strftime("%Y-%m-%d"),
        "district": str(info["district"]),
        "county": str(info["county"]),
        "type_of_work": str(info["type_of_work"]),
        **notice(contract),
        "key_dates": key_dates(contract),
        "working_days": float(info["working_days"]),
        "engineers_estimate": float(info["engineers_estimate"]),
        "low_bid_cost": float(info["low_bid_cost"]),
        "bidders": int(info["n_bidders_ranked"]),
        "plan_holders": None
        if pd.isna(info["proposals_issued"])
        else int(info["proposals_issued"]),
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


OUT = ROOT / "outputs" / "21_app"


def write_outputs(contract: str, s: dict, seconds: float) -> None:
    """outputs/21_app: the draft estimate as CSV, the workbook, and a README."""
    from datetime import date

    from bidlens.documents.extract import DEFAULT_RUN
    from bidlens.export import workbook

    OUT.mkdir(parents=True, exist_ok=True)
    est = pd.read_parquet(APP / contract / "estimate.parquet")
    est.drop(columns=["tier"]).to_csv(OUT / f"draft_estimate_{contract}.csv", index=False)
    (OUT / f"draft_estimate_{contract}.xlsx").write_bytes(workbook(contract))
    m = est["tier"] == 0
    chk = est.loc[m].dropna(subset=["low_bid_unit_price"])
    inside = (chk["low_bid_unit_price"] >= chk["low"]) & (chk["low_bid_unit_price"] <= chk["high"])
    mk = s.get("market") or {}
    ee, low, tot = s["engineers_estimate"], s["low_bid_cost"], s["estimate_total"]
    (OUT / "README.md").write_text(
        f"""# 21 App

The draft estimate the BidLens app shows for the sample bid package {contract}
(steps 4.1 and 4.2, decisions D-064 and D-065), and the workbook it exports.

## The draft

| | Amount | vs the actual low bid |
| --- | ---: | ---: |
| BidLens draft total (likely prices) | ${tot:,.0f} | {100 * (tot / low - 1):+.1f}% |
| Engineer's estimate | ${ee:,.0f} | {100 * (ee / low - 1):+.1f}% |
| Actual low bid (rank 1, public result) | ${low:,.0f} | |

- {s["lines"]} bid items from the package's bid item list; {int(m.sum())} of them
  ({100 * s["model_share"]:.0f}% of the draft total) priced by the pricing model with a
  low to high range. The rest come from earlier low bids for the same item, as in step 2.1.
- On the {len(chk)} modeled items, the low bidder's unit price fell inside the BidLens
  range on {100 * inside.mean():.0f}% (the range is built to hold 8 in 10).
- Market context: the low bid was expected about {100 * mk.get("spread_kumo", float("nan")):+.0f}%
  from the engineer's estimate (likely {100 * mk.get("spread_low", float("nan")):+.0f}% to
  {100 * mk.get("spread_high", float("nan")):+.0f}%); it came in at {100 * (low / ee - 1):+.0f}%.
  Expected bidders {mk.get("bidders_kumo", float("nan")):.0f}; actual {s["bidders"]}.
- The actual results are used only for this check, never in the draft.

Document findings in the app and the workbook come from the `{DEFAULT_RUN}` extraction run
(stage 20).

## Files

- `draft_estimate_{contract}.csv`: every bid item with low, likely and high unit price,
  amount, source, and the low bidder's unit price for the check.
- `draft_estimate_{contract}.xlsx`: the exported workbook (Estimate with live formulas,
  Comparables, Risk register, Closure hours, About).

## How it was produced

`uv run python -m bidlens.estimate {contract}` ({seconds:.0f} seconds), then the app:
`uv run streamlit run app/Home.py`. Code in `src/bidlens/estimate.py`,
`src/bidlens/export.py` and `app/`. Generated {date.today().isoformat()}.
""",
        encoding="utf-8",
    )
    from bidlens.outputs import write_index

    write_index()


def main(argv: list[str] | None = None) -> int:
    import time

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("contract")
    contract = ap.parse_args(argv).contract
    t0 = time.perf_counter()
    s = build(contract)
    write_outputs(contract, s, time.perf_counter() - t0)
    print(json.dumps({k: v for k, v in s.items() if k != "market"}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
