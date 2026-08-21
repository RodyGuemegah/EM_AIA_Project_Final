.PHONY: install test lint sanity ingest clean

install:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	@echo "✓ Environnement prêt. Active-le : source .venv/bin/activate"

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check src tests

sanity:
	.venv/bin/python -m src.sanity data/raw/CMAPSSData

ingest:
	.venv/bin/python -m src.ingestion

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache
