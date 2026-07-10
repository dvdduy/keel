.PHONY: install format lint type test test-integration eval demo seed check check-all

install:
	pip install -e ".[dev]"

format:
	black .
	ruff check --fix .

lint:
	ruff check .
	black --check .

type:
	mypy src evals

test:
	python -m pytest -m "not integration"

test-integration:
	python -m pytest -m integration

eval:
	python -m evals.rca.run

demo:
	python -m demo.breaking_change

seed: demo

check: lint type test
	lint-imports

check-all: lint type test test-integration
	lint-imports
