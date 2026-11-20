"""Database load tests (step 1.3), built from the saved sv08data fixtures."""

from __future__ import annotations

from pathlib import Path

import duckdb

from bidlens.db.load import build
from bidlens.ingest.caltrans import _BID_SCHEMA, _DETAIL_SCHEMA, write_parquet
from bidlens.ingest.parse_sv08 import parse_details, parse_results

FIX = Path(__file__).parent / "fixtures" / "caltrans"


def test_build_reconciles(tmp_path: Path) -> None:
    rows = parse_results((FIX / "results_item_district_year.html").read_text(errors="replace"))
    write_parquet([r.as_dict() for r in rows], _BID_SCHEMA, tmp_path / "sv08_bids.parquet")
    detail = parse_details((FIX / "contract_item_details.html").read_text(errors="replace"))
    write_parquet([detail.as_dict()], _DETAIL_SCHEMA, tmp_path / "sv08_contracts.parquet")

    db = tmp_path / "test.duckdb"
    result = build(tmp_path, db)

    rec = result["reconciliation"]
    assert rec["bids_reconcile"] and rec["bid_rows_loaded"] == len(rows) == 68
    assert rec["listed_contracts_loaded"] == 1
    con = duckdb.connect(str(db), read_only=True)
    n_contracts = con.execute("SELECT count(*) FROM contract").fetchone()[0]
    assert n_contracts == len({r.contract_number for r in rows}) + 1  # + the listed detail
    # every bid joins to an item and a contract
    orphans = con.execute("""
        SELECT count(*) FROM bid b
        LEFT JOIN bid_item i USING (bid_item_id)
        LEFT JOIN contract c USING (contract_id)
        WHERE c.contract_id IS NULL
    """).fetchone()[0]
    assert orphans == 0
    # bidder count from ranks
    top = con.execute(
        "SELECT n_bidders_sv08 FROM contract WHERE contract_id = '05-1R2904_2025-02-19'"
    ).fetchone()[0]
    assert top == max(r.bid_rank for r in rows if r.contract_number == "05-1R2904")
    con.close()
