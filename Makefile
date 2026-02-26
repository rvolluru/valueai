PYTHON ?= python3

.PHONY: run test lint

run:
	PYTHONPATH=apps/api:packages/brand/src:packages/condition/src:packages/valuation/src $(PYTHON) -m uvicorn app.main:app --app-dir apps/api --reload --host 0.0.0.0 --port 8000

test:
	PYTHONPATH=apps/api:packages/brand/src:packages/condition/src:packages/valuation/src $(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .
