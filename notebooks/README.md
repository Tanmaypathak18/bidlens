# Notebooks

The BidLens analysis, step by step, in order (decision D-032). Each notebook opens with a plain-language summary (the question, what we did, what we found) and explains every chart before showing it. They are committed with their charts saved, so they read directly on GitHub. The code they call lives in `src/bidlens/`. Each one saves its results to a numbered folder in [`outputs/`](../outputs/README.md). No notebook names a bidder.

| Notebook | What it covers | Results in |
| --- | --- | --- |
| [01_data_overview](01_data_overview.ipynb) | What we collected, coverage by district and year, the cross-check between the two Caltrans sources, and data quality | `outputs/07_data_overview/` |
| [02_price_escalation](02_price_escalation.ipynb) | Bringing past prices to bid-day dollars with Caltrans' own cost index (step 2.2) | `outputs/09_price_escalation/` |
| [03_xgboost_baseline](03_xgboost_baseline.ipynb) | The test rules, and the first pricing models (XGBoost, LightGBM) against the historical median (steps 2.1, 2.3) | `outputs/08_` and `10_baselines/` |
| [04_kumo_tabular](04_kumo_tabular.ipynb) | NVIDIA Kumo Tabular on the same test; why single items miss; why frozen models drift high (step 2.4) | `outputs/11_` and `12_sanity_check/` |
| [05_model_comparison](05_model_comparison.ipynb) | **The headline:** BidLens totals against Caltrans' engineer's estimate on 178 test contracts; price ranges (steps 2.5, 2.6) | `outputs/13_` and `14_price_ranges/` |
| [06_market_context](06_market_context.ipynb) | Where the low bid lands against the engineer's estimate, and how many contractors bid (step 2.7) | `outputs/15_market_context/` |
| [07_document_extraction](07_document_extraction.ipynb) | Reading a real bid package with local models, scored against 89 gold facts; the draft estimate checked against the real result (Phase 3, steps 4.1, 4.2) | `outputs/17_` to `21_app/` |

**To rerun one:** notebooks 02 to 07 read the results each stage already saved in `outputs/` (decision D-070), so they run in seconds on a fresh clone:
`uv run jupyter nbconvert --execute --to notebook --inplace notebooks/<name>.ipynb`.
Notebook 01 reads the database, so it needs `make data` first. Each notebook ends with the command that recomputes its stage from scratch.
