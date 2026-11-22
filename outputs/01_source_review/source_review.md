# Caltrans source review (step 1.1)

Reviewed 2026-11-19. This review covers where BidLens gets its Caltrans bid history and what each source does and does not contain.

## Summary

| Need | Source | Status |
| --- | --- | --- |
| Item-level bids: item, unit, quantity, unit price, bid rank, date, district, contract | Contract Cost Data (`sv08data.dot.ca.gov`) | Available. Collected with plain page requests, one at a time, 2 seconds apart |
| County, route and type of work per contract | Contract Cost Data, `details.php` | Available |
| Bidder count | Derived: the highest bid rank seen for a contract | Available, with a caveat (see below) |
| Item code list and descriptions | Contract Cost Data, `codes.php` | Available |
| Engineer's estimate, contract total | Bid Summary PDFs, downloaded by hand | Available |
| Engineer's estimate, item level | Not found in any public source | **Not available.** Affects the step 2.1 benchmark |
| Working days | Bid Summary PDFs | Available |
| Every bid total, low bid and bidder count | Bid Summary PDFs (cross-checked against sv08data bid ranks) | Available |
| Contract list for the slice | sv08data, four near-universal items | 827 bid openings, 815 contract numbers |

## Source 1: Contract Cost Data (sv08data.dot.ca.gov)

- **What it is:** Caltrans' public search of historic bid prices. At review time it held 3,476,161 records, with bid opening dates up to 11-03-2026. Caltrans says the data is imported about every two weeks from the HQ bid summary documents.
- **Base URL:** `https://sv08data.dot.ca.gov/`. The `/contractcost/` path redirects here.
- **Terms:** use of the site means accepting the Caltrans [Conditions of Use](https://dot.ca.gov/conditions-of-use), dated July 19, 2021. They say site information is generally in the public domain and "may be distributed or copied as permitted by law". They don't mention automated access. The site has no `robots.txt` (it returns 404).
- **Technology:** server-rendered PHP. Forms use GET, so every query is a plain URL. No login, cookies or JavaScript are needed to get data.

### Endpoints

#### `index.php`: search form
Fixture: `tests/fixtures/caltrans/search_form.html`

The form fields map to these `results.php` parameters:

| Parameter | Values | Notes |
| --- | --- | --- |
| `item` | an item code (e.g. `390132`) or description text; `%` and `_` are wildcards | Required. Code searches are faster than description or wildcard searches |
| `ob` | `0` all bidders, `1` awarded only, `2` to `5` top N | Irregular bidders are always excluded. With `ob=1`, the bid rank column is replaced by the bid-open quarter |
| `DISTRICT[]` | `01` to `12`, repeatable; or county codes (`ALA`, `SON`, ...) | Empty means all |
| `Year[]` | `y1993` to `y2026`, repeatable | **Needs the `y` prefix.** Data runs from 1993 |
| `min`, `max` | item total price bounds ($) | Optional |
| `minU`, `maxU` | quantity bounds | Optional |
| `unit` | `none` or a unit code (`TON`, `CY`, `LF`, `EA`, `LS`, ...) | Filters by unit |
| `convert` | `1` | Converts to the selected unit where Caltrans has a factor. BidLens leaves this off and normalizes units itself in step 1.4 |
| `start` | `Search` | Submit button; harmless to include |

#### `results.php`: item bid rows
Fixture: `tests/fixtures/caltrans/results_item_district_year.html` (item 390132, District 05, 2025, all bidders: 68 bid rows)

Example: `results.php?item=390132&ob=0&DISTRICT[]=05&Year[]=y2025&unit=none&start=Search`

- One HTML table with one row per bid per item. Columns:
  - item code and description
  - unit and district
  - quantity
  - unit price, adjusted price and total
  - bid open date (`mm-dd-yyyy`)
  - contract number (EA, e.g. `04-1Q7004`)
  - bid rank
  - links for Mobilization (M) and time-related overhead (TRO)
- Each row's checkbox `name` and its `details.php?Num=` link carry a numeric row ID (e.g. `5014594`). Use it as the source key for a bid row.
- **Bid rank** is the bidder's overall position on the contract (1 = low bidder). It is not the rank on this item, so rank 1 can have a higher item price than rank 2. No bidder names are shown, which fits the project's market-level rule.
- **Adjusted price** uses the Caltrans general Construction Cost Index: `I(current 12 months) / I(quarter advertised) × original price`. BidLens stores the original price and does its own escalation in step 2.2.
- Prices are formatted text (`$1742400.00`) and need parsing.
- A summary block at the bottom (average, standard deviation, weighted average) is filled by JavaScript and is ignored.
- One-time-use item codes (starting `01` to `04`) are flagged in the page and are out of scope.
- **Errors return HTTP 200.** A bad parameter returns an error page titled "ERROR" with an alert message, for example "Invalid year(s) specified!". Fixture: `tests/fixtures/caltrans/results_error_invalid_year.html`. The scraper must check the page content, not just the status code.

#### `details.php?Num=<row id>`: contract and row details
Fixture: `tests/fixtures/caltrans/contract_item_details.html`

- Shows the EA, item code and description, bid opening date, District-County-Route-Postmile (e.g. `SON-101-22.8/32.8`), quantity, unit price, total price and **type of work** (the contract description).
- It is per bid row, but the county, route and type of work are per contract, so one call per contract is enough.

#### `codes.php`: item code search
Fixture: `tests/fixtures/caltrans/code_search.html` (`Item=hot mix asphalt`, `R1=StdItems`)

- Parameters: `Item` (description text) and `R1`, which is one of `All`, `StdItems` (standard contract items) or `StateFurnished`.
- Returns item codes with descriptions, but no units. The current official item list is a Word document on the Caltrans construction contract standards page. Step 1.4 decides which list ItemMaster uses.

#### Not used
- `graph.php`: price history charts, built from the same data.
- `map.php`: district map.
- `help.php`, `searchtips.php` and `resources.php`: documentation.

### Bidder count

The highest bid rank seen for a contract gives its number of regular bidders. In the 2025 District 4 sample for item 390132, the 38 contracts had between 1 and 12 bidders. The caveat: a contract only shows up through the items we query, and a bidder that left an item blank would be missed. Taking the highest rank across all queried items keeps this risk small. Step 1.5 cross-checks the count.

## Source 2: HQ bid summaries (ppmoe.dot.ca.gov)

- **What it is:** the Caltrans Office Engineer pages of bids opened and contracts awarded (`https://ppmoe.dot.ca.gov/cc?id=cc_bid_summary`). The Contract Cost Data is built from these documents. This is the only public place found that has the **engineer's estimate**, **working days**, and the full bid totals per contract.
- **Technology:** a ServiceNow portal, rendered by JavaScript.
- **Automated access is not allowed.** `https://ppmoe.dot.ca.gov/robots.txt` says `User-agent: *` / `Disallow: /`. One request was made to the landing page during this review, before the `robots.txt` was checked. BidLens makes no further automated requests to this host.
- **Open data:** a search of data.ca.gov found no dataset of Caltrans bid results, engineer's estimates or working days.

The maintainer downloads Bid Summary PDFs from this site by hand.

## Source 3: Bid Summary PDFs (manual download)

Pilot: 10 contracts from 2025 (5 in District 4, 5 in District 5), saved as `data/raw/bid_summaries/<contract>.pdf`. They aren't committed: they contain bidder names, addresses and phone numbers, and BidLens works at market level. The parser fixtures for step 1.5 will be redacted text extracts.

**Layout.** Each file is a text PDF (not a scan) produced by Caltrans' report tool. Pages are in this order:

1. **Header (page 1):** contract number, bid opening date, project ID, location (`04-Son-101-22.8/32.8`), number of items, type of work, federal aid number, proposals issued, **total number of working days**, **number of bidders**, **engineer's estimate**, % over/under the estimate, and overrun/underrun.
2. **Bid list:** one entry per bidder, with bid rank, bid amount, bidder ID, name and address, and the preference claimed (small business and so on).
   - **A+B contracts** (cost plus time) show `Cost`, `Time: N Days x $rate` and `Total` for each bidder. The ranking uses `Total`.
3. **Contract Proposal of Low Bidder:** every item, with item number, an optional `F` flag (final pay item), item code, description, unit, estimated quantity, unit price and amount.
4. **Summary of Remaining Bidders:** for every other bidder, each item's unit price and amount, four bidders per page block.
5. **List of Subcontractors:** not used.

**Fields found in all 10 pilot files:**

| Field | Found | Notes |
| --- | --- | --- |
| Engineer's estimate (contract total) | 10 of 10 | `Engineers Est: $…`. % over/under matches the low bid |
| Working days | 10 of 10 | `Total Number of Working Days` |
| Bid totals for every bidder | 10 of 10 | Bid list on pages 1 and 2 |
| Item-level prices, low bidder | 10 of 10 | Item rows match `Number of Items` once the `F` flag is allowed for |
| Item-level prices, other bidders | 10 of 10 | Summary of Remaining Bidders |
| Item-level engineer's estimate | 0 of 10 | Not in the bid summary |

**Quirks:**
- **Unranked bidders.** 04-1Q7004 lists 8 bidders but ranks only 7. The eighth has no rank and is most likely an irregular bid. sv08data, which excludes irregular bidders, also shows 7. Use the ranked count as the bidder count, and keep `Number of Bidders` as published.
- **A+B bids.** The low bid is chosen on `Total` (cost plus time), not `Cost`.
- **Header-only pages.** 05-1N3804 page 5 and 05-1R7504 page 4 have only the header. They are harmless.
- **One bidder.** 05-1R7504 had a single bid, 10% over the estimate. Bidder counts in the pilot range from 1 to 12.
- Single-bidder and two-bidder contracts have no separate bid-list page.

## Contract list

Searches on sv08data need at least 3 contiguous letters or digits, so no single search lists every contract. The site also returned HTTP 500 for the code pattern `390___`. The contract list is built from the union of awarded-only (`ob=1`) searches, one per district covering all years, for four items nearly every contract has:

- 999990 mobilization
- 120090 construction area signs
- 120100 traffic control system
- 130100 job site management

Mobilization alone missed 2 of the 10 pilot contracts. The union found all 10.

Result for the BidLens slice (Districts 4 and 5, 2018 to 2026):

| District | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 (to Nov 3) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 04 | 80 | 64 | 43 | 64 | 68 | 72 | 68 | 64 | 28 |
| 05 | 40 | 29 | 27 | 40 | 42 | 30 | 25 | 24 | 19 |

That's 827 bid openings under 815 contract numbers. Twelve openings re-use a contract number, meaning the contract was re-advertised.

With `ob=1`, the Bid column holds the awarded bidder's rank, not the bid-open quarter that the help page describes. Fixture: `tests/fixtures/caltrans/results_awarded_contract_list.html`.

## Collection plan for the BidLens slice

- **Queries:** about 100 items × 2 districts × 9 years = up to 1,800 `results.php` calls, plus one `details.php` call per contract (827). That is about 2,600 requests, roughly 1.5 hours at one request every 2 seconds.
- **Picking the top 100 items:** from bid summary dollar totals. The list is provisional until Tier 1 of the checklist is downloaded.
- **Cache:** raw HTML keyed by URL (format chosen in step 1.2).
