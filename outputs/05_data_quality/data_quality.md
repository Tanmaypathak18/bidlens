# Data quality report (step 1.6)

Generated 2026-11-19 from `data/bidlens.duckdb` by `uv run python -m bidlens.db.checks` (part of `make data`). Nothing is deleted. Flags sit in the database tables `bid_flag` and `contract_flag` and in the CSV files next to this report.

## Bid price checks

72,113 bid prices checked.

| Check | What it means | Bids flagged | Share |
| --- | --- | --- | --- |
| missing_value | A required price field is empty | 0 | 0.00% |
| non_positive_price | Unit price is zero or negative | 1 | 0.00% |
| duplicate_bid | The same bid appears twice (same item line and rank, or the same source row) | 0 | 0.00% |
| total_mismatch | Total differs from quantity × unit price by more than 1% | 0 | 0.00% |
| price_outlier | Robust z-score of log unit price above 3.5 within the item and unit | 773 | 1.07% |
| **any flag** | | **774** | **1.07%** |

Price outliers by bid rank: 134 low bids (rank 1) and 639 higher bids. High outliers are often small quantities or unusual work. Low outliers are often unbalanced bids. Both can be real, so they are flagged for the models to handle, not removed.

**Items with the most outlier flags:**

| Item | Description | Flagged | Bids | Share |
| --- | --- | --- | --- | --- |
| 397005 | TACK COAT | 105 | 2,529 | 4.2% |
| 846007 | 6" THERMOPLASTIC TRAFFIC STRIPE (ENHANCED WET NIGHT VISIBILITY) | 67 | 2,335 | 2.9% |
| 390137 | RUBBERIZED HOT MIX ASPHALT (GAP GRADED) | 44 | 914 | 4.8% |
| 840516 | THERMOPLASTIC PAVEMENT MARKING (ENHANCED WET NIGHT VISIBILITY) | 43 | 1,539 | 2.8% |
| 520102 | BAR REINFORCING STEEL (BRIDGE) | 41 | 713 | 5.8% |
| 832007 | MIDWEST GUARDRAIL SYSTEM (WOOD POST) | 39 | 725 | 5.4% |
| 090100 | TIME-RELATED OVERHEAD (WDAY) | 29 | 2,754 | 1.1% |
| 120100 | TRAFFIC CONTROL SYSTEM | 26 | 3,990 | 0.7% |
| 390132 | HOT MIX ASPHALT (TYPE A) | 23 | 2,763 | 0.8% |
| 130640 | TEMPORARY FIBER ROLL | 19 | 1,602 | 1.2% |

## Contract checks

848 contract openings checked.

| Check | What it means | Contracts flagged |
| --- | --- | --- |
| low_bidder_disagrees | The cost database's rank-1 bidder is not the bid summary's low bidder | 11 |
| bidder_count_mismatch | Highest bid rank in the cost database differs from ranked bidders in the summary | 8 |
| missing_engineers_estimate | No engineer's estimate (no usable bid summary) | 176 |

**How to read these:**
- `low_bidder_disagrees` marks contracts where the two Caltrans sources name different low bidders, most likely because a low bid was later rejected. Rank-1 prices in these contracts may not be the winning prices (see `04_cross_check`).
- `missing_engineers_estimate` contracts are listed with their reasons in `missing_data.csv`.

## Files

- `bid_flags.csv`: every flagged bid price, with its flag, detail and source link.
- `contract_flags.csv`: every flagged contract.
- `missing_data.csv` and `missing_data.md`: missing contract-level fields (step 1.5).
