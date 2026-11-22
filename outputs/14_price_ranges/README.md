# 14 Price ranges and comparable bids

A low / likely / high price for every bid item, and the past bids behind it (step 2.6).

## What the range means

For each item BidLens gives three prices: **low**, **likely** and **high**. The range is
built so that the winning bidder's unit price falls between low and high on about
80.0% of items, below low on about 10% and above high on about 10%. Likely is
the model's middle estimate (stage 13).

## How it is built

Kumo Tabular gives a full spread of possible prices, not just one number. Its own
10th-to-90th percentile range is the starting point. Each quarter, BidLens checks how
often that range held the actual low bid on every earlier priced item, and widens (or
narrows) it until it would have held 80% of them, separately for lump sums and for
unit-priced items, which are much less predictable. Only past results are used.

## Does it hold up on the test years?

On 4,507 test prices (2024 to 2026): the BidLens range held the actual low bid on
**79.0%** of items (target 80%); 7.6% came in below low and
13.4% above high. Kumo's own range, before this adjustment, held
82.7% (84.8% on 2023 validation bids). The typical range is
5.3 times as high at the top as at the bottom, a direct reflection of
how noisy single low-bid prices are (stage 12).

| Kind of item | Prices | Kumo's own range | BidLens range | Typical width (high / low) |
| --- | ---: | ---: | ---: | ---: |
| Priced per unit | 2,923 | 82.7% | 80.0% | 4.1x |
| Lump sum | 1,584 | 82.7% | 77.3% | 12.6x |

| Bid year | Prices | Kumo's own range | BidLens range | Typical width (high / low) |
| --- | ---: | ---: | ---: | ---: |
| 2024 | 1,758 | 82.7% | 77.5% | 4.4x |
| 2025 | 1,748 | 82.7% | 79.6% | 5.6x |
| 2026 | 1,001 | 82.7% | 80.7% | 7.0x |

| Item family | Prices | Kumo's own range | BidLens range | Typical width (high / low) |
| --- | ---: | ---: | ---: | ---: |
| Traffic Control | 955 | 81.0% | 76.5% | 6.8x |
| Asphalt Surfacing | 585 | 84.4% | 81.4% | 4.9x |
| Water Pollution and Site Management | 506 | 83.8% | 80.6% | 15.7x |
| General and Overhead | 427 | 83.8% | 75.6% | 6.7x |
| Striping and Markings | 422 | 80.6% | 78.0% | 4.0x |
| Earthwork and Clearing | 341 | 81.5% | 79.8% | 8.0x |
| Fencing, Guardrail and Barriers | 221 | 81.9% | 78.7% | 3.1x |
| Structural Concrete and Reinforcement | 219 | 80.4% | 76.7% | 3.4x |
| Landscape and Erosion Control | 208 | 85.1% | 81.2% | 2.9x |
| Electrical and Signals | 177 | 83.6% | 80.8% | 41.3x |
| Bridge Rehabilitation and Removal | 121 | 87.6% | 85.1% | 3.4x |
| Base and Subbase | 106 | 82.1% | 80.2% | 5.0x |
| Minor Concrete and Miscellaneous | 70 | 81.4% | 80.0% | 4.0x |
| Drainage | 55 | 83.6% | 81.8% | 3.8x |
| Concrete Pavement | 45 | 91.1% | 86.7% | 2.7x |
| Piling | 22 | 86.4% | 86.4% | 3.7x |
| Steel Structures, Signs and Painting | 21 | 71.4% | 71.4% | 21.4x |
| Other | 6 | 100.0% | 100.0% | 3.5x |

## Comparable bids

Every price comes with the 10 most similar earlier low bids for the same item: closest in
quantity first, then recent, same district and similar contract size. Each links to its
Caltrans source page. 99.2% of test prices have a full 10. As a check,
the median of an item's comparables (in today's dollars) misses the low bid by a median of
43.2%, and the actual price falls inside the comparables' span on
81.4% of items.

### Examples

**120100 (LS), contract 04-0K1104, bid 10 Jan 2024, quantity 1:** range $95,087.87 / $303,913.95 / $773,728.00; actual low bid $1,700,000.00.

| Comparable contract | Bid date | District | Quantity | Unit price | In this bid's dollars |
| --- | --- | --- | ---: | ---: | ---: |
| [04-3G3644](https://sv08data.dot.ca.gov/details.php?Num=4844670) | 2023-12-14 | 04 | 1 | $624,000.00 | $643,136.31 |
| [04-3G4444](https://sv08data.dot.ca.gov/details.php?Num=4838414) | 2023-11-30 | 04 | 1 | $909,000.00 | $936,876.45 |
| [04-0K7804](https://sv08data.dot.ca.gov/details.php?Num=4833743) | 2023-10-25 | 04 | 1 | $200,000.00 | $206,133.43 |
| [04-0P9804](https://sv08data.dot.ca.gov/details.php?Num=4849373) | 2023-12-14 | 04 | 1 | $325,000.00 | $334,966.83 |
| [04-3W7504](https://sv08data.dot.ca.gov/details.php?Num=4845050) | 2023-11-01 | 04 | 1 | $800,000.00 | $824,533.73 |

**120100 (LS), contract 04-0P1204, bid 13 Feb 2024, quantity 1:** range $45,499.69 / $118,830.69 / $226,127.24; actual low bid $60,000.00.

| Comparable contract | Bid date | District | Quantity | Unit price | In this bid's dollars |
| --- | --- | --- | ---: | ---: | ---: |
| [04-3Y5204](https://sv08data.dot.ca.gov/details.php?Num=4865680) | 2024-02-07 | 04 | 1 | $130,000.00 | $130,000.00 |
| [04-3Q7604](https://sv08data.dot.ca.gov/details.php?Num=4856341) | 2023-12-12 | 04 | 1 | $187,000.00 | $192,734.76 |
| [04-4J5404](https://sv08data.dot.ca.gov/details.php?Num=4829428) | 2023-11-28 | 04 | 1 | $82,327.00 | $84,851.74 |
| [04-0K1304](https://sv08data.dot.ca.gov/details.php?Num=4827242) | 2023-09-13 | 04 | 1 | $170,000.00 | $187,437.38 |
| [04-3W5204](https://sv08data.dot.ca.gov/details.php?Num=4866063) | 2024-01-09 | 04 | 1 | $250,000.00 | $250,000.00 |

**120100 (LS), contract 04-0Q0704, bid 14 Feb 2024, quantity 1:** range $87,254.53 / $285,734.98 / $681,755.84; actual low bid $915,000.00.

| Comparable contract | Bid date | District | Quantity | Unit price | In this bid's dollars |
| --- | --- | --- | ---: | ---: | ---: |
| [04-3W7604](https://sv08data.dot.ca.gov/details.php?Num=4866690) | 2024-01-30 | 04 | 1 | $250,000.00 | $250,000.00 |
| [04-2Q5704](https://sv08data.dot.ca.gov/details.php?Num=4860193) | 2024-01-10 | 04 | 1 | $50,000.00 | $50,000.00 |
| [04-3G3644](https://sv08data.dot.ca.gov/details.php?Num=4844670) | 2023-12-14 | 04 | 1 | $624,000.00 | $643,136.31 |
| [04-0K1104](https://sv08data.dot.ca.gov/details.php?Num=4863284) | 2024-01-10 | 04 | 1 | $1,700,000.00 | $1,700,000.00 |
| [04-3W5504](https://sv08data.dot.ca.gov/details.php?Num=4851615) | 2024-01-11 | 04 | 1 | $287,430.00 | $287,430.00 |


## Files

- `test_ranges.csv`: every test price with its low / likely / high, Kumo's own 10th and
  90th percentiles, and the quarter's adjustment.
- `coverage_by_group.csv`: the coverage tables above.
- `comparable_bids.csv`: the 10 comparable bids for every test price, with source links.
- `results.json`: the headline numbers.

## How it was produced

`uv run python -m bidlens.pricing.refresh --model kumo`, then
`uv run python -m bidlens.pricing.ranges` (code in `src/bidlens/pricing/ranges.py` and
`comparables.py`). Generated 2026-11-20.

## Charts from the notebook

`notebooks/05_model_comparison.ipynb` explains this stage and saved these charts here: `nb_range_coverage_by_family.png`.
