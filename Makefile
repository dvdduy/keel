.PHONY: install format lint type test eval demo seed check

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
	pytest

eval:
	python -m evals.rca.run

demo:
	python -m demo.breaking_change

seed: demo

check: lint type test
	lint-imports
