.PHONY: setup data pricing test lint format

setup:
	uv sync

# Rebuild everything from the raw cache (step 1.6). Network requests happen only for
# pages missing from data/raw/sv08data; bid summary PDFs must already be in
# data/raw/bid_summaries (downloaded by hand, D-014).
data:
	uv run python -m bidlens.ingest.caltrans all
	uv run python -m bidlens.ingest.check_bid_summaries
	uv run python -m bidlens.db.load
	uv run python -m bidlens.db.checks
	uv run python -m bidlens.pricing.escalate
	uv run python -m bidlens.outputs

# Pricing models and reports (steps 2.1 to 2.6), after `make data`. Each model library runs
# in its own process (PyTorch and XGBoost/LightGBM clash on macOS). About 12 minutes.
pricing:
	uv run python -m bidlens.pricing.compare
	uv run python -m bidlens.pricing.baseline
	uv run python -m bidlens.pricing.kumo
	uv run python -m bidlens.pricing.sanity
	uv run python -m bidlens.pricing.refresh --model xgboost
	uv run python -m bidlens.pricing.refresh --model lightgbm
	uv run python -m bidlens.pricing.refresh --model kumo
	uv run python -m bidlens.pricing.select
	uv run python -m bidlens.pricing.ranges

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .
