# 15 Market context

What the market is likely to do on a contract: how the low bid will compare with the
engineer's estimate, and how many contractors will bid (step 2.7).

## What we did

Each contract with a bid summary and an engineer's estimate is one row
(464 before January 2024, 208 after). The models see only what is known
before bids open (decision D-049): the engineer's estimate, working days, number of items,
location, time of year, the type of work, the number of plan holders (contractors who
took out the plans), and how the market behaved over the previous 12 months. As in stage
13, each method is refreshed every quarter with all earlier contracts. Three methods are
compared: Kumo Tabular (which also gives a range), a simple linear model, and the
trailing 12-month median.

## Low bid vs the engineer's estimate

On test contracts the low bid averaged -12.7% against the engineer's
estimate. Misses are in percentage points of the estimate.

| Method | Typical miss (mean) | Within 10 points | Median over (+) / under (-) |
| --- | ---: | ---: | ---: |
| Kumo Tabular | 15.7 points | 41.8% | +3.7 points |
| Linear model | 18.3 points | 33.2% | +8.1 points |
| Trailing 12-month median | 17.0 points | 36.5% | +4.6 points |
| Kumo Tabular, without plan holders | 16.4 points | 38.9% | +4.2 points |
| Linear model, without plan holders | 18.5 points | 34.1% | +8.1 points |

The 80% range held the actual spread on **76.9%** of test contracts
(Kumo's own range: 78.4%); a typical range is
49.9 points wide.

## Number of bidders

On test contracts the average was 5.2 bidders. Predictions are rounded to
whole bidders.

| Method | Typical miss (mean) | Within 1 bidder | Median over (+) / under (-) |
| --- | ---: | ---: | ---: |
| Kumo Tabular | 1.33 bidders | 63.5% | +0.0 |
| Linear model | 1.50 bidders | 58.2% | +0.0 |
| Trailing 12-month median | 1.79 bidders | 50.5% | +0.0 |
| Kumo Tabular, without plan holders | 1.60 bidders | 52.4% | +0.0 |
| Linear model, without plan holders | 1.73 bidders | 50.0% | +0.0 |

The 80% range held the actual count on **81.7%** of test contracts
(Kumo's own range: 81.7%); a typical range is
4.4 bidders wide.

## Examples (the five latest test contracts)

| Contract | Bid date | Engineer's estimate | Expected low bid vs EE (range) | Actual | Expected bidders (range) | Actual |
| --- | --- | ---: | --- | ---: | --- | ---: |
| 04-0W0504 | 2026-09-17 | $22,715,571 | -19% (-39% to +2%) | -38% | 5 (3 to 8) | 7 |
| 04-2W6604 | 2026-09-23 | $2,201,133 | -13% (-33% to +9%) | +18% | 5 (3 to 7) | 5 |
| 05-1P2404 | 2026-09-29 | $791,929 | -11% (-34% to +16%) | -36% | 6 (3 to 8) | 6 |
| 04-3AA504 | 2026-10-07 | $3,549,944 | -31% (-52% to -9%) | -36% | 11 (7 to 14) | 11 |
| 05-1Q1504 | 2026-11-03 | $4,192,092 | -24% (-47% to +1%) | -30% | 6 (4 to 9) | 4 |

## What this means for an estimator

The spread is hard to predict for a single contract: even the best method misses by
several points on average, so the range matters more than the middle number. The
bidder count is more predictable, mostly from the plan-holder list.

## Files

- `test_predictions.csv`: every test contract with the actual spread and bidder count,
  Kumo's middle estimate and range, and the other methods.
- `results.json`: all the scores above.

## How it was produced

`uv run python -m bidlens.market.context` (code in `src/bidlens/market/context.py`).
Generated 2026-11-20.

## Charts from the notebook

`notebooks/06_market_context.ipynb` explains this stage and saved these charts here: `nb_bidders_expected_vs_actual.png`, `nb_spread_expected_vs_actual.png`.
