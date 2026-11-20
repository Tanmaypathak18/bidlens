"""Tests for the bid summary PDF reader (step 1.5).

The pages below are synthetic text in the real layout. Bidder names, addresses and IDs
are invented, because real bid summaries must never be committed.
"""

from __future__ import annotations

from datetime import date

import pytest

from bidlens.ingest.bid_summary import BidSummaryError, parse_text

PAGE1_PLAIN = """State of California Department of Transportation
Bid Summary
Bid Opening Date:02/12/2025 Page 1
Contract Number: 04-0X0000 02/12/2025
Project ID: 0400000001 IN CONTRA COSTA COUNTY AT VARIOUS LOCATIONS Contract Code: E
Location: 04-CC-80-7.6, Number of Items: 3
Bridge deck rehabilitation.
Federal Aid #1: NONE
Proposals Issued: 23 Total Number of Working Days: 160 Overrun/Underrun: -$3,000.00
Number of Bidders: 3 Engineers Est: $10,000.00 % Over/Under Est: -30.00%
Bid Rank Bid Amount Bidder Id Bidder Information (Name / Address / License Number / Phone / Fax) Preference
1 $7,000.00 VC0000000001 EXAMPLE BUILDERS ONE CSLB# 00000001
1 MAIN ST Phone (000) 000-0000
2 $8,500.00 VC0000000002 EXAMPLE BUILDERS TWO CSLB# 00000002
2 MAIN ST
3 $12,000.00 VC0000000003 EXAMPLE BUILDERS THREE CSLB# 00000003
"""

PAGE2_ITEMS = """Bid Opening Date:02/12/2025 Page 2
Contract Number: 04-0X0000 02/12/2025
Contract Proposal of Low Bidder
EXAMPLE BUILDERS ONE
Item Item Unit of Estimated
Item Description Bid Amount
No. Code Measure Quantity
0001 090100 TIME-RELATED OVERHEAD (WDAY) WDAY 100.0 10.00 1,000.00
0002 F 510053 STRUCTURAL CONCRETE, BRIDGE CY 2.0 1,500.00 3,000.00
0003 999990 MOBILIZATION LS LUMP SUM 3,000.00 3,000.00
"""

PAGE3_OTHER = """Bid Opening Date:02/12/2025 Page 3
Contract Number: 04-0X0000 02/12/2025
Summary of Remaining Bidders
Second Third
Item Bid Amount Bid Amount
0001 12.00 1,200.00 20.00 2,000.00
"""

PAGE1_A_PLUS_B = """State of California Department of Transportation
Bid Summary
Bid Opening Date:01/07/2025 Page 1
Contract Number: 04-0Y0000 01/08/2025
Project ID: 0400000002 SONOMA COUNTY Contract Code: E
Location: 04-Son-101-22.8/32.8 Number of Items: 1
Replace bridge railing.
NO GOAL Federal Aid #1: NONE
Proposals Issued: 11 Total Number of Working Days: 200 Overrun/Underrun: -$100.00
Number of Bidders: 3 Engineers Est: $1,000.00 % Over/Under Est: -10.00%
Bid Rank Bid Amount Bidder Id Bidder Information (Name / Address / License Number / Phone / Fax) Preference
1 Cost: $900.00 VC0000000004 EXAMPLE CIVIL ONE CSLB# 00000004 CC PREF CLAIMED
Time: 10 Days x $50.00 4 MAIN ST
Total: $1,400.00 SOMEWHERE CA 00000
2 Cost: $800.00 VC0000000005 EXAMPLE CIVIL TWO CSLB# 00000005
Time: 20 Days x $50.00 5 MAIN ST
Total: $1,800.00 SOMEWHERE CA 00000
Cost: $700.00 VC0000000006 EXAMPLE CIVIL THREE CSLB# 00000006
Time: 30 Days x $50.00 6 MAIN ST
Total: $2,200.00 SOMEWHERE CA 00000
"""

PAGE2_A_PLUS_B = """Bid Opening Date:01/07/2025 Page 2
Contract Number: 04-0Y0000 01/08/2025
Contract Proposal of Low Bidder
EXAMPLE CIVIL ONE
0001 390132 HOT MIX ASPHALT (TYPE A) TON 6.0 150.00 900.00
"""


def test_plain_bid_summary() -> None:
    s = parse_text([PAGE1_PLAIN, PAGE2_ITEMS, PAGE3_OTHER], "04-0X0000.pdf")
    assert s.contract_number == "04-0X0000"
    assert s.bid_open_date == date(2025, 2, 12)
    assert s.district == "04" and s.county == "CC"
    assert s.location == "04-CC-80-7.6"
    assert s.working_days == 160
    assert s.engineers_estimate == 10_000.00
    assert s.n_bidders_reported == 3
    assert [b.rank for b in s.bids] == [1, 2, 3]
    assert s.low_bid.cost == 7_000.00
    assert not s.is_a_plus_b
    assert s.type_of_work == "Bridge deck rehabilitation."
    assert len(s.low_items) == 3
    lump = s.low_items[2]
    assert lump.item_code == "999990" and lump.quantity is None and lump.amount == 3_000.00
    assert s.low_items[1].flag == "F"
    assert s.checks() == []
    rec = s.contract_record()
    assert rec["second_bid_total"] == 8_500.00
    assert "EXAMPLE" not in str(rec)  # no bidder identities stored


def test_a_plus_b_and_unranked_bid() -> None:
    s = parse_text([PAGE1_A_PLUS_B, PAGE2_A_PLUS_B])
    assert s.is_a_plus_b
    assert len(s.bids) == 3
    assert [b.rank for b in s.ranked_bids] == [1, 2]
    assert s.bids[2].rank is None  # listed without a rank
    low = s.low_bid
    assert (low.cost, low.time_days, low.time_rate, low.total) == (900.0, 10, 50.0, 1400.0)
    assert s.contract_record()["low_bid_total"] == 1400.0
    assert s.contract_record()["n_bidders_ranked"] == 2
    assert s.checks() == []


def test_checks_flag_inconsistencies() -> None:
    broken_items = PAGE2_ITEMS.replace("3,000.00 3,000.00\n", "3,000.00 3,500.00\n", 1)
    s = parse_text([PAGE1_PLAIN, broken_items])
    assert any("item total" in p for p in s.checks())


def test_unparsed_item_line_reported() -> None:
    odd = PAGE2_ITEMS + "0004 123456 DESCRIPTION WITH NO NUMBERS\n"
    s = parse_text([PAGE1_PLAIN, odd])
    assert s.unparsed_item_lines == ["0004 123456 DESCRIPTION WITH NO NUMBERS"]


def test_rejects_non_bid_summary() -> None:
    with pytest.raises(BidSummaryError):
        parse_text(["Some other document"])
    with pytest.raises(BidSummaryError):
        parse_text(["Bid Summary\nContract Number: 04-0X0000\n"])  # header fields missing
