"""Data quality check tests (step 1.6)."""

from __future__ import annotations

import math
from pathlib import Path

import duckdb

from bidlens.db.checks import run_checks, write_report
from bidlens.db.load import SCHEMA


def _db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(SCHEMA)
    con.execute("""
        INSERT INTO contract (contract_id, contract_number, bid_open_date, district,
                              in_contract_list, n_bidders_sv08, n_bidders, has_bid_summary)
        VALUES ('04-0X0000_2025-01-01', '04-0X0000', DATE '2025-01-01', '04', TRUE, 3, 4, TRUE)
    """)
    rows = []
    for k in range(30):  # 30 normal prices around 100 on the same item and unit
        item = f"c_390132_{k + 1}"
        rows.append((item, 100.0 * math.exp(0.05 * ((k % 7) - 3))))
        con.execute(
            "INSERT INTO bid_item VALUES (?, '04-0X0000_2025-01-01', '390132', 'HMA', 'TON', 10)",
            [item],
        )
    con.execute(
        "INSERT INTO bid_item VALUES ('c_390132_99', '04-0X0000_2025-01-01', '390132', 'HMA',"
        " 'TON', 10)"
    )
    rows.append(("c_390132_99", 5000.0))  # an outlier
    for i, (item, price) in enumerate(rows, start=1):
        con.execute(
            "INSERT INTO bid VALUES (?, 1, ?, ?, ?)", [item, price, round(price * 10, 2), i]
        )
    con.execute("UPDATE bid SET total = 1 WHERE bid_item_id = 'c_390132_5'")  # total mismatch
    return con


def test_checks_flag_outlier_mismatch_and_contracts(tmp_path: Path) -> None:
    con = _db()
    result = run_checks(con, tmp_path)  # no bid summary items in tmp_path
    assert result["bid_flags"]["price_outlier"] == 1
    assert result["bid_flags"]["total_mismatch"] == 1
    assert result["bid_flags"]["non_positive_price"] == 0
    assert result["contract_flags"]["bidder_count_mismatch"] == 1
    assert result["contract_flags"]["missing_engineers_estimate"] == 1
    outlier = con.execute(
        "SELECT bid_item_id FROM bid_flag WHERE flag = 'price_outlier'"
    ).fetchone()
    assert outlier[0] == "c_390132_99"

    write_report(con, result, tmp_path / "out")
    report = (tmp_path / "out" / "data_quality.md").read_text()
    assert "price_outlier" in report and "bidder_count_mismatch" in report
    assert (tmp_path / "out" / "bid_flags.csv").read_text().count("\n") == 3  # header + 2


def test_small_groups_are_not_scored(tmp_path: Path) -> None:
    con = _db()
    con.execute("DELETE FROM bid WHERE source_row_id > 5 AND bid_item_id <> 'c_390132_99'")
    result = run_checks(con, tmp_path)
    assert result["bid_flags"]["price_outlier"] == 0  # fewer than 20 bids
