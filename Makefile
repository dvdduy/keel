.PHONY: install format lint type test check

install:
	pip install -e ".[dev]"

format:
	black .
	ruff check --fix .

lint:
	ruff check .
	black --check .

type:
	mypy src

test:
	pytest

check: lint type test
	lint-imports