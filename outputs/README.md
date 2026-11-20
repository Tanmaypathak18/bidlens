# Outputs

Every stage of BidLens writes its results to a numbered folder here, so anyone can follow and check the work in order (decision D-031). Each folder has a README that says what is inside and how it was produced. No file names a bidder: bids are identified by rank. The bid summary PDFs are not included; `03_bid_summaries/pdf_manifest.csv` says where to find each one.

| Stage | Folder | What it shows |
| --- | --- | --- |
| 01 | [`01_source_review/`](01_source_review/README.md) | Where the data comes from: the Caltrans sites, their rules, and sample pages. |
| 02 | [`02_price_collection/`](02_price_collection/README.md) | Every request made to the Caltrans cost database and every bid price collected. |
| 03 | [`03_bid_summaries/`](03_bid_summaries/README.md) | The bid summary PDFs: what was downloaded, what was read, and any problems. |
| 04 | [`04_cross_check/`](04_cross_check/README.md) | Prices from the cost database compared with the same prices in the bid summaries. |
| 05 | [`05_data_quality/`](05_data_quality/README.md) | Missing values and data quality checks on the combined database. |
| 06 | [`06_item_master/`](06_item_master/README.md) | The official Caltrans item list, item families, and how bid items map to it. |
| 07 | [`07_data_overview/`](07_data_overview/README.md) | The results of `notebooks/01_data_overview.ipynb`: a plain-language tour of the data |
| 08 | [`08_target_split_metrics/`](08_target_split_metrics/README.md) | How BidLens will be tested, and how well two simple yardsticks do on that test (step 2.1). |
| 09 | [`09_price_escalation/`](09_price_escalation/README.md) | Bringing old bid prices to today's dollars with Caltrans' own cost index (step 2.2). |
| 10 | [`10_baselines/`](10_baselines/README.md) | Two machine-learning models that price bid items, scored on the step 2.1 test (step 2.3). |
| 11 | [`11_kumo_tabular/`](11_kumo_tabular/README.md) | NVIDIA Kumo Tabular, a pretrained model for tables, scored on the same test as the |
| 12 | [`12_sanity_check/`](12_sanity_check/README.md) | A check of the pricing results so far, in plain terms (after step 2.4). |
| 13 | [`13_model_comparison/`](13_model_comparison/README.md) | Which pricing method BidLens uses, and how it compares with Caltrans' engineer's estimate |
| 14 | [`14_price_ranges/`](14_price_ranges/README.md) | A low / likely / high price for every bid item, and the past bids behind it (step 2.6). |
| 15 | [`15_market_context/`](15_market_context/README.md) | What the market is likely to do on a contract: how the low bid will compare with the |
| 16 | [`16_bid_package/`](16_bid_package/README.md) | The sample bid package BidLens reads in Phase 3: Caltrans contract 04-0W0504 (step 3.1). |
| 17 | [`17_document_parsing/`](17_document_parsing/README.md) | The bid package turned into text BidLens can search and cite (step 3.2). |
| 18 | [`18_extraction/`](18_extraction/README.md) | What BidLens reads out of the bid documents for contract 04-0W0504, with the page each |
| 19 | [`19_extraction_evaluation/`](19_extraction_evaluation/README.md) | None |

Regenerate stages 01 to 06 with `uv run python -m bidlens.outputs`. Last generated 2026-11-20.
