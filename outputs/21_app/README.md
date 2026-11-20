# 21 App

The draft estimate the BidLens app shows for the sample bid package 04-0W0504
(steps 4.1 and 4.2, decisions D-064 and D-065), and the workbook it exports.

## The draft

| | Amount | vs the actual low bid |
| --- | ---: | ---: |
| BidLens draft total (likely prices) | $14,539,427 | +3.2% |
| Engineer's estimate | $22,715,571 | +61.3% |
| Actual low bid (rank 1, public result) | $14,086,513 | |

- 118 bid items from the package's bid item list; 27 of them
  (32% of the draft total) priced by the pricing model with a
  low to high range. The rest come from earlier low bids for the same item, as in step 2.1.
- On the 27 modeled items, the low bidder's unit price fell inside the BidLens
  range on 81% (the range is built to hold 8 in 10).
- Market context: the low bid was expected about -19%
  from the engineer's estimate (likely -39% to
  +2%); it came in at -38%.
  Expected bidders 5; actual 7.
- The actual results are used only for this check, never in the draft.

Document findings in the app and the workbook come from the `combined` extraction run
(stage 20).

## Files

- `draft_estimate_04-0W0504.csv`: every bid item with low, likely and high unit price,
  amount, source, and the low bidder's unit price for the check.
- `draft_estimate_04-0W0504.xlsx`: the exported workbook (Estimate with live formulas,
  Comparables, Risk register, Closure hours, About).

## How it was produced

`uv run python -m bidlens.estimate 04-0W0504` (3 seconds), then the app:
`uv run streamlit run app/Home.py`. Code in `src/bidlens/estimate.py`,
`src/bidlens/export.py` and `app/`. Generated 2026-11-20.
