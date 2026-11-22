"""Item master tests (step 1.4) with a small synthetic item list."""

from __future__ import annotations

from pathlib import Path

import duckdb
import openpyxl
import pytest

from bidlens.db.item_master import SECTION_FAMILY, build_item_master, read_item_list
from bidlens.db.load import SCHEMA


def make_list(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([None, None, None, None, "Revised 10-19-26"])
    ws.append(["Note:", "F = final pay", None, None, None])
    ws.append([None, None, None, None, None])
    ws.append(["Item Code", "Final Pay Item (F)", "Item Description", "Unit Pay", "2026\nSection"])
    ws.append(["390132", None, "HOT MIX ASPHALT (TYPE A)", "TON", 39])
    ws.append(["510053", "F", "STRUCTURAL CONCRETE, BRIDGE", "CY", 51])
    ws.append(["999990", None, "MOBILIZATION", "LS", 9])
    wb.save(path)
    return path


def test_read_item_list(tmp_path: Path) -> None:
    items = read_item_list(make_list(tmp_path / "list.xlsx"))
    assert [i.item_code for i in items] == ["390132", "510053", "999990"]
    assert items[1].final_pay and not items[0].final_pay
    assert items[0].spec_section == 39


def test_read_item_list_rejects_other_files(tmp_path: Path) -> None:
    wb = openpyxl.Workbook()
    wb.active.append(["something else"])
    wb.save(tmp_path / "x.xlsx")
    with pytest.raises(ValueError):
        read_item_list(tmp_path / "x.xlsx")


def test_every_section_in_2026_range_has_a_family() -> None:
    assert SECTION_FAMILY[39] == "Asphalt Surfacing"
    assert SECTION_FAMILY[9] == SECTION_FAMILY[99] == "General and Overhead"
    assert SECTION_FAMILY[87] == "Electrical and Signals"


def test_build_item_master_maps_converts_and_flags(tmp_path: Path) -> None:
    con = duckdb.connect()
    con.execute(SCHEMA)
    con.execute("""
        INSERT INTO contract (contract_id, contract_number, bid_open_date, district,
                              in_contract_list)
        VALUES ('04-0X0000_2025-01-01', '04-0X0000', DATE '2025-01-01', '04', TRUE)
    """)
    con.execute("""
        INSERT INTO bid_item VALUES
          ('c_390132_1', '04-0X0000_2025-01-01', '390132', 'HMA', 'TONN', 100),
          ('c_872130_1', '04-0X0000_2025-01-01', '872130', 'MODIFYING ELECTRICAL', 'LS', 1),
          ('c_510053_1', '04-0X0000_2025-01-01', '510053', 'CONCRETE', 'EA', 3)
    """)
    for i, item in enumerate(("c_390132_1", "c_872130_1", "c_510053_1"), start=1):
        con.execute("INSERT INTO bid VALUES (?, 1, 110.231, 11023.10, ?)", [item, i])
    stats = build_item_master(con, make_list(tmp_path / "list.xlsx"))

    assert stats["retired_codes_in_data"] == ["872130"]
    assert stats["rows_current_code"] == 2
    retired = con.execute(
        "SELECT is_current, item_family, replaced_by FROM item_master WHERE item_code = '872130'"
    ).fetchone()
    assert retired[0] is False and retired[1] == "Electrical and Signals"
    assert "872133" in retired[2]
    hma = con.execute(
        "SELECT unit, quantity, unit_price, unit_mismatch FROM bid_normalized "
        "WHERE item_code = '390132'"
    ).fetchone()
    assert hma[0] == "TON"  # metric tonne converted
    assert float(hma[1]) == pytest.approx(110.231)
    assert float(hma[2]) == pytest.approx(100.0, rel=1e-4)
    assert hma[3] is False
    concrete = con.execute(
        "SELECT unit_mismatch FROM bid_normalized WHERE item_code = '510053'"
    ).fetchone()
    assert concrete[0] is True  # EA vs CY pay unit, no factor: flagged, not converted
