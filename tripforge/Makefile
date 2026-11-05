.PHONY: setup test lint demo

setup:
	uv sync --group dev

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .

demo:
	uv run tripforge examples/vietnam/notes.md \
		--brief examples/vietnam/brief.json \
		--seed examples/vietnam/geocode_seed.csv --offline \
		--start 2027-01-10 --out out/vietnam
