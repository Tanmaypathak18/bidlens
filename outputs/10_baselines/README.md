# 10 Baselines: XGBoost and LightGBM

Two machine-learning models that price bid items, scored on the step 2.1 test (step 2.3).

## What we did

Both models (XGBoost and LightGBM, two widely used decision-tree methods) learn the low
bidder's unit price from bids opened before 01 January 2024, then price every test item
from January 2024 on. They see only what an estimator knows before bids open (decision
D-041): the item and its family, the quantity (and how it compares with the item's usual
quantity), district and county, the time of year and the date, the contract's size
(engineer's estimate, working days, number of items), the type of work from the contract
description, and the item's recent median price. Prices are in constant dollars (stage
09) while learning, and converted back to each bid's date.

Settings were chosen on the training years only: fit on bids before 2023 and pick the
best of 30 random settings on 2023 bids. Each final model averages three fits with
different random seeds (decision D-042), because a single fit's score moved by about two
points from seed to seed.

## Results

All test prices: XGBoost misses the low-bid unit price by a median of
**47.1%**, LightGBM by **43.4%**,
against 54.7% for the trailing median. Within 15% of
the low bid: 17.6%, 19.4%
and 15.8%. Without flagged outliers:
46.4%, 42.8% and
53.8%.

By item family (all test prices; "Best" is the lowest MdAPE):

| Item family | Prices | Median MdAPE | XGBoost MdAPE | LightGBM MdAPE | Median within 15% | XGBoost within 15% | LightGBM within 15% | Best |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Traffic Control | 955 | 60.0% | 55.4% | 52.7% | 13.9% | 14.3% | 16.5% | LightGBM |
| Asphalt Surfacing | 585 | 55.1% | 49.1% | 42.1% | 15.7% | 15.2% | 22.2% | LightGBM |
| Water Pollution and Site Management | 506 | 69.4% | 62.1% | 56.9% | 13.0% | 15.2% | 15.6% | LightGBM |
| General and Overhead | 427 | 66.2% | 57.6% | 52.1% | 10.8% | 14.3% | 15.5% | LightGBM |
| Striping and Markings | 422 | 54.7% | 38.2% | 34.6% | 15.2% | 22.0% | 23.5% | LightGBM |
| Earthwork and Clearing | 341 | 59.9% | 49.2% | 46.2% | 12.0% | 18.5% | 19.1% | LightGBM |
| Fencing, Guardrail and Barriers | 221 | 36.1% | 33.7% | 28.5% | 21.7% | 25.8% | 29.4% | LightGBM |
| Structural Concrete and Reinforcement | 219 | 35.8% | 35.7% | 33.7% | 22.8% | 19.6% | 20.1% | LightGBM |
| Landscape and Erosion Control | 208 | 32.3% | 35.6% | 26.9% | 24.5% | 25.5% | 24.0% | LightGBM |
| Electrical and Signals | 177 | 83.5% | 95.1% | 76.4% | 7.9% | 11.9% | 5.6% | LightGBM |
| Bridge Rehabilitation and Removal | 121 | 27.6% | 38.4% | 34.5% | 33.1% | 16.5% | 24.0% | Trailing 12-month median |
| Base and Subbase | 106 | 48.3% | 36.4% | 34.5% | 16.0% | 17.9% | 20.8% | LightGBM |
| Minor Concrete and Miscellaneous | 70 | 37.7% | 22.1% | 22.8% | 27.1% | 38.6% | 40.0% | XGBoost |
| Drainage | 55 | 35.6% | 25.3% | 28.3% | 27.3% | 29.1% | 27.3% | XGBoost |
| Concrete Pavement | 45 | 39.0% | 36.3% | 28.7% | 28.9% | 15.6% | 17.8% | LightGBM |
| Piling | 22 | 51.5% | 42.7% | 47.0% | 4.5% | 18.2% | 13.6% | XGBoost |
| Steel Structures, Signs and Painting | 21 | 81.6% | 57.9% | 50.4% | 9.5% | 38.1% | 23.8% | LightGBM |
| Other | 6 | 58.0% | 75.2% | 122.8% | 16.7% | 0.0% | 0.0% | Trailing 12-month median |
| All | 4,507 | 54.7% | 47.1% | 43.4% | 15.8% | 17.6% | 19.4% | LightGBM |

Families where the trailing median beats both models: Bridge Rehabilitation and Removal, Other.

By bid year (MdAPE):

| Bid year | Median | XGBoost | LightGBM |
| --- | ---: | ---: | ---: |
| 2024 | 54.7% | 42.4% | 41.1% |
| 2025 | 53.5% | 47.5% | 42.7% |
| 2026 | 56.1% | 56.7% | 48.2% |
| All | 54.7% | 47.1% | 43.4% |

## What the models rely on

Share of each model's learning gain, top five: XGBoost: item_code 86.1%; log_trailing_median 9.5%; log_engineers_estimate 1.3%; log_quantity 1.1%; log_quantity_vs_history 0.6%. LightGBM:
log_trailing_median 54.2%; log_quantity 25.3%; item_code 11.6%; unit 3.6%; log_engineers_estimate 1.3%. The engineer's estimate carries 1.3% (XGBoost) and
1.3% (LightGBM) of the gain.

## Tuning and speed

| | XGBoost | LightGBM |
| --- | ---: | ---: |
| Validation MdAPE (2023 bids) | 38.1% | 38.7% |
| Same setting, six single seeds | 37.5% to 38.9% | 38.7% to 40.5% |
| Three-seed average, two seed sets (used, D-042) | 38.4%, 37.9% | 38.8%, 39.9% |
| Trees | 130 | 258 |
| Tuning time (30 trials) | 16 s | 90 s |
| Final fit time (three fits) | 0.5 s | 2.1 s |
| Time to price all 4,507 test items | 9 ms | 25 ms |

## Files

- `scores.csv`: MdAPE, within-15% and coverage for each model, by family and by year, with
  and without outliers.
- `predictions.csv`: every test price with the three predictions.
- `tuning_xgboost.csv`, `tuning_lightgbm.csv`: all 30 settings tried and their 2023 scores.
- `feature_importance.csv`: each feature's share of each model's gain.

The fitted models (three per library) are saved in `data/models/` (not committed; rebuild
with the command below).

## How it was produced

`uv run python -m bidlens.pricing.baseline` (code in `src/bidlens/pricing/baseline.py` and
`features.py`). Generated 2026-11-20.
