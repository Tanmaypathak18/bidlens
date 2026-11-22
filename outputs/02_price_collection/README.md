# 02 Price collection

Every request made to the Caltrans cost database and every bid price collected.

| File | Rows | What it is |
| --- | --- | --- |
| `request_log.csv` | 2,635 | One row per page requested from sv08data.dot.ca.gov: time, page, full URL, outcome, HTTP status, rows read from the page, and size |
| `bid_prices.csv` | 72,113 | Every bid price collected: contract, bid date, district, county, item, family, unit, quantity, unit price, total, bid rank (1 = low bidder) and a link to the price on the Caltrans site |

**Requests:** {'results.php': 1808, 'details.php': 827}. Outcomes: {'ok': 2635}. A dropped connection that recovered on retry is logged once, with its final outcome.

**How it was produced:** `uv run python -m bidlens.ingest.caltrans all` (step 1.2), with one request at a time, at least 2 seconds apart. First, 8 searches listed the contracts for Districts 4 and 5, 2018 to 2026, through four items nearly every contract has. Then 827 contract pages gave county and type of work, and 1,800 searches (100 items × 2 districts × 9 years) gave the prices. The scope is set in `config/scope.yaml`.

**Notes:**
- Prices are in the units Caltrans published. No conversion was needed (see `06_item_master`).
- Bid rank is the bidder's overall rank on the contract, not on the item.
- The cost database leaves out irregular bids. No bidder names are collected.
