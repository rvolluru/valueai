PYTHON ?= python3

.PHONY: run backend-dev-start backend-dev-stop backend-dev-restart backend-dev-status backend-dev-logs test lint train-logo-yolo-litw

run:
	PYTHONPATH=apps/api:packages/brand/src:packages/condition/src:packages/valuation/src $(PYTHON) -m uvicorn app.main:app --app-dir apps/api --reload --host 0.0.0.0 --port 8000

backend-dev-start:
	./scripts/backend-dev.sh start

backend-dev-stop:
	./scripts/backend-dev.sh stop

backend-dev-restart:
	./scripts/backend-dev.sh restart

backend-dev-status:
	./scripts/backend-dev.sh status

backend-dev-logs:
	./scripts/backend-dev.sh logs

test:
	PYTHONPATH=apps/api:packages/brand/src:packages/condition/src:packages/valuation/src $(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .

train-logo-yolo-litw:
	PYTHONPATH=apps/api:packages/brand/src:packages/condition/src:packages/valuation/src $(PYTHON) scripts/train_logo_yolo_litw.py
