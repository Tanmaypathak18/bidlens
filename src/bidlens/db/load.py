"""Build bidlens.duckdb from the interim Parquet files (steps 1.3 and 1.5).

Usage:
    uv run python -m bidlens.db.load            # writes data/bidlens.duckdb

Inputs (all in data/interim/):
    sv08_bids.parquet           item bids from sv08data (step 1.2)
    sv08_contracts.parquet      contract details for the D-015 contract list (step 1.2)
    bid_summaries.parquet       contract fields from bid summary PDFs (step 1.5, optional)
"""

from __future__ import annotations

import argparse
import json
from importlib.resources import files
from pathlib import Path

import duckdb

from bidlens.ingest.check_bid_summaries import _CONTRACT_SCHEMA

SCHEMA = files("bidlens.db").joinpath("schema.sql").read_text()


def build(interim: Path, db_path: Path) -> dict:
    """Create a fresh database and load it. Returns row counts and reconciliation."""
    bids = interim / "sv08_bids.parquet"
    contracts = interim / "sv08_contracts.parquet"
    summaries = interim / "bid_summaries.parquet"
    for required in (bids, contracts):
        if not required.exists():
            raise FileNotFoundError(f"{required} is missing; run the step 1.2 scraper first")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".building.duckdb")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    con.execute(SCHEMA)

    # Staging: number repeated item codes within an opening (D-023).
    con.execute(f"""
        CREATE TEMP TABLE stg_bid AS
        WITH b AS (
            SELECT *,
                   contract_number || '_' || strftime(bid_open_date, '%Y-%m-%d') AS contract_id,
                   CASE WHEN quantity = 0 AND unit = 'LS' THEN 1 ELSE quantity END AS qty,
                   row_number() OVER (
                       PARTITION BY contract_number, bid_open_date, item_code, unit, quantity,
                                    bid_rank
                       ORDER BY row_id) AS dup
            FROM read_parquet('{bids}')
        )
        SELECT *,
               dense_rank() OVER (
                   PARTITION BY contract_id, item_code ORDER BY qty, unit, dup) AS n
        FROM b
    """)
    has_summaries = summaries.exists()
    if has_summaries:
        summary_cte = f"SELECT * FROM read_parquet('{summaries}')"
    else:  # typed, empty: keeps the same columns
        cols = ", ".join(f"NULL::{t} AS {c}" for c, t in _CONTRACT_SCHEMA.items())
        summary_cte = f"SELECT {cols} WHERE false"
    con.execute(f"""
        CREATE TEMP TABLE stg_contract AS
        WITH listed AS (
            SELECT DISTINCT contract_number, bid_open_date, county, location, type_of_work
            FROM read_parquet('{contracts}')
        ),
        from_bids AS (
            SELECT contract_number, bid_open_date, max(bid_rank) AS n_bidders_sv08
            FROM stg_bid GROUP BY ALL
        ),
        summ AS ({summary_cte}),
        keys AS (
            SELECT contract_number, bid_open_date FROM listed
            UNION SELECT contract_number, bid_open_date FROM from_bids
            UNION SELECT contract_number, bid_open_date FROM summ
        )
        SELECT k.contract_number, k.bid_open_date,
               l.contract_number IS NOT NULL AS in_contract_list,
               coalesce(l.county, s.county) AS county,
               coalesce(l.location, s.location) AS location,
               coalesce(l.type_of_work, s.type_of_work) AS type_of_work,
               f.n_bidders_sv08,
               s.contract_number IS NOT NULL AS has_bid_summary,
               s.* EXCLUDE (contract_number, bid_open_date, county, location, type_of_work)
        FROM keys k
        LEFT JOIN listed l USING (contract_number, bid_open_date)
        LEFT JOIN from_bids f USING (contract_number, bid_open_date)
        LEFT JOIN summ s USING (contract_number, bid_open_date)
    """)
    summary_cols = """project_id, n_items, proposals_issued, working_days, n_bidders_reported,
           n_bidders_ranked, engineers_estimate, low_bid_cost, low_bid_total,
           second_bid_total, is_a_plus_b, source_file"""
    con.execute(f"""
        INSERT INTO contract
        SELECT contract_number || '_' || strftime(bid_open_date, '%Y-%m-%d'),
               contract_number, bid_open_date, substr(contract_number, 1, 2),
               county, location, type_of_work, in_contract_list, n_bidders_sv08,
               has_bid_summary, {summary_cols}
        FROM stg_contract
    """)
    con.execute("""
        INSERT INTO bid_item
        SELECT DISTINCT ON (contract_id, item_code, n)
               contract_id || '_' || item_code || '_' || n, contract_id, item_code,
               item_description, unit, qty
        FROM stg_bid ORDER BY contract_id, item_code, n, bid_rank
    """)
    con.execute("""
        INSERT INTO bid
        SELECT contract_id || '_' || item_code || '_' || n, bid_rank, unit_price, total, row_id
        FROM stg_bid
    """)

    counts = {
        t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        for t in ("contract", "bid_item", "bid", "item_master", "cost_index")
    }
    source_rows = con.execute(f"SELECT count(*) FROM read_parquet('{bids}')").fetchone()[0]
    listed = con.execute(
        f"SELECT count(DISTINCT (contract_number, bid_open_date)) FROM read_parquet('{contracts}')"
    ).fetchone()[0]
    recon = {
        "sv08_bid_rows": source_rows,
        "bid_rows_loaded": counts["bid"],
        "bids_reconcile": source_rows == counts["bid"],
        "listed_contracts": listed,
        "listed_contracts_loaded": con.execute(
            "SELECT count(*) FROM contract WHERE in_contract_list"
        ).fetchone()[0],
        "contracts_from_bids_only": con.execute(
            "SELECT count(*) FROM contract"
            " WHERE NOT in_contract_list AND n_bidders_sv08 IS NOT NULL"
        ).fetchone()[0],
        "contracts_with_bid_summary": con.execute(
            "SELECT count(*) FROM contract WHERE has_bid_summary"
        ).fetchone()[0],
    }
    con.close()
    tmp.replace(db_path)
    return {"counts": counts, "reconciliation": recon}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interim", type=Path, default=Path("data/interim"))
    ap.add_argument("--db", type=Path, default=Path("data/bidlens.duckdb"))
    args = ap.parse_args(argv)
    result = build(args.interim, args.db)
    print(json.dumps(result, indent=2))
    (args.interim / "load_log.json").write_text(json.dumps(result, indent=2))
    return 0 if result["reconciliation"]["bids_reconcile"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
