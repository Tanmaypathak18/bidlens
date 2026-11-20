# 08 Target, split and metrics

How BidLens will be tested, and how well two simple yardsticks do on that test (step 2.1).

## The question

Before building pricing models, we fix the rules of the test so every later model is
judged the same way, and we score two yardsticks that any model has to beat.

## The test (decision D-034)

- **What is predicted:** the low bidder's unit price for each bid item (models work on its
  logarithm, because prices span several orders of magnitude).
- **Time split:** models learn from bids opened before 01 January 2024 and are tested on
  bids opened from then to 03 November 2026. Never a random split: an estimator only ever
  knows the past.
- **Left out of the test:** contracts where the cost database and the bid summary disagree
  on who was low (stage 05), and any price of $0 or less. Unusual prices flagged in stage
  05 stay in; results are shown with and without them.
- **Scores:** the median percentage miss (MdAPE: half of the predictions miss by less than
  this) and the share of predictions within 15% of the low bid. Item families with fewer
  than 20 test prices are grouped as "Other".
- **Price levels:** every earlier price is brought to the bid date of the price being
  predicted with Caltrans' cost index, as known before that bid opened (stage 09).

| Set | Prices | Contracts |
| --- | ---: | ---: |
| Low-bid prices, train (before cutoff) | 10,296 | 599 |
| Low-bid prices, test period | 4,563 | 242 |
| Test prices after exclusions | 4,507 | 238 |
| of which flagged price outliers | 58 | 45 |
| Test contracts with an engineer's estimate and item lines |  | 201 |
| Headline contracts (90%+ lines with item-level history) |  | 178 |

## Headline: whole-contract totals (decisions D-037, D-038)

The estimator's real question: would BidLens's total have been closer to the winning bid
than Caltrans' own engineer's estimate? Until the pricing model exists, BidLens's total here
is a **historical-median total**: every line of the low bidder's item list, priced at the
median of earlier low bids for the same item, times the bid quantity. Nothing from the
contract being priced is used except its item list and quantities.

The headline uses the 178 test contracts where at least 90% of lines have
price history for that exact item (all 201 contracts are shown below too).
Contracts need a bid summary with its item lines: three test-period summaries were read
by OCR with their header only (decision D-026), so they have no lines to price.

**The historical-median total landed closer to the low bid than the engineer's estimate on
31.5% of headline contracts.**

| Measure | Historical-median total | Engineer's estimate |
| --- | ---: | ---: |
| Median distance from the low bid | 43.0% | 21.2% |
| Median over (+) or under (-) the low bid | 38.2% | 19.9% |
| Within 15% of the low bid | 20.2% | 35.4% |

All 201 test contracts with an engineer's estimate: closer on
31.3%.

| Measure | Historical-median total | Engineer's estimate |
| --- | ---: | ---: |
| Median distance from the low bid | 42.5% | 20.4% |
| Median over (+) or under (-) the low bid | 35.1% | 17.2% |
| Within 15% of the low bid | 21.4% | 38.3% |

How the lines of the headline contracts were priced:

| Tier | How the line is priced | Share of lines | Share of BidLens dollars |
| ---: | --- | ---: | ---: |
| 1 | Top-100 item: trailing 12-month median | 27.6% | 64.5% |
| 2 | Other standard item: median of earlier bids | 63.7% | 22.7% |
| 3 | Special item: median of earlier bids with the same description | 4.4% | 10.7% |
| 4 | Fallback: median for the same item family or unit | 4.3% | 2.0% |
| 5 | Unpriced: no earlier bid with the same unit | 0.0% | 0.0% |

## Item level: trailing 12-month median

For each test price, the yardstick is the median low-bid unit price for the same item and
unit over the 12 months before the bid (all earlier bids when the 12 months hold fewer than
3). Coverage is the share of test prices that had any earlier bid.

The misses are large because a plain median ignores the size of the job. A third of test
prices are lump sums (mobilization, traffic control, job site management) whose price
grows with the contract, and unit prices for quantities like asphalt tonnage drop sharply
as quantities grow. This is the gap the pricing models in steps 2.3 to 2.5 have to close.

All test prices:

| Group | Prices | Coverage | MdAPE | Within 15% |
| --- | ---: | ---: | ---: | ---: |
| Traffic Control | 955 | 100.0% | 60.0% | 13.2% |
| Asphalt Surfacing | 585 | 100.0% | 55.4% | 15.2% |
| Water Pollution and Site Management | 506 | 100.0% | 69.3% | 13.4% |
| General and Overhead | 427 | 100.0% | 65.8% | 10.1% |
| Striping and Markings | 422 | 100.0% | 54.2% | 16.1% |
| Earthwork and Clearing | 341 | 100.0% | 60.7% | 11.4% |
| Fencing, Guardrail and Barriers | 221 | 100.0% | 37.3% | 19.5% |
| Structural Concrete and Reinforcement | 219 | 100.0% | 37.0% | 21.5% |
| Landscape and Erosion Control | 208 | 100.0% | 34.1% | 23.6% |
| Electrical and Signals | 177 | 100.0% | 86.3% | 7.9% |
| Bridge Rehabilitation and Removal | 121 | 100.0% | 27.8% | 31.4% |
| Base and Subbase | 106 | 100.0% | 48.1% | 17.0% |
| Minor Concrete and Miscellaneous | 70 | 100.0% | 42.3% | 24.3% |
| Drainage | 55 | 100.0% | 36.3% | 27.3% |
| Concrete Pavement | 45 | 100.0% | 38.6% | 20.0% |
| Piling | 22 | 100.0% | 46.1% | 4.5% |
| Steel Structures, Signs and Painting | 21 | 100.0% | 79.4% | 14.3% |
| Other | 6 | 100.0% | 54.3% | 16.7% |
| All | 4,507 | 100.0% | 55.0% | 15.3% |

Without flagged outliers:

| Group | Prices | Coverage | MdAPE | Within 15% |
| --- | ---: | ---: | ---: | ---: |
| Traffic Control | 944 | 100.0% | 59.3% | 13.3% |
| Asphalt Surfacing | 577 | 100.0% | 55.2% | 15.4% |
| Water Pollution and Site Management | 503 | 100.0% | 68.5% | 13.5% |
| General and Overhead | 425 | 100.0% | 64.6% | 10.1% |
| Striping and Markings | 414 | 100.0% | 53.4% | 16.4% |
| Earthwork and Clearing | 335 | 100.0% | 59.6% | 11.6% |
| Fencing, Guardrail and Barriers | 219 | 100.0% | 37.2% | 19.6% |
| Structural Concrete and Reinforcement | 212 | 100.0% | 35.3% | 22.2% |
| Landscape and Erosion Control | 207 | 100.0% | 34.0% | 23.7% |
| Electrical and Signals | 177 | 100.0% | 86.3% | 7.9% |
| Bridge Rehabilitation and Removal | 118 | 100.0% | 27.3% | 32.2% |
| Base and Subbase | 106 | 100.0% | 48.1% | 17.0% |
| Minor Concrete and Miscellaneous | 69 | 100.0% | 41.4% | 24.6% |
| Drainage | 55 | 100.0% | 36.3% | 27.3% |
| Concrete Pavement | 42 | 100.0% | 33.2% | 21.4% |
| Piling | 22 | 100.0% | 46.1% | 4.5% |
| Steel Structures, Signs and Painting | 18 | 100.0% | 85.9% | 16.7% |
| Other | 6 | 100.0% | 54.3% | 16.7% |
| All | 4,449 | 100.0% | 54.0% | 15.5% |

By bid year (all test prices):

| Group | Prices | Coverage | MdAPE | Within 15% |
| --- | ---: | ---: | ---: | ---: |
| 2024 | 1,758 | 100.0% | 55.5% | 13.5% |
| 2025 | 1,748 | 100.0% | 53.3% | 17.3% |
| 2026 | 1,001 | 100.0% | 56.5% | 14.8% |
| All | 4,507 | 100.0% | 55.0% | 15.3% |

## Files

- `split_summary.csv`: the counts in the split table above.
- `item_benchmark_scores.csv`: item-level scores by family and by year, with and without outliers.
- `item_benchmark_predictions.csv`: every test price with its trailing-median prediction and
  how many earlier prices it used.
- `contract_totals.csv`: every test contract: low bid, engineer's estimate, historical-median
  total, errors, and the share of BidLens dollars from each pricing tier.
- `contract_line_prices.csv`: every priced line of those contracts, with its tier.
- `pricing_tiers.csv`: the share of lines and dollars from each pricing tier.
- `results.json`: the headline numbers.

No file names a bidder. Contracts are identified by their Caltrans contract number.

## How it was produced

`uv run python -m bidlens.pricing.compare` (code in `src/bidlens/pricing/`), from
`data/bidlens.duckdb` and the bid summary item lines. Generated 2026-11-20.
