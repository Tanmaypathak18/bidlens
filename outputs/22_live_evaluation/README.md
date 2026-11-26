# 22 Live evaluation

How LightGBM, the lighter fallback model of the Evaluate page, does on the
201 test contracts bid in 2024 to 2026, priced exactly as the page prices them.
Wherever Kumo Tabular is installed (a laptop and the hosted demo), the Evaluate page uses
Kumo instead: the listed jobs show stage 13's own Kumo prices, and uploads run Kumo live.

## Method

For each contract, LightGBM (the step 2.3 settings, one seed) is fit at run time on
every cleaned low bid opened before the contract's quarter, and prices the top-100 items;
the other items come from earlier bids for the same item. Ranges are 80%: model items take
the 10th to 90th percentile of the errors a model fit one year earlier made on that last
year's bids (lump sum and unit-priced items separately); other items with at least 5
earlier prices take the 10th to 90th percentile of those prices. The market view is a
linear model on earlier contracts. The actual results are used only to score. LightGBM is
used only where Kumo Tabular can't be installed; Kumo's stage 13 results are shown for
comparison.

## Results

On the 178 headline contracts (the same ones as stage 13):

| | Closer to the low bid than the engineer's estimate | Typical miss |
| --- | ---: | ---: |
| Light live model (LightGBM, fallback) | 51.7% | 22.4% |
| Kumo Tabular (production, stage 13; live on a laptop) | 57.9% | 18.4% |
| Engineer's estimate | | 21.2% |

- The live total is within 15% of the low bid on 34.8% of these
  contracts; its median miss is +8.6%.
- Item ranges held the actual low-bid unit price on 78.1% of
  3,911 model-priced items and
  67.7% of 9,100
  history-priced items (target 80%).
- Market view: low bid against the engineer's estimate missed by 18.0
  points on average (80% range held 78.1%); bidder count missed by
  1.50 (within 1 bidder on 58.7%; range held
  82.1%).
- For scale: the second-lowest bid was a median 6.4% above the
  low bid on these contracts. Bidders themselves disagree by about that much.
- Run time on this laptop: 77 seconds for all contracts
  (0.4 s each, with one model fit per quarter reused).

## Files

- `contract_totals.csv`: one row per contract: live total, engineer's estimate, low bid,
  errors, market view and its range.
- `results.json`: the numbers above.

## How it was produced

`uv run python -m bidlens.live.backtest` (code in `src/bidlens/live/`). Data from the
committed bundle in `data/sample/engine/` (`uv run python -m bidlens.live.bundle`).
Generated 2026-11-25.
