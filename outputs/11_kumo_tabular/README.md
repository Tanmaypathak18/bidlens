# 11 Kumo Tabular

NVIDIA Kumo Tabular, a pretrained model for tables, scored on the same test as the
baselines (step 2.4).

## What we did

Kumo Tabular is not trained on our data. It is given a table of known prices (every
cleaned training bid before 01 January 2024: 10,091 rows, with the same
22 facts per bid as the baselines) and predicts each test price from it in one pass. It
runs on this Mac's processor with NVIDIA's small model (decision D-043), downloaded once
from Hugging Face (`nvidia/Kumo-Tabular`, version v1.0.1).

Settings were chosen on 2023 bids before looking at the test: one shared table of known
prices beat separate tables per item family (36.8% vs 38.4% median miss), and the small
model beat the medium one (36.8% vs 37.2%) at a third of the time.

## Results

All 4,507 test prices: Kumo misses the low-bid unit price by a median of
**40.2%** and is within 15% on 20.5% of them,
against 43.4% and 19.4% for LightGBM,
46.1% and 18.0% for XGBoost, and
55.0% and 15.3% for the
trailing median. Without flagged outliers, Kumo: 39.7%.

Median miss by item family ("Best" is the lowest):

| Item family | Prices | Median | XGBoost | LightGBM | Kumo | Best |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Traffic Control | 955 | 60.0% | 54.2% | 53.1% | 50.5% | Kumo |
| Asphalt Surfacing | 585 | 55.4% | 47.0% | 39.8% | 37.9% | Kumo |
| Water Pollution and Site Management | 506 | 69.3% | 60.3% | 57.9% | 55.7% | Kumo |
| General and Overhead | 427 | 65.8% | 55.0% | 54.9% | 43.7% | Kumo |
| Striping and Markings | 422 | 54.2% | 37.9% | 37.5% | 31.2% | Kumo |
| Earthwork and Clearing | 341 | 60.7% | 47.0% | 43.2% | 46.3% | LightGBM |
| Fencing, Guardrail and Barriers | 221 | 37.3% | 31.5% | 31.2% | 27.6% | Kumo |
| Structural Concrete and Reinforcement | 219 | 37.0% | 37.9% | 31.1% | 32.1% | LightGBM |
| Landscape and Erosion Control | 208 | 34.1% | 38.0% | 30.0% | 29.1% | Kumo |
| Electrical and Signals | 177 | 86.3% | 94.3% | 88.1% | 83.5% | Kumo |
| Bridge Rehabilitation and Removal | 121 | 27.8% | 35.1% | 28.1% | 32.2% | Median |
| Base and Subbase | 106 | 48.1% | 36.5% | 35.4% | 34.4% | Kumo |
| Minor Concrete and Miscellaneous | 70 | 42.3% | 28.4% | 23.2% | 27.0% | LightGBM |
| Drainage | 55 | 36.3% | 29.5% | 29.6% | 27.1% | Kumo |
| Concrete Pavement | 45 | 38.6% | 33.6% | 27.2% | 20.9% | Kumo |
| Piling | 22 | 46.1% | 56.3% | 49.0% | 33.8% | Kumo |
| Steel Structures, Signs and Painting | 21 | 79.4% | 48.6% | 48.4% | 40.7% | Kumo |
| Other | 6 | 54.3% | 96.2% | 89.3% | 75.8% | Median |
| All | 4,507 | 55.0% | 46.1% | 43.4% | 40.2% | Kumo |

Kumo is best in: Traffic Control, Asphalt Surfacing, Water Pollution and Site Management, General and Overhead, Striping and Markings, Fencing, Guardrail and Barriers, Landscape and Erosion Control, Electrical and Signals, Base and Subbase, Drainage, Concrete Pavement, Piling, Steel Structures, Signs and Painting.

By bid year (median miss):

| Bid year | Median | XGBoost | LightGBM | Kumo |
| --- | ---: | ---: | ---: | ---: |
| 2024 | 55.5% | 41.3% | 38.8% | 35.7% |
| 2025 | 53.3% | 46.2% | 42.1% | 42.5% |
| 2026 | 56.5% | 59.6% | 53.4% | 45.2% |
| All | 55.0% | 46.1% | 43.4% | 40.2% |

## Speed and licence

Pricing all 4,507 test items took 11.1 s on CPU, including
reading the 10,091 context rows; there is no training step. The model code is
Apache-2.0 and the weights are OpenMDW-1.1 (both allow commercial use).

## Files

- `scores.csv`: median miss, within-15% and coverage for all four methods, by family and
  year, with and without outliers.
- `predictions.csv`: every test price with Kumo's prediction.

## How it was produced

`uv run python -m bidlens.pricing.kumo` (code in `src/bidlens/pricing/kumo.py`), after
`bidlens.pricing.baseline`. Generated 2026-11-20.

## Charts from the notebook

`notebooks/04_kumo_tabular.ipynb` explains this stage and saved these charts here: `nb_mdape_by_family.png`.
