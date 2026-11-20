# 13 Model comparison and selection

Which pricing method BidLens uses, and how it compares with Caltrans' engineer's estimate
(step 2.5).

## The question

Four ways of pricing a bid item have been built: the historical median of recent low bids
(stage 08), XGBoost and LightGBM (stage 10), and NVIDIA Kumo Tabular (stage 11). Which one
should BidLens use, and is a BidLens total closer to the winning bid than the engineer's
estimate?

## Two ways of running the models (decision D-045)

Stages 10 and 11 froze the models at the end of 2023 and tested them on almost three
years of later bids. The sanity check (stage 12) showed they drift high as time passes.
In real use BidLens always has the latest bids, so each model is also run **refreshed
each quarter**: before pricing a quarter's bids it sees every bid opened before that
quarter. It still never sees the bids it is pricing.

## The choice (decision D-046)

The choice was made on 2023 bids (everything before 2023 as history), not on the test
years, so the test results below are an honest check of it:

| Method | Validation median miss (2023 bids) |
| --- | ---: |
| Historical median | 56.8% |
| XGBoost | 40.1% |
| LightGBM | 41.2% |
| Kumo Tabular | 36.8% |

**Default: Kumo Tabular.** Family exceptions (a method must beat the default by 5
points on at least 50 validation prices): none (no family cleared the bar).

## Results on the test years (2024 to 2026)

### Single items

| Method | How it runs | Median miss | Within 15% | Median over (+) / under (-) | Without outliers |
| --- | --- | ---: | ---: | ---: | ---: |
| Historical median | Latest bids, always | 55.0% | 15.3% | +7.3% | 54.0% |
| XGBoost | Frozen at the end of 2023 | 46.1% | 18.0% | +27.9% | 45.7% |
| LightGBM | Frozen at the end of 2023 | 43.4% | 19.4% | +20.6% | 43.0% |
| Kumo Tabular | Frozen at the end of 2023 | 40.2% | 20.5% | +13.4% | 39.7% |
| XGBoost | Refreshed each quarter | 40.1% | 20.9% | +2.0% | 39.6% |
| LightGBM | Refreshed each quarter | 38.9% | 20.9% | +0.5% | 38.4% |
| Kumo Tabular | Refreshed each quarter | 38.2% | 20.8% | -9.3% | 37.7% |
| BidLens (chosen) | Refreshed each quarter | 38.2% | 20.8% | -9.3% | 37.7% |

By item family (refreshed; median miss):

| Item family | Prices | Historical median | XGBoost | LightGBM | Kumo Tabular | BidLens (chosen) | Best |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Traffic Control | 955 | 60.0% | 50.8% | 48.6% | 46.8% | 46.8% | Kumo Tabular |
| Asphalt Surfacing | 585 | 55.4% | 35.2% | 35.8% | 30.7% | 30.7% | Kumo Tabular |
| Water Pollution and Site Management | 506 | 69.3% | 55.1% | 54.1% | 53.4% | 53.4% | Kumo Tabular |
| General and Overhead | 427 | 65.8% | 43.1% | 38.7% | 38.8% | 38.8% | LightGBM |
| Striping and Markings | 422 | 54.2% | 34.7% | 32.8% | 33.5% | 33.5% | LightGBM |
| Earthwork and Clearing | 341 | 60.7% | 41.8% | 41.5% | 46.4% | 46.4% | LightGBM |
| Fencing, Guardrail and Barriers | 221 | 37.3% | 27.5% | 28.0% | 26.9% | 26.9% | Kumo Tabular |
| Structural Concrete and Reinforcement | 219 | 37.0% | 34.7% | 34.2% | 29.8% | 29.8% | Kumo Tabular |
| Landscape and Erosion Control | 208 | 34.1% | 23.2% | 23.4% | 24.3% | 24.3% | XGBoost |
| Electrical and Signals | 177 | 86.3% | 81.3% | 74.8% | 74.7% | 74.7% | Kumo Tabular |
| Bridge Rehabilitation and Removal | 121 | 27.8% | 27.7% | 30.4% | 21.8% | 21.8% | Kumo Tabular |
| Base and Subbase | 106 | 48.1% | 34.9% | 35.4% | 37.3% | 37.3% | XGBoost |
| Minor Concrete and Miscellaneous | 70 | 42.3% | 28.1% | 23.2% | 27.7% | 27.7% | LightGBM |
| Drainage | 55 | 36.3% | 27.3% | 29.0% | 25.7% | 25.7% | Kumo Tabular |
| Concrete Pavement | 45 | 38.6% | 24.7% | 18.4% | 12.0% | 12.0% | Kumo Tabular |
| Piling | 22 | 46.1% | 41.3% | 39.8% | 37.7% | 37.7% | Kumo Tabular |
| Steel Structures, Signs and Painting | 21 | 79.4% | 42.9% | 36.8% | 55.5% | 55.5% | LightGBM |
| Other | 6 | 54.3% | 56.4% | 73.8% | 39.2% | 39.2% | Kumo Tabular |

Where each method loses (another method has a lower median miss on the test years):

- **Historical median** is beaten in 18 of 18 families: Traffic Control, Asphalt Surfacing, Water Pollution and Site Management, General and Overhead, Striping and Markings, Earthwork and Clearing, Fencing, Guardrail and Barriers, Structural Concrete and Reinforcement, Landscape and Erosion Control, Electrical and Signals, Bridge Rehabilitation and Removal, Base and Subbase, Minor Concrete and Miscellaneous, Drainage, Concrete Pavement, Piling, Steel Structures, Signs and Painting, Other.
- **XGBoost** is beaten in 16 of 18 families: Traffic Control, Asphalt Surfacing, Water Pollution and Site Management, General and Overhead, Striping and Markings, Earthwork and Clearing, Fencing, Guardrail and Barriers, Structural Concrete and Reinforcement, Electrical and Signals, Bridge Rehabilitation and Removal, Minor Concrete and Miscellaneous, Drainage, Concrete Pavement, Piling, Steel Structures, Signs and Painting, Other.
- **LightGBM** is beaten in 13 of 18 families: Traffic Control, Asphalt Surfacing, Water Pollution and Site Management, Fencing, Guardrail and Barriers, Structural Concrete and Reinforcement, Landscape and Erosion Control, Electrical and Signals, Bridge Rehabilitation and Removal, Base and Subbase, Drainage, Concrete Pavement, Piling, Other.
- **Kumo Tabular** is beaten in 7 of 18 families: General and Overhead, Striping and Markings, Earthwork and Clearing, Landscape and Erosion Control, Base and Subbase, Minor Concrete and Miscellaneous, Steel Structures, Signs and Painting.

By bid year (median miss, and median over or under in brackets):

| Bid year | Historical median | XGBoost | LightGBM | Kumo Tabular | BidLens (chosen) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2024 | 55.5% (+12%) | 37.8% (+10%) | 37.1% (+8%) | 35.3% (-3%) | 35.3% (-3%) |
| 2025 | 53.3% (+4%) | 40.1% (-1%) | 38.2% (-1%) | 39.7% (-14%) | 39.7% (-14%) |
| 2026 | 56.5% (+8%) | 45.4% (-8%) | 44.0% (-9%) | 41.0% (-12%) | 41.0% (-12%) |

### Whole contracts: the headline

Every line of each test contract's bid list is priced (top-100 items by the method; other
lines by earlier prices for the same item, as in stage 08), and added up.

| Total built with | Closer than the EE | Typical miss | Median over (+) / under (-) | Within 15% |
| --- | ---: | ---: | ---: | ---: |
| Historical median | 31.5% | 43.0% | +38.2% | 20.2% |
| XGBoost | 54.5% | 21.8% | +10.9% | 34.3% |
| LightGBM | 55.6% | 22.0% | +7.6% | 34.8% |
| Kumo Tabular | 57.9% | 18.4% | +0.8% | 43.3% |
| BidLens (chosen) | 57.9% | 18.4% | +0.8% | 43.3% |
| Engineer's estimate | | 21.2% | +19.9% | 35.4% |

On the 178 headline contracts (at least 90% of lines have price
history), **the BidLens total landed closer to the low bid than Caltrans' engineer's
estimate on 57.9% of contracts.** Over all
201 test contracts: 55.2%.

The engineer's estimate sits above the low bid on most contracts (median
+19.9%): the low bid is the most aggressive of several bids,
and in 2024 to 2026 low bids in Districts 4 and 5 came in well under Caltrans' estimates.
The BidLens total is centred much closer to the low bid (median
+0.8%), because it is built from earlier
low bids rather than from an engineer's cost build-up.

## Speed and licence

| Method | Time per quarter's refresh and pricing | Training | Licence |
| --- | ---: | --- | --- |
| Historical median | under 1 s | none | None needed (simple statistic) |
| XGBoost | 1.5 s | refit, three seeds | Apache-2.0 |
| LightGBM | 11.1 s | refit, three seeds | MIT |
| Kumo Tabular | 9.8 s | none: reads a table of known prices | Code Apache-2.0; weights OpenMDW-1.1 |

## What is saved

`data/models/production.json` records the choice (default method, family exceptions,
refresh rule and model versions). The app (step 4.1) prices with it. Not committed; rebuild
with the commands below.

## Files

- `validation_choice.csv`: 2023 validation median miss per family and method, and the choice.
- `test_by_family.csv`, `test_by_year.csv`: the tables above.
- `test_predictions_refreshed.csv`: every test price with each method's refreshed prediction.
- `contract_totals_refreshed.csv`: every test contract's totals by method, with errors.

## How it was produced

`uv run python -m bidlens.pricing.refresh --model xgboost` (then `lightgbm`, then `kumo`;
one process each), then `uv run python -m bidlens.pricing.select`. Code in
`src/bidlens/pricing/`. Generated 2026-11-20.

## Charts from the notebook

`notebooks/05_model_comparison.ipynb` explains this stage and saved these charts here: `nb_contract_totals_vs_low_bid.png`, `nb_drift_frozen_vs_refreshed.png`, `nb_mdape_by_family_refreshed.png`.
