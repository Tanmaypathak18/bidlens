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
  predicted with Caltrans' cost index (4-quarter average, stage 09). In the test years the
  index kept rising while prices for these items levelled off (see stage 09's check), so
  escalated historical prices run high; the pricing models also see the bid date and can
  correct for this.

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
32.0% of headline contracts.**

| Measure | Historical-median total | Engineer's estimate |
| --- | ---: | ---: |
| Median distance from the low bid | 41.9% | 21.2% |
| Median over (+) or under (-) the low bid | 37.4% | 19.9% |
| Within 15% of the low bid | 18.5% | 35.4% |

All 201 test contracts with an engineer's estimate: closer on
31.8%.

| Measure | Historical-median total | Engineer's estimate |
| --- | ---: | ---: |
| Median distance from the low bid | 40.0% | 20.4% |
| Median over (+) or under (-) the low bid | 32.7% | 17.2% |
| Within 15% of the low bid | 19.4% | 38.3% |

How the lines of the headline contracts were priced:

| Tier | How the line is priced | Share of lines | Share of BidLens dollars |
| ---: | --- | ---: | ---: |
| 1 | Top-100 item: trailing 12-month median | 27.6% | 64.3% |
| 2 | Other standard item: median of earlier bids | 63.7% | 22.8% |
| 3 | Special item: median of earlier bids with the same description | 4.4% | 10.9% |
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
| Traffic Control | 955 | 100.0% | 60.0% | 14.0% |
| Asphalt Surfacing | 585 | 100.0% | 55.1% | 15.7% |
| Water Pollution and Site Management | 506 | 100.0% | 69.4% | 13.0% |
| General and Overhead | 427 | 100.0% | 66.2% | 10.8% |
| Striping and Markings | 422 | 100.0% | 54.7% | 15.2% |
| Earthwork and Clearing | 341 | 100.0% | 59.9% | 12.0% |
| Fencing, Guardrail and Barriers | 221 | 100.0% | 36.1% | 21.7% |
| Structural Concrete and Reinforcement | 219 | 100.0% | 35.8% | 22.8% |
| Landscape and Erosion Control | 208 | 100.0% | 32.3% | 24.5% |
| Electrical and Signals | 177 | 100.0% | 83.5% | 7.9% |
| Bridge Rehabilitation and Removal | 121 | 100.0% | 27.6% | 33.1% |
| Base and Subbase | 106 | 100.0% | 48.3% | 16.0% |
| Minor Concrete and Miscellaneous | 70 | 100.0% | 37.7% | 27.1% |
| Drainage | 55 | 100.0% | 35.6% | 27.3% |
| Concrete Pavement | 45 | 100.0% | 39.0% | 28.9% |
| Piling | 22 | 100.0% | 51.5% | 4.5% |
| Steel Structures, Signs and Painting | 21 | 100.0% | 81.6% | 9.5% |
| Other | 6 | 100.0% | 58.0% | 16.7% |
| All | 4,507 | 100.0% | 54.7% | 15.8% |

Without flagged outliers:

| Group | Prices | Coverage | MdAPE | Within 15% |
| --- | ---: | ---: | ---: | ---: |
| Traffic Control | 944 | 100.0% | 59.3% | 14.2% |
| Asphalt Surfacing | 577 | 100.0% | 54.4% | 15.9% |
| Water Pollution and Site Management | 503 | 100.0% | 68.9% | 13.1% |
| General and Overhead | 425 | 100.0% | 65.9% | 10.8% |
| Striping and Markings | 414 | 100.0% | 53.4% | 15.5% |
| Earthwork and Clearing | 335 | 100.0% | 59.2% | 12.2% |
| Fencing, Guardrail and Barriers | 219 | 100.0% | 35.1% | 21.9% |
| Structural Concrete and Reinforcement | 212 | 100.0% | 34.9% | 23.6% |
| Landscape and Erosion Control | 207 | 100.0% | 31.9% | 24.6% |
| Electrical and Signals | 177 | 100.0% | 83.5% | 7.9% |
| Bridge Rehabilitation and Removal | 118 | 100.0% | 27.4% | 33.9% |
| Base and Subbase | 106 | 100.0% | 48.3% | 16.0% |
| Minor Concrete and Miscellaneous | 69 | 100.0% | 36.8% | 27.5% |
| Drainage | 55 | 100.0% | 35.6% | 27.3% |
| Concrete Pavement | 42 | 100.0% | 35.2% | 31.0% |
| Piling | 22 | 100.0% | 51.5% | 4.5% |
| Steel Structures, Signs and Painting | 18 | 100.0% | 88.8% | 11.1% |
| Other | 6 | 100.0% | 58.0% | 16.7% |
| All | 4,449 | 100.0% | 53.8% | 16.0% |

By bid year (all test prices):

| Group | Prices | Coverage | MdAPE | Within 15% |
| --- | ---: | ---: | ---: | ---: |
| 2024 | 1,758 | 100.0% | 54.7% | 14.8% |
| 2025 | 1,748 | 100.0% | 53.5% | 16.9% |
| 2026 | 1,001 | 100.0% | 56.1% | 15.8% |
| All | 4,507 | 100.0% | 54.7% | 15.8% |

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
