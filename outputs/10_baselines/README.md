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
**46.1%**, LightGBM by **43.4%**,
against 55.0% for the trailing median. Within 15% of
the low bid: 18.0%, 19.4%
and 15.3%. Without flagged outliers:
45.7%, 43.0% and
54.0%.

By item family (all test prices; "Best" is the lowest MdAPE):

| Item family | Prices | Median MdAPE | XGBoost MdAPE | LightGBM MdAPE | Median within 15% | XGBoost within 15% | LightGBM within 15% | Best |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Traffic Control | 955 | 60.0% | 54.2% | 53.1% | 13.2% | 15.1% | 15.0% | LightGBM |
| Asphalt Surfacing | 585 | 55.4% | 47.0% | 39.8% | 15.2% | 17.1% | 21.5% | LightGBM |
| Water Pollution and Site Management | 506 | 69.3% | 60.3% | 57.9% | 13.4% | 15.0% | 15.8% | LightGBM |
| General and Overhead | 427 | 65.8% | 55.0% | 54.9% | 10.1% | 14.1% | 16.4% | LightGBM |
| Striping and Markings | 422 | 54.2% | 37.9% | 37.5% | 16.1% | 22.0% | 20.9% | LightGBM |
| Earthwork and Clearing | 341 | 60.7% | 47.0% | 43.2% | 11.4% | 18.5% | 17.3% | LightGBM |
| Fencing, Guardrail and Barriers | 221 | 37.3% | 31.5% | 31.2% | 19.5% | 26.7% | 24.4% | LightGBM |
| Structural Concrete and Reinforcement | 219 | 37.0% | 37.9% | 31.1% | 21.5% | 20.5% | 23.7% | LightGBM |
| Landscape and Erosion Control | 208 | 34.1% | 38.0% | 30.0% | 23.6% | 26.0% | 26.9% | LightGBM |
| Electrical and Signals | 177 | 86.3% | 94.3% | 88.1% | 7.9% | 12.4% | 9.0% | Trailing 12-month median |
| Bridge Rehabilitation and Removal | 121 | 27.8% | 35.0% | 28.1% | 31.4% | 16.5% | 32.2% | Trailing 12-month median |
| Base and Subbase | 106 | 48.1% | 36.5% | 35.4% | 17.0% | 23.6% | 23.6% | LightGBM |
| Minor Concrete and Miscellaneous | 70 | 42.3% | 28.4% | 23.2% | 24.3% | 37.1% | 35.7% | LightGBM |
| Drainage | 55 | 36.3% | 29.5% | 29.6% | 27.3% | 20.0% | 29.1% | XGBoost |
| Concrete Pavement | 45 | 38.6% | 33.6% | 27.2% | 20.0% | 13.3% | 35.6% | LightGBM |
| Piling | 22 | 46.1% | 56.3% | 49.0% | 4.5% | 18.2% | 22.7% | Trailing 12-month median |
| Steel Structures, Signs and Painting | 21 | 79.4% | 48.6% | 48.4% | 14.3% | 23.8% | 28.6% | LightGBM |
| Other | 6 | 54.3% | 96.2% | 89.3% | 16.7% | 0.0% | 0.0% | Trailing 12-month median |
| All | 4,507 | 55.0% | 46.1% | 43.4% | 15.3% | 18.0% | 19.4% | LightGBM |

Families where the trailing median beats both models: Electrical and Signals, Bridge Rehabilitation and Removal, Piling, Other.

By bid year (MdAPE):

| Bid year | Median | XGBoost | LightGBM |
| --- | ---: | ---: | ---: |
| 2024 | 55.5% | 41.3% | 38.8% |
| 2025 | 53.3% | 46.2% | 42.1% |
| 2026 | 56.5% | 59.6% | 53.4% |
| All | 55.0% | 46.1% | 43.4% |

## What the models rely on

Share of each model's learning gain, top five: XGBoost: item_code 72.1%; log_trailing_median 16.6%; log_quantity 6.6%; log_engineers_estimate 1.2%; unit 1.0%. LightGBM:
log_trailing_median 53.1%; log_quantity 23.4%; item_code 12.3%; unit 4.5%; item_family 1.7%. The engineer's estimate carries 1.2% (XGBoost) and
1.3% (LightGBM) of the gain.

## Tuning and speed

| | XGBoost | LightGBM |
| --- | ---: | ---: |
| Validation MdAPE (2023 bids) | 39.6% | 40.8% |
| Same setting, six single seeds | 39.6% to 40.9% | 40.8% to 43.4% |
| Three-seed average, two seed sets (used, D-042) | 40.1%, 40.1% | 41.2%, 42.7% |
| Trees | 457 | 212 |
| Tuning time (30 trials) | 16 s | 89 s |
| Final fit time (three fits) | 1.4 s | 10.7 s |
| Time to price all 4,507 test items | 16 ms | 46 ms |

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

## Charts from the notebook

`notebooks/03_xgboost_baseline.ipynb` explains this stage and saved these charts here: `nb_feature_importance.png`, `nb_mdape_by_family.png`, `nb_mdape_by_year.png`.
