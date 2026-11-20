# Caltrans source review (step 1.1)

Reviewed 2026-11-19. This review covers where BidLens gets its Caltrans bid history and what each source does and does not contain.

## Summary

| Need | Source | Status |
| --- | --- | --- |
| Item-level bids: item, unit, quantity, unit price, bid rank, date, district, contract | Contract Cost Data (`sv08data.dot.ca.gov`) | Available. Collection follows D-012 and D-013 |
| County, route and type of work per contract | Contract Cost Data, `details.php` | Available |
| Bidder count | Derived: the highest bid rank seen for a contract | Available, with a caveat (see below) |
| Item code list and descriptions | Contract Cost Data, `codes.php` | Available |
| Engineer's estimate (contract and item level) | HQ bid summaries (`ppmoe.dot.ca.gov`) only | **Not available for automated collection** |
| Working days | HQ bid summaries only | **Not available for automated collection** |
| Low bid total | HQ bid summaries; or summed from all items of bid rank 1 | Open: summing needs every item of a contract, not only in-scope items |

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
- It is per bid row, but the county, route and type of work are per contract, so one call per contract is enough (D-012).

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
- **Automated access is not allowed.** `https://ppmoe.dot.ca.gov/robots.txt` says `User-agent: *` / `Disallow: /`. One request was made to the landing page during this review, before the `robots.txt` was checked. BidLens makes no further automated requests to this host (D-013).
- **Open data:** a search of data.ca.gov found no dataset of Caltrans bid results, engineer's estimates or working days.

**The source for the engineer's estimate and working days is an open question for the maintainer.** These fields feed:
- step 1.5 (contract data)
- the engineer's-estimate benchmark in step 2.1
- the spread model in step 2.7

## Collection plan for the D-007 slice

- **Queries:** about 100 items × 2 districts × 9 years = up to 1,800 `results.php` calls, plus one `details.php` call per contract (estimated at under 1,700). That is about 3,500 requests, roughly 2 hours at D-013's rate.
- **Picking the top 100 items:** this needs item totals first. Step 1.2 decides how, either a one-off wildcard query per district and year (heavy) or a candidate list from the code search.
- **Cache:** raw HTML keyed by URL (format chosen in step 1.2).
