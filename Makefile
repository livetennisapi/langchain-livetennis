.PHONY: all install test integration_test lint format check build clean

all: help

install:
	uv sync --all-groups

TEST_FILE ?= tests/unit_tests/

test:
	uv run --group test pytest --disable-socket --allow-unix-socket $(TEST_FILE)

integration_test:
	uv run --group test pytest tests/integration_tests/

lint:
	uv run --group lint ruff check .
	uv run --group lint ruff format --check .

format:
	uv run --group lint ruff format .
	uv run --group lint ruff check --fix .

check:
	uv run --group typing mypy langchain_livetennis

build:
	uv run --with build python -m build

clean:
	rm -rf dist build .pytest_cache .mypy_cache .ruff_cache

help:
	@echo "install          install every dependency group"
	@echo "test             run the unit tests with the network blocked"
	@echo "integration_test run the tests that need a real LIVETENNISAPI_KEY"
	@echo "lint             ruff check + format check"
	@echo "format           apply ruff fixes and formatting"
	@echo "check            mypy"
	@echo "build            build the wheel and sdist"
