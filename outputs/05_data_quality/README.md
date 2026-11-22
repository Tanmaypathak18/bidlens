# 05 Data quality

Missing values and data quality checks on the combined database.

| File | Rows | What it is |
| --- | --- | --- |
| `missing_data.csv` | 180 | Every contract opening missing a contract-level field, which fields, and why |
| `missing_data.md` | | The same, as a report with totals (step 1.5) |
| `data_quality.md` | | Checks on prices and contracts (step 1.6): what was checked, how many failed, and what it means |
| `bid_flags.csv` | | Every flagged bid price, with its flag, detail and source link |
| `contract_flags.csv` | | Every flagged contract |

**How it was produced:** from `data/bidlens.duckdb`, which `uv run python -m bidlens.db.load` builds. `uv run python -m bidlens.db.checks` runs the checks. Both are part of `make data`. Flagged data is never deleted. Most missing fields come from contracts that have no usable bid summary (see `03_bid_summaries/coverage.md`).
