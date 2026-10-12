.PHONY: install run run-windows test lint typecheck clean

install:
	pip install -r requirements.txt && pip install -e .
	cd frontend && npm install

run:
	bash start_monika.sh

run-windows:
	start_monika.bat

test:
	PYTHONPATH=src pytest tests -v

lint:
	ruff check .

typecheck:
	npx pyright

clean:
	python -c "import os, shutil; [shutil.rmtree(os.path.join(r, d), ignore_errors=True) for r, ds, fs in os.walk('.') if not any(x in r for x in ('node_modules', '.git', 'venv', '.venv')) for d in list(ds) if d in ('__pycache__', '.pytest_cache', '.ruff_cache')]; [os.remove(os.path.join(r, f)) for r, ds, fs in os.walk('.') if not any(x in r for x in ('node_modules', '.git', 'venv', '.venv')) for f in fs if f.endswith(('.pyc', '.pyo'))]"
