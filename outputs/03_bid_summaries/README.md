# 03 Bid summaries

The bid summary PDFs: what was downloaded, what was read, and any problems.

| File | Rows | What it is |
| --- | --- | --- |
| `pdf_manifest.csv` | 673 | Every downloaded PDF: contract and bid date read from it, SHA-256 hash, layout, whether it was read from text or OCR, parse status, problems, and where to find the original |
| `parsed_contracts.csv` | 672 | Contract fields from each usable PDF: engineer's estimate, working days, bidder counts, low and second bid, A+B flag and checks. `type_of_work` is blank for older-layout files, whose description wraps into the location text. The database takes type of work from the cost database instead |
| `parsed_item_prices.csv` | 44,334 | The low bidder's price for every item, from PDFs whose item lines fully reconcile |
| `parse_issues.csv` | 8 | Every PDF with a problem, and what the problem is |
| `coverage.md` | | Which contracts have a usable summary, and why the others do not |

**Parse status:** {'usable': 668, 'usable, contract fields only': 4, 'not usable': 1}. Read by: {'text': 631, 'OCR': 41, '': 1}.

**How it was produced:**
1. The maintainer downloaded the PDFs by hand from the Caltrans bid summary site (decision D-014). Its robots.txt bars scripts.
2. `uv run python -m bidlens.ingest.check_bid_summaries` read each file (decisions D-021, D-025 and D-026). It handles two report layouts. Files that Caltrans serves with broken fonts are read with OCR.

**Checks:**
- **Exact sum:** the low bidder's items must add up exactly to the low bid.
- **Header check:** the engineer's estimate × (1 + printed % over/under) must reproduce the low bid.

**The PDFs are not in this repository.** They list bidder names and contact details. To open one:
1. Go to the `caltrans_source_page` (the Caltrans bid summary search).
2. Search it for the contract number and bid date in `search_the_source_page_for`. The site has no stable link per record.
3. `same_contract_in_cost_database` links straight to the same contract's prices on the public cost database.
4. The `sha256` column confirms a downloaded copy is the same file.

**No bidder names, addresses or phone numbers are stored.** Bids are identified by rank.
