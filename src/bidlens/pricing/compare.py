"""Score pricing benchmarks on the step 2.1 test set (decisions D-034, D-037, D-038).

Usage:
    uv run python -m bidlens.pricing.compare     # writes outputs/08_target_split_metrics

Two benchmarks:
1. Item level: trailing 12-month median low-bid unit price, scored per item family with
   MdAPE and the share within 15%, with and without flagged price outliers.
2. Contract level (the headline): a BidLens contract total built from earlier bids, against
   Caltrans' engineer's estimate, both measured against the actual low bid.

Later steps add their models to the same tables.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from bidlens.pricing.benchmarks import (
    TIERS,
    LinePricer,
    contract_totals,
    headline,
    item_history,
    prepare_lines,
    trailing_median,
)
from bidlens.pricing.escalate import CostIndex
from bidlens.pricing.setup import (
    CUTOFF,
    MIN_FAMILY_TEST,
    TEST_END,
    load_low_bids,
    report_family,
    score,
    select_test,
    use_cost_index,
)

ROOT = Path(".")
DB = ROOT / "data" / "bidlens.duckdb"
ITEMS = ROOT / "data" / "interim" / "bid_summary_items.parquet"
SCOPE = ROOT / "config" / "scope.yaml"
OUT = ROOT / "outputs" / "08_target_split_metrics"


def load_scope(path: Path = SCOPE) -> set[tuple[str, str]]:
    cfg = yaml.safe_load(path.read_text())
    return {(str(i["code"]), str(i["unit"])) for i in cfg["items"]}


def load_contracts(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Test contracts for the headline: after the cutoff, with a bid summary and an
    engineer's estimate, and not flagged low_bidder_disagrees."""
    return con.execute(
        f"""
        SELECT contract_id, contract_number, bid_open_date, district, county,
               CAST(engineers_estimate AS DOUBLE) AS engineers_estimate,
               CAST(low_bid_cost AS DOUBLE) AS low_bid_cost, is_a_plus_b, n_bidders
        FROM contract c
        WHERE has_bid_summary AND engineers_estimate IS NOT NULL AND low_bid_cost > 0
          AND bid_open_date BETWEEN DATE '{CUTOFF}' AND DATE '{TEST_END}'
          AND contract_id NOT IN (
              SELECT contract_id FROM contract_flag WHERE flag = 'low_bidder_disagrees')
        ORDER BY bid_open_date, contract_number
        """
    ).df()


def item_benchmark(low: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Predictions for every test price, and the per-family score table."""
    test = select_test(low)
    pred = trailing_median(test, item_history(low))
    pred["family"] = report_family(pred["item_family"])
    pred["year"] = pred["bid_open_date"].dt.year
    tables = []
    for label, df in (("all prices", pred), ("without outliers", pred[~pred["is_outlier"]])):
        for by in ("family", "year"):
            t = score(df, by)
            t.insert(0, "by", by)
            t.insert(0, "test_set", label)
            tables.append(t)
    return pred, pd.concat(tables, ignore_index=True)


def contract_benchmark(
    low: pd.DataFrame,
    raw_lines: pd.DataFrame,
    master: pd.DataFrame,
    contracts: pd.DataFrame,
    scope: set[tuple[str, str]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    lines = prepare_lines(raw_lines, master)
    pricer = LinePricer(low, lines, scope)
    keys = contracts[["contract_number", "bid_open_date"]].assign(
        bid_open_date=lambda d: pd.to_datetime(d["bid_open_date"])
    )
    targets = lines.merge(keys, on=["contract_number", "bid_open_date"], how="inner")
    priced = pricer.price_lines(targets)
    return priced, contract_totals(priced, contracts)


def split_summary(low: pd.DataFrame, contracts: pd.DataFrame, n_ee: int) -> pd.DataFrame:
    test = select_test(low)
    rows = [
        (
            "Low-bid prices, train (before cutoff)",
            (low["split"] == "train").sum(),
            low.loc[low["split"] == "train", "contract_id"].nunique(),
        ),
        (
            "Low-bid prices, test period",
            (low["split"] == "test").sum(),
            low.loc[low["split"] == "test", "contract_id"].nunique(),
        ),
        ("Test prices after exclusions", len(test), test["contract_id"].nunique()),
        (
            "  of which flagged price outliers",
            int(test["is_outlier"].sum()),
            test.loc[test["is_outlier"], "contract_id"].nunique(),
        ),
        ("Test contracts with an engineer's estimate and item lines", None, n_ee),
        (
            "Headline contracts (90%+ lines with item-level history)",
            None,
            int(contracts["in_headline"].sum()),
        ),
    ]
    return pd.DataFrame(rows, columns=["set", "prices", "contracts"])


def tier_summary(priced: pd.DataFrame, totals: pd.DataFrame) -> pd.DataFrame:
    head = priced.merge(
        totals.loc[totals["in_headline"], ["contract_number", "bid_open_date"]],
        on=["contract_number", "bid_open_date"],
    )
    rows = []
    for label, df in (("all test contracts", priced), ("headline contracts", head)):
        total = df["pred_amount"].sum()
        for t, desc in TIERS.items():
            sel = df["tier"] == t
            rows.append(
                {
                    "contracts": label,
                    "tier": t,
                    "description": desc,
                    "lines": int(sel.sum()),
                    "share_of_lines": sel.mean(),
                    "share_of_bidlens_dollars": df.loc[sel, "pred_amount"].sum() / total,
                }
            )
    return pd.DataFrame(rows)


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def _md_table(df: pd.DataFrame) -> list[str]:
    lines = [
        "| Group | Prices | Coverage | MdAPE | Within 15% |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for r in df.itertuples(index=False):
        lines.append(
            f"| {r.group} | {int(r.n):,} | {_pct(r.coverage)} | {_pct(r.mdape)} | "
            f"{_pct(r.within_15)} |"
        )
    return lines


def write_outputs(
    out: Path,
    pred: pd.DataFrame,
    scores: pd.DataFrame,
    priced: pd.DataFrame,
    totals: pd.DataFrame,
    split: pd.DataFrame,
    tiers: pd.DataFrame,
    result: dict,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    split.to_csv(out / "split_summary.csv", index=False)
    scores.to_csv(out / "item_benchmark_scores.csv", index=False, float_format="%.4f")
    pred[
        [
            "bid_item_id",
            "contract_number",
            "bid_open_date",
            "district",
            "item_code",
            "unit",
            "family",
            "quantity",
            "unit_price",
            "pred",
            "n_history",
            "is_outlier",
        ]
    ].rename(columns={"unit_price": "low_bid_unit_price", "pred": "trailing_median"}).to_csv(
        out / "item_benchmark_predictions.csv",
        index=False,
        float_format="%.4f",
        date_format="%Y-%m-%d",
    )
    totals[
        [
            "contract_number",
            "bid_open_date",
            "district",
            "county",
            "is_a_plus_b",
            "n_bidders",
            "n_lines",
            "share_lines_item_level",
            "in_headline",
            "low_bid_cost",
            "engineers_estimate",
            "bidlens_total",
            "ee_error",
            "bidlens_error",
            "bidlens_closer",
            *[f"tier{t}_share" for t in TIERS],
        ]
    ].to_csv(out / "contract_totals.csv", index=False, float_format="%.4f", date_format="%Y-%m-%d")
    priced[
        [
            "contract_number",
            "bid_open_date",
            "item_no",
            "item_code",
            "description",
            "unit",
            "quantity",
            "unit_price",
            "pred_unit_price",
            "tier",
            "n_history",
        ]
    ].rename(columns={"unit_price": "low_bid_unit_price"}).to_csv(
        out / "contract_line_prices.csv",
        index=False,
        float_format="%.4f",
        date_format="%Y-%m-%d",
    )
    tiers.to_csv(out / "pricing_tiers.csv", index=False, float_format="%.4f")
    (out / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    _write_readme(out, scores, split, tiers, result)


def _write_readme(out, scores, split, tiers, result) -> None:
    h, a = result["contract_level"]["headline"], result["contract_level"]["all_test_contracts"]
    fam = scores[(scores["test_set"] == "all prices") & (scores["by"] == "family")]
    fam_clean = scores[(scores["test_set"] == "without outliers") & (scores["by"] == "family")]
    year = scores[(scores["test_set"] == "all prices") & (scores["by"] == "year")]
    split_lines = ["| Set | Prices | Contracts |", "| --- | ---: | ---: |"]
    for r in split.itertuples(index=False):
        p = "" if pd.isna(r.prices) else f"{int(r.prices):,}"
        split_lines.append(f"| {r.set.strip()} | {p} | {int(r.contracts):,} |")
    tier_lines = [
        "| Tier | How the line is priced | Share of lines | Share of BidLens dollars |",
        "| ---: | --- | ---: | ---: |",
    ]
    for r in tiers[tiers["contracts"] == "headline contracts"].itertuples(index=False):
        tier_lines.append(
            f"| {r.tier} | {r.description} | {_pct(r.share_of_lines)} | "
            f"{_pct(r.share_of_bidlens_dollars)} |"
        )

    def _cmp(d: dict) -> list[str]:
        return [
            "| Measure | Historical-median total | Engineer's estimate |",
            "| --- | ---: | ---: |",
            f"| Median distance from the low bid | {_pct(d['bidlens_median_abs_error'])} | "
            f"{_pct(d['ee_median_abs_error'])} |",
            f"| Median over (+) or under (-) the low bid | {_pct(d['bidlens_median_error'])} | "
            f"{_pct(d['ee_median_error'])} |",
            f"| Within 15% of the low bid | {_pct(d['bidlens_within_15'])} | "
            f"{_pct(d['ee_within_15'])} |",
        ]

    body = f"""
How BidLens will be tested, and how well two simple yardsticks do on that test (step 2.1).

## The question

Before building pricing models, we fix the rules of the test so every later model is
judged the same way, and we score two yardsticks that any model has to beat.

## The test (decision D-034)

- **What is predicted:** the low bidder's unit price for each bid item (models work on its
  logarithm, because prices span several orders of magnitude).
- **Time split:** models learn from bids opened before {CUTOFF:%d %B %Y} and are tested on
  bids opened from then to {TEST_END:%d %B %Y}. Never a random split: an estimator only ever
  knows the past.
- **Left out of the test:** contracts where the cost database and the bid summary disagree
  on who was low (stage 05), and any price of $0 or less. Unusual prices flagged in stage
  05 stay in; results are shown with and without them.
- **Scores:** the median percentage miss (MdAPE: half of the predictions miss by less than
  this) and the share of predictions within 15% of the low bid. Item families with fewer
  than {MIN_FAMILY_TEST} test prices are grouped as "Other".
- **Price levels:** every earlier price is brought to the bid date of the price being
  predicted with Caltrans' cost index, as known before that bid opened (stage 09).

{chr(10).join(split_lines)}

## Headline: whole-contract totals (decisions D-037, D-038)

The estimator's real question: would BidLens's total have been closer to the winning bid
than Caltrans' own engineer's estimate? Until the pricing model exists, BidLens's total here
is a **historical-median total**: every line of the low bidder's item list, priced at the
median of earlier low bids for the same item, times the bid quantity. Nothing from the
contract being priced is used except its item list and quantities.

The headline uses the {h["contracts"]} test contracts where at least 90% of lines have
price history for that exact item (all {a["contracts"]} contracts are shown below too).
Contracts need a bid summary with its item lines: three test-period summaries were read
by OCR with their header only (decision D-026), so they have no lines to price.

**The historical-median total landed closer to the low bid than the engineer's estimate on
{_pct(h["bidlens_closer_share"])} of headline contracts.**

{chr(10).join(_cmp(h))}

All {a["contracts"]} test contracts with an engineer's estimate: closer on
{_pct(a["bidlens_closer_share"])}.

{chr(10).join(_cmp(a))}

How the lines of the headline contracts were priced:

{chr(10).join(tier_lines)}

## Item level: trailing 12-month median

For each test price, the yardstick is the median low-bid unit price for the same item and
unit over the 12 months before the bid (all earlier bids when the 12 months hold fewer than
3). Coverage is the share of test prices that had any earlier bid.

The misses are large because a plain median ignores the size of the job. A third of test
prices are lump sums (mobilization, traffic control, job site management) whose price
grows with the contract, and unit prices for quantities like asphalt tonnage drop sharply
as quantities grow. This is the gap the pricing models in steps 2.3 to 2.5 have to close.

All test prices:

{chr(10).join(_md_table(fam))}

Without flagged outliers:

{chr(10).join(_md_table(fam_clean))}

By bid year (all test prices):

{chr(10).join(_md_table(year))}

## Files

- `split_summary.csv`: the counts in the split table above.
- `item_benchmark_scores.csv`: item-level scores by family and by year, with and without outliers.
- `item_benchmark_predictions.csv`: every test price with its trailing-median prediction and
  how many earlier prices it used.
- `contract_totals.csv`: every test contract: low bid, engineer's estimate, historical-median
  total, errors, and the share of BidLens dollars from each pricing tier.
- `contract_line_prices.csv`: every priced line of those contracts, with its tier.
- `pricing_tiers.csv`: the share of lines and dollars from each pricing tier.
- `results.json`: the headline numbers.

No file names a bidder. Contracts are identified by their Caltrans contract number.

## How it was produced

`uv run python -m bidlens.pricing.compare` (code in `src/bidlens/pricing/`), from
`data/bidlens.duckdb` and the bid summary item lines. Generated {date.today().isoformat()}.
"""
    (out / "README.md").write_text(
        "# 08 Target, split and metrics\n\n" + body.strip() + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    con = duckdb.connect(str(DB), read_only=True)
    use_cost_index(CostIndex.from_db(con))
    low = load_low_bids(con)
    contracts = load_contracts(con)
    master = con.execute(
        "SELECT item_code, unit, item_family FROM item_master ORDER BY item_code"
    ).df()
    raw_lines = con.execute(
        f"SELECT * FROM read_parquet('{ITEMS}') ORDER BY contract_number, bid_open_date, item_no"
    ).df()
    con.close()

    pred, scores = item_benchmark(low)
    priced, totals = contract_benchmark(low, raw_lines, master, contracts, load_scope())
    split = split_summary(low, totals, len(totals))
    tiers = tier_summary(priced, totals)
    overall = scores[(scores["by"] == "family") & (scores["group"] == "All")]
    result = {
        "cutoff": str(CUTOFF),
        "test_end": str(TEST_END),
        "item_level": {
            r.test_set: {
                "n": int(r.n),
                "coverage": r.coverage,
                "mdape": r.mdape,
                "within_15": r.within_15,
            }
            for r in overall.itertuples(index=False)
        },
        "contract_level": headline(totals),
    }
    write_outputs(OUT, pred, scores, priced, totals, split, tiers, result)

    from bidlens.outputs import write_index

    write_index()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
