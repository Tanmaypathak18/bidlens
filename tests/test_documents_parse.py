"""Step 3.2 tests: bid package parsing, on synthetic page text."""

from __future__ import annotations

import pandas as pd

from bidlens.documents.parse import chunk, label_lines, page_lines, parse_item_rows


def test_page_lines_drops_footer_and_reads_printed_page():
    lines, printed = page_lines("Some text\nmore\nContract No. 04-0W0504\n12")
    assert lines == ["Some text", "more"] and printed == "12"


def test_item_rows_with_continuations_lump_sums_and_deletions():
    rows = parse_item_rows(
        [
            "Item Item Code Item Description Unit of Measure Estimated Quantity",
            "0003 090205 DISPUTE RESOLUTION BOARD ON-SITE EA 12",
            "MEETING",
            "0005 120090 CONSTRUCTION AREA SIGNS LS LUMP SUM",
            "0029 192001 (F) - STRUCTURE EXCAVATION CY 2,531",
            "0026 000001 ITEM DELETED PER ADDENDUM",
            "0120 999990 MOBILIZATION LS LUMP SUM LUMP SUM",
            "REPLACED PER ADDENDUM NO. 2 DATED SEPTEMBER 2, 2026",
        ]
    )
    by = {r["item_no"]: r for r in rows}
    assert by["0003"]["description"] == "DISPUTE RESOLUTION BOARD ON-SITE MEETING"
    assert (by["0003"]["unit"], by["0003"]["quantity"]) == ("EA", 12.0)
    assert by["0005"]["quantity"] is None and by["0005"]["unit"] == "LS"
    assert by["0029"]["final_pay"] and by["0029"]["quantity"] == 2531.0
    assert by["0029"]["description"] == "STRUCTURE EXCAVATION"
    assert by["0026"]["deleted"]
    assert by["0120"]["description"] == "MOBILIZATION"


def _pages():
    sp = [
        "STATE OF CALIFORNIA\nNOTICE TO BIDDERS AND\nSPECIAL PROVISIONS\nContract No. 04-0X0000\n1",
        "NOTICE TO BIDDERS\nBids open soon.\nContract No. 04-0X0000\n2",
        "SPECIAL PROVISIONS\n^^^^^^^^^^^^^^^^^^^^\nDIVISION I GENERAL PROVISIONS\n"
        "5 CONTROL OF WORK\n"
        "Add to section 5-1.20:\nWork windows apply.\n^^^^^^^^^^^^^^^^^^^^\n"
        "12 TEMPORARY TRAFFIC CONTROL\nReplace section 12-3.01 with:\nClose lanes at night.\n3",
    ]
    return pd.DataFrame(
        {
            "file": "sp.pdf",
            "kind": "special_provisions",
            "title": "Special Provisions",
            "page": [1, 2, 3],
            "text": sp,
        }
    )


def test_sections_follow_headings_not_the_cover_title():
    lines = label_lines(_pages())
    sec = {ln.text: ln.section for ln in lines}
    by_page = {(ln.page, ln.text): ln.section for ln in lines}
    assert sec["STATE OF CALIFORNIA"] == "Cover And Contents"
    assert by_page[(1, "SPECIAL PROVISIONS")] == "Cover And Contents"  # cover title line
    assert by_page[(3, "SPECIAL PROVISIONS")] == "Special Provisions"  # real heading
    assert sec["Bids open soon."] == "Notice To Bidders"
    assert sec["Work windows apply."] == "5 Control Of Work"
    assert sec["Close lanes at night."] == "12 Temporary Traffic Control"
    sub = {ln.text: ln.subsection for ln in lines}
    assert sub["Close lanes at night."] == "12-3.01"


def test_chunks_stay_within_one_page_and_section():
    c = chunk(label_lines(_pages()), max_chars=60)
    assert c.groupby("chunk_id")[["page", "section"]].nunique().max().max() == 1
    assert c["chunk_id"].is_unique
    assert set(c.loc[c["page"] == 3, "section"]) >= {
        "5 Control Of Work",
        "12 Temporary Traffic Control",
    }
