.PHONY: setup data test lint format

setup:
	uv sync

data:
	@echo "make data: the pipeline is built in steps 1.2-1.6 and is not implemented yet." >&2
	@exit 1

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .
