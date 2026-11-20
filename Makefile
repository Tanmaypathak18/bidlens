.PHONY: setup data test lint format

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
	uv run python -m bidlens.outputs

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .
