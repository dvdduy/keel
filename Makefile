.PHONY: install format lint type test eval check

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

check: lint type test
	lint-imports
