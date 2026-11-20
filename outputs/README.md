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

Regenerate stages 01 to 06 with `uv run python -m bidlens.outputs`. Last generated 2026-11-19.
