# 07 Data overview

The results of `notebooks/01_data_overview.ipynb`: a plain-language tour of the data
collected in stages 02 to 06. It covers coverage by district and year, bid summary
coverage, item families, the cross-check between the two Caltrans sources, and data
quality.

| File |
| --- |
| `bid_summary_coverage.png` |
| `bid_summary_coverage_by_year.csv` |
| `contracts_by_year.csv` |
| `contracts_by_year.png` |
| `cross_check.png` |
| `cross_check_summary.csv` |
| `data_quality_summary.csv` |
| `headline.csv` |
| `hma_type_a_prices.png` |
| `item_families.csv` |
| `low_bid_dollars_by_family.png` |

**How it was produced:** run the notebook top to bottom:
`uv run jupyter nbconvert --execute --to notebook --inplace notebooks/01_data_overview.ipynb`.
It reads `data/bidlens.duckdb` (built by `make data`) and calls
`src/bidlens/analysis/overview.py`. The charts here are the same ones shown in the notebook.
No file names a bidder.
