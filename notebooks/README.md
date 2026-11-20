# Notebooks

The BidLens analysis, step by step, in order (decision D-032). Each notebook opens with a plain-language summary (the question, what we did, what we found) and explains every chart before showing it. They are committed with their charts saved, so they read directly on GitHub. The code they call lives in `src/bidlens/`. Each one saves its results to a numbered folder in [`outputs/`](../outputs/README.md). No notebook names a bidder.

| Notebook | What it covers | Results in |
| --- | --- | --- |
| [01_data_overview](01_data_overview.ipynb) | What we collected, coverage by district and year, the cross-check between the two Caltrans sources, and data quality | `outputs/07_data_overview/` |
| 02_price_escalation | Bringing past prices to today's dollars with the Caltrans Construction Cost Index (step 2.2) | planned |
| 03_xgboost_baseline | The first pricing model and its baselines (step 2.3) | planned |
| 04_kumo_tabular | NVIDIA Kumo Tabular on the same test (step 2.4) | planned |
| 05_model_comparison | XGBoost, LightGBM and Kumo against Caltrans' engineer's estimate (step 2.5) | planned |
| 06_market_context | Expected bid spread and bidder count (step 2.7) | planned |
| 07_document_extraction | Reading scope, risks and requirements from bid documents (phase 3) | planned |

**To rerun one:** build the data with `make data`, then run
`uv run jupyter nbconvert --execute --to notebook --inplace notebooks/<name>.ipynb`.
