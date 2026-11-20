"""Data quality checks (step 1.6, decision D-033).

Usage:
    uv run python -m bidlens.db.checks    # updates the database and outputs/05_data_quality

Flags are stored in the tables `bid_flag` and `contract_flag` and are never used to delete
data. The report is outputs/05_data_quality/data_quality.md.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import duckdb

ROBUST_Z_LIMIT = 3.5
MIN_GROUP = 20
TOTAL_TOLERANCE = 0.01

BID_CHECKS = {
    "missing_value": "A required price field is empty",
    "non_positive_price": "Unit price is zero or negative",
    "duplicate_bid": "The same bid appears twice (same item line and rank, or the same source row)",
    "total_mismatch": "Total differs from quantity × unit price by more than 1%",
    "price_outlier": (
        f"Robust z-score of log unit price above {ROBUST_Z_LIMIT} within the item and unit"
    ),
}
CONTRACT_CHECKS = {
    "low_bidder_disagrees": "The cost database's rank-1 bidder is not the bid summary's low bidder",
    "bidder_count_mismatch": (
        "Highest bid rank in the cost database differs from ranked bidders in the summary"
    ),
    "missing_engineers_estimate": "No engineer's estimate (no usable bid summary)",
}


def run_checks(con: duckdb.DuckDBPyConnection, interim: Path) -> dict:
    con.execute("""
        CREATE OR REPLACE TABLE bid_flag (
            bid_item_id VARCHAR, bid_rank INTEGER, flag VARCHAR, detail VARCHAR
        )
    """)
    con.execute("""
        CREATE OR REPLACE TABLE contract_flag (contract_id VARCHAR, flag VARCHAR, detail VARCHAR)
    """)
    con.execute("""
        INSERT INTO bid_flag
        SELECT bid_item_id, bid_rank, 'missing_value', 'unit_price or total is empty'
        FROM bid WHERE unit_price IS NULL OR total IS NULL
    """)
    con.execute("""
        INSERT INTO bid_flag
        SELECT bid_item_id, bid_rank, 'non_positive_price', 'unit price ' || unit_price
        FROM bid WHERE unit_price <= 0
    """)
    con.execute("""
        INSERT INTO bid_flag
        SELECT bid_item_id, bid_rank, 'duplicate_bid', 'source row ' || source_row_id
        FROM (SELECT *, count(*) OVER (PARTITION BY source_row_id) n1,
                        count(*) OVER (PARTITION BY bid_item_id, bid_rank) n2 FROM bid)
        WHERE n1 > 1 OR n2 > 1
    """)
    con.execute(f"""
        INSERT INTO bid_flag
        SELECT b.bid_item_id, b.bid_rank, 'total_mismatch',
               'quantity × price = ' || round(i.quantity * b.unit_price, 2)
                   || ', total = ' || b.total
        FROM bid b JOIN bid_item i USING (bid_item_id)
        WHERE b.unit_price > 0
          AND abs(i.quantity * b.unit_price - b.total) > {TOTAL_TOLERANCE} * b.total
    """)
    con.execute(f"""
        INSERT INTO bid_flag
        WITH p AS (
            SELECT b.bid_item_id, b.bid_rank, i.item_code, i.unit, ln(b.unit_price) AS lp
            FROM bid b JOIN bid_item i USING (bid_item_id) WHERE b.unit_price > 0
        ),
        g AS (
            SELECT item_code, unit, median(lp) AS med, count(*) AS n FROM p GROUP BY ALL
        ),
        m AS (
            SELECT p.item_code, p.unit, median(abs(p.lp - g.med)) AS mad
            FROM p JOIN g USING (item_code, unit) GROUP BY ALL
        ),
        z AS (
            SELECT p.*, 0.6745 * (p.lp - g.med) / m.mad AS rz, exp(g.med) AS median_price
            FROM p JOIN g USING (item_code, unit) JOIN m USING (item_code, unit)
            WHERE g.n >= {MIN_GROUP} AND m.mad > 0
        )
        SELECT bid_item_id, bid_rank, 'price_outlier',
               'robust z ' || round(rz, 1) || ' (median price ' || round(median_price, 2) || ')'
        FROM z WHERE abs(rz) > {ROBUST_Z_LIMIT}
    """)

    summaries = interim / "bid_summary_items.parquet"
    if summaries.exists():
        con.execute(f"""
            INSERT INTO contract_flag
            WITH s AS (
                SELECT contract_number || '_' || strftime(bid_open_date, '%Y-%m-%d') AS contract_id,
                       item_code, unit_price AS pdf_price, quantity AS pdf_qty
                FROM read_parquet('{summaries}')
            ),
            pairs AS (
                SELECT i.contract_id, abs(b.unit_price - s.pdf_price) >= 0.005 AS differs
                FROM bid b JOIN bid_item i USING (bid_item_id)
                JOIN s ON s.contract_id = i.contract_id AND s.item_code = i.item_code
                WHERE b.bid_rank = 1 AND (s.pdf_qty IS NULL OR abs(s.pdf_qty - i.quantity) < 0.001)
            )
            SELECT contract_id, 'low_bidder_disagrees',
                   sum(differs::INT) || ' of ' || count(*) || ' compared prices differ'
            FROM pairs GROUP BY contract_id HAVING avg(differs::INT) >= 0.5
        """)
    con.execute("""
        INSERT INTO contract_flag
        SELECT contract_id, 'bidder_count_mismatch',
               'cost database ' || n_bidders_sv08 || ', bid summary ' || n_bidders
        FROM contract
        WHERE n_bidders IS NOT NULL AND n_bidders_sv08 IS NOT NULL AND n_bidders <> n_bidders_sv08
    """)
    con.execute("""
        INSERT INTO contract_flag
        SELECT contract_id, 'missing_engineers_estimate',
               CASE WHEN has_bid_summary THEN 'not readable' ELSE 'no usable bid summary' END
        FROM contract WHERE engineers_estimate IS NULL
    """)

    total_bids = con.execute("SELECT count(*) FROM bid").fetchone()[0]
    total_contracts = con.execute("SELECT count(*) FROM contract").fetchone()[0]
    bid_counts = dict(con.execute("SELECT flag, count(*) FROM bid_flag GROUP BY 1").fetchall())
    contract_counts = dict(
        con.execute("SELECT flag, count(*) FROM contract_flag GROUP BY 1").fetchall()
    )
    flagged_bids = con.execute(
        "SELECT count(*) FROM (SELECT DISTINCT bid_item_id, bid_rank FROM bid_flag)"
    ).fetchone()[0]
    return {
        "total_bids": total_bids,
        "total_contracts": total_contracts,
        "bid_flags": {k: bid_counts.get(k, 0) for k in BID_CHECKS},
        "contract_flags": {k: contract_counts.get(k, 0) for k in CONTRACT_CHECKS},
        "bids_with_any_flag": flagged_bids,
    }


def write_report(con: duckdb.DuckDBPyConnection, result: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
        COPY (
            SELECT c.contract_number, strftime(c.bid_open_date, '%Y-%m-%d') AS bid_open_date,
                   i.item_code, i.unit, i.quantity::DOUBLE AS quantity,
                   b.unit_price::DOUBLE AS unit_price, b.total::DOUBLE AS total, f.bid_rank,
                   f.flag, f.detail,
                   'https://sv08data.dot.ca.gov/details.php?Num=' || b.source_row_id AS source_url
            FROM bid_flag f JOIN bid b USING (bid_item_id, bid_rank)
            JOIN bid_item i USING (bid_item_id) JOIN contract c USING (contract_id)
            ORDER BY f.flag, c.bid_open_date, c.contract_number, i.item_code, f.bid_rank
        ) TO '{out / "bid_flags.csv"}' (HEADER)
    """)
    con.execute(f"""
        COPY (
            SELECT c.contract_number, strftime(c.bid_open_date, '%Y-%m-%d') AS bid_open_date,
                   f.flag, f.detail
            FROM contract_flag f JOIN contract c USING (contract_id)
            ORDER BY f.flag, c.bid_open_date, c.contract_number
        ) TO '{out / "contract_flags.csv"}' (HEADER)
    """)
    outliers_by_item = con.execute("""
        SELECT i.item_code, any_value(i.item_description), count(*) AS flagged,
               (SELECT count(*) FROM bid b2 JOIN bid_item i2 USING (bid_item_id)
                WHERE i2.item_code = i.item_code) AS bids
        FROM bid_flag f JOIN bid_item i USING (bid_item_id)
        WHERE f.flag = 'price_outlier' GROUP BY i.item_code ORDER BY flagged DESC LIMIT 10
    """).fetchall()
    rank_split = con.execute("""
        SELECT count(*) FILTER (WHERE bid_rank = 1), count(*) FILTER (WHERE bid_rank > 1)
        FROM bid_flag WHERE flag = 'price_outlier'
    """).fetchone()
    tb, tc = result["total_bids"], result["total_contracts"]
    lines = [
        "# Data quality report (step 1.6)",
        "",
        f"Generated {date.today().isoformat()} from `data/bidlens.duckdb` by "
        "`uv run python -m bidlens.db.checks` (part of `make data`). Rules: decision D-033. "
        "Nothing is deleted. Flags sit in the database tables `bid_flag` and `contract_flag` "
        "and in the CSV files next to this report.",
        "",
        "## Bid price checks",
        "",
        f"{tb:,} bid prices checked.",
        "",
        "| Check | What it means | Bids flagged | Share |",
        "| --- | --- | --- | --- |",
    ]
    for key, desc in BID_CHECKS.items():
        n = result["bid_flags"][key]
        lines.append(f"| {key} | {desc} | {n:,} | {n / tb:.2%} |")
    lines += [
        f"| **any flag** | | **{result['bids_with_any_flag']:,}** | "
        f"**{result['bids_with_any_flag'] / tb:.2%}** |",
        "",
        f"Price outliers by bid rank: {rank_split[0]:,} low bids (rank 1) and {rank_split[1]:,} "
        "higher bids. High outliers are often small quantities or unusual work. Low outliers "
        "are often unbalanced bids. Both can be real, so they are flagged for the models to "
        "handle, not removed.",
        "",
        "**Items with the most outlier flags:**",
        "",
        "| Item | Description | Flagged | Bids | Share |",
        "| --- | --- | --- | --- | --- |",
    ]
    for code, desc, n, total in outliers_by_item:
        lines.append(f"| {code} | {desc} | {n} | {total:,} | {n / total:.1%} |")
    lines += [
        "",
        "## Contract checks",
        "",
        f"{tc:,} contract openings checked.",
        "",
        "| Check | What it means | Contracts flagged |",
        "| --- | --- | --- |",
    ]
    for key, desc in CONTRACT_CHECKS.items():
        lines.append(f"| {key} | {desc} | {result['contract_flags'][key]:,} |")
    lines += [
        "",
        "**How to read these:**",
        "- `low_bidder_disagrees` marks contracts where the two Caltrans sources name different "
        "low bidders, most likely because a low bid was later rejected. Rank-1 prices in these "
        "contracts may not be the winning prices (see `04_cross_check`).",
        "- `missing_engineers_estimate` contracts are listed with their reasons in "
        "`missing_data.csv`.",
        "",
        "## Files",
        "",
        "- `bid_flags.csv`: every flagged bid price, with its flag, detail and source link.",
        "- `contract_flags.csv`: every flagged contract.",
        "- `missing_data.csv` and `missing_data.md`: missing contract-level fields (step 1.5).",
    ]
    (out / "data_quality.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=Path("data/bidlens.duckdb"))
    ap.add_argument("--interim", type=Path, default=Path("data/interim"))
    ap.add_argument("--out", type=Path, default=Path("outputs/05_data_quality"))
    args = ap.parse_args(argv)
    con = duckdb.connect(str(args.db))
    result = run_checks(con, args.interim)
    write_report(con, result, args.out)
    con.close()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
