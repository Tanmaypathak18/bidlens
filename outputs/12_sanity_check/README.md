# 12 Sanity check

A check of the pricing results so far, in plain terms (after step 2.4).

## 1. Whole-contract totals: the headline

For each of the 178 test contracts, each method prices every line of the low bidder's
bid list, and the lines are added up. The 69.6% of contract dollars that are
top-100 items are priced by the model; the other lines use the same historical prices for
every method (stage 08). The engineer's estimate is Caltrans' own figure.

| Total built with | Closer than the EE | Typical miss | Median over (+) / under (-) | Within 15% |
| --- | ---: | ---: | ---: | ---: |
| Historical median | 31.5% | 43.0% | 38.2% | 20.2% |
| XGBoost | 38.2% | 31.8% | 25.6% | 24.7% |
| LightGBM | 45.5% | 28.1% | 18.6% | 30.3% |
| Kumo Tabular | 46.1% | 24.5% | 14.6% | 32.6% |
| Engineer's estimate | | 21.2% | 19.9% | 35.4% |

"Closer than the EE" is the share of contracts where that total was nearer the actual low
bid than Caltrans' engineer's estimate. "Typical miss" is the median distance from the low
bid. Contract totals land much closer than single items because over- and under-priced
lines partly cancel.

## 2. Why single items miss by about 40%

**The low bid itself is noisy.** On the same line of the same contract, the second-lowest
bidder's unit price differs from the low bidder's by a median of **27.5%**
(4,168 lines bid since 2024; 38.6% for lump sums,
23.2% for unit-priced items). Contractors spread their costs
across items differently ("unbalanced" bids), so a single item's low-bid price carries a
lot of noise even when the total is competitive. That sets a floor: no method should be
expected to match single low-bid prices much better than a second real bidder does. The
best model is about 13 points above that floor.

**Lump sums and odd quantities are the hardest.**

| Kind of item | Prices | Historical median | XGBoost | LightGBM | Kumo Tabular |
| --- | ---: | ---: | ---: | ---: | ---: |
| Priced per unit | 2,923 | 45.3% | 39.4% | 35.6% | 34.4% |
| Lump sum | 1,584 | 76.6% | 65.2% | 63.6% | 58.6% |

| Quantity vs the item’s usual quantity | Prices | Historical median | XGBoost | LightGBM | Kumo Tabular |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lump sum (quantity 1) | 1,584 | 76.6% | 65.2% | 63.6% | 58.6% |
| Much larger (over 3x) | 876 | 60.2% | 37.2% | 32.7% | 28.0% |
| Much smaller (under 1/3) | 722 | 54.5% | 46.9% | 46.2% | 43.7% |
| Larger | 529 | 33.7% | 37.6% | 32.2% | 31.7% |
| Smaller | 526 | 37.2% | 38.7% | 34.9% | 35.7% |
| Typical (0.8 to 1.25x) | 270 | 32.9% | 38.1% | 30.8% | 33.7% |

| Engineer’s estimate on file | Prices | Historical median | XGBoost | LightGBM | Kumo Tabular |
| --- | ---: | ---: | ---: | ---: | ---: |
| Known | 3,941 | 55.1% | 45.0% | 42.7% | 39.5% |
| Not available | 566 | 53.4% | 63.6% | 52.1% | 46.7% |

By item family:

| Item family | Prices | Historical median | XGBoost | LightGBM | Kumo Tabular |
| --- | ---: | ---: | ---: | ---: | ---: |
| Traffic Control | 955 | 60.0% | 54.2% | 53.1% | 50.5% |
| Asphalt Surfacing | 585 | 55.4% | 47.0% | 39.8% | 37.9% |
| Water Pollution and Site Management | 506 | 69.3% | 60.3% | 57.9% | 55.7% |
| General and Overhead | 427 | 65.8% | 55.0% | 54.9% | 43.7% |
| Striping and Markings | 422 | 54.2% | 37.9% | 37.5% | 31.2% |
| Earthwork and Clearing | 341 | 60.7% | 47.0% | 43.2% | 46.3% |
| Fencing, Guardrail and Barriers | 221 | 37.3% | 31.5% | 31.2% | 27.6% |
| Structural Concrete and Reinforcement | 219 | 37.0% | 37.9% | 31.1% | 32.1% |
| Landscape and Erosion Control | 208 | 34.1% | 38.0% | 30.0% | 29.1% |
| Electrical and Signals | 177 | 86.3% | 94.3% | 88.1% | 83.5% |
| Bridge Rehabilitation and Removal | 121 | 27.8% | 35.1% | 28.1% | 32.2% |
| Base and Subbase | 106 | 48.1% | 36.5% | 35.4% | 34.4% |
| Minor Concrete and Miscellaneous | 70 | 42.3% | 28.4% | 23.2% | 27.0% |
| Drainage | 55 | 36.3% | 29.5% | 29.6% | 27.1% |
| Concrete Pavement | 45 | 38.6% | 33.6% | 27.2% | 20.9% |
| Piling | 22 | 46.1% | 56.3% | 49.0% | 33.8% |
| Steel Structures, Signs and Painting | 21 | 79.4% | 48.6% | 48.4% | 40.7% |
| Other | 6 | 54.3% | 96.2% | 89.3% | 75.8% |

## 3. Is the error calculated correctly?

The miss is |predicted − actual| / actual, using the low bidder's unit price as the actual,
with both in the dollars of the bid date. Recomputed independently from the saved
predictions:

| Method | Median miss (recomputed) | Median signed error | Share over the low bid |
| --- | ---: | ---: | ---: |
| Historical median | 55.0% | 7.3% | 53.9% |
| XGBoost | 46.1% | 27.9% | 66.2% |
| LightGBM | 43.4% | 20.6% | 62.7% |
| Kumo Tabular | 40.2% | 13.4% | 59.6% |

The recomputed numbers match stages 10 and 11. Errors are measured against the actual
price, so an under-prediction can miss by at most 100% while an over-prediction has no
cap: the median is used for that reason, and the share over the low bid shows whether a
method leans high or low.

**The models lean high, more so the further from the training years.** Median over (+)
or under (-) the low bid, by bid year:

| Method | 2024 | 2025 | 2026 |
| --- | ---: | ---: | ---: |
| Historical median | +11.5% | +3.5% | +8.4% |
| XGBoost | +19.6% | +26.7% | +45.4% |
| LightGBM | +16.5% | +17.8% | +35.5% |
| Kumo Tabular | +7.4% | +15.8% | +24.3% |

The trained models learned prices up to the end of 2023 and carry them forward with
Caltrans' statewide cost index. That index rose about 29% from late 2023 to early 2026,
while low bids for these items in Districts 4 and 5 rose much less, so the models drift
high. The historical median sees the latest bids and drifts much less. A first fix was
made: the index used for a bid is now the one known before that bid
opened, which removed a small look-ahead leak; it did not remove the drift. The real fix
is to let the models see recent bids (refreshing Kumo's table of known prices costs
nothing; the other models would be retrained), which step 2.5 decides.

## Files

- `contract_totals_by_model.csv`: every test contract with each method's total and error.
- `item_error_breakdown.csv`: the item-level tables above.
- `results.json`: the headline numbers.

## How it was produced

`uv run python -m bidlens.pricing.sanity` (code in `src/bidlens/pricing/sanity.py`), after
stages 10 and 11. Generated 2026-11-20.

## Charts from the notebook

`notebooks/04_kumo_tabular.ipynb` explains this stage and saved these charts here: `nb_drift_by_year.png`, `nb_miss_by_quantity.png`.
